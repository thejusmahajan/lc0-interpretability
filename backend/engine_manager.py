"""
UCI Engine Wrapper for LC0 (Leela Chess Zero).

Provides an async-friendly interface to the LC0 chess engine using
python-chess's SimpleEngine.popen_uci(). Falls back to mock mode
when the engine binary is not available.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional
import re

import chess
import chess.engine

from backend.mock_data import get_mock_analysis

logger = logging.getLogger(__name__)

# Default engine directory
ENGINE_DIR = Path(r"C:\Users\Admin\Documents\chess_speak_out_loud\engine")

# Wall-clock safety net for node-limited searches: high enough that a normal
# node-limited search (sub-second on GPU, a few seconds on CPU) never hits it,
# but bounded so a stalled/deadlocked engine can't hang a multi-hour paid run.
NODE_LIMIT_SAFETY_SECONDS = 30.0


def terminal_analysis(board: "chess.Board") -> dict:
    """Synthetic analyze() result for a no-legal-moves position (checkmate or
    stalemate). lc0 emits 'bestmove a1a1' for these, which crashes the UCI
    parser, so we never send them to the engine. Evaluation is white-POV, with
    ±10000 matching eval_cp_number's mate magnitude (sign preserved, unlike an
    'M0' string). Shape matches the normal analyze() dict."""
    if board.is_checkmate():
        white_mated = board.turn == chess.WHITE   # side to move is the mated side
        return {
            "evaluation": -10000 if white_mated else 10000,
            "best_moves": [], "pv_lines": [], "nodes": 0,
            "wdl": [0, 0, 1000] if white_mated else [1000, 0, 0],
        }
    # stalemate = draw
    return {"evaluation": 0, "best_moves": [], "pv_lines": [], "nodes": 0,
            "wdl": [0, 1000, 0]}


class LC0Engine:
    """
    Wrapper around the LC0 UCI chess engine.

    If the engine binary is not found or fails to start, the engine
    transparently falls back to mock mode, returning pre-computed
    analysis from the mock_data module.
    """

    def __init__(
        self,
        engine_path: Optional[str | Path] = None,
        weights_path: Optional[str | Path] = None,
        custom_uci_options: Optional[dict] = None,
        gpu_id: Optional[int] = None,
    ) -> None:
        """
        Initialize the LC0 engine wrapper.

        Args:
            engine_path: Absolute path to the lc0.exe binary.
                         Defaults to ENGINE_DIR / "lc0.exe".
            weights_path: Absolute path to the .pb.gz weights file.
                          If None, LC0 will use its default weights.
            custom_uci_options: Optional dict of UCI options to apply on start.
        """
        self.engine_path: Path = Path(engine_path) if engine_path else ENGINE_DIR / "lc0.exe"
        self.weights_path: Optional[Path] = Path(weights_path) if weights_path else None
        self.custom_uci_options: dict = custom_uci_options or {}
        self.gpu_id: Optional[int] = gpu_id
        self.engine: Optional[chess.engine.SimpleEngine] = None
        self.mock_mode: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

        # Dedicated event loop for all engine I/O.
        #
        # python-chess spawns the engine as a subprocess, which on Windows
        # requires a ProactorEventLoop. Uvicorn's --reload mode runs the
        # server on a SelectorEventLoop (which raises a bare
        # NotImplementedError when asked to spawn a subprocess), so we run
        # every engine coroutine on our own Proactor loop in a background
        # thread. This keeps the engine working regardless of how the
        # server was launched.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def _ensure_loop(self) -> None:
        """Start the dedicated engine event loop thread (idempotent)."""
        if self._loop is not None:
            return
        if sys.platform == "win32":
            self._loop = asyncio.ProactorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            name="lc0-engine-loop",
            daemon=True,
        )
        self._thread.start()

    async def _submit(self, coro):
        """Run *coro* on the dedicated engine loop and await the result."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(fut)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the LC0 subprocess cleanly (idempotent).

        If the process dies unexpectedly, calling start() will spawn a fresh process.
        """
        if self.engine is not None and not self.mock_mode:
            return

        if not self.engine_path.exists():
            logger.warning(
                "Engine binary not found at %s — entering mock mode.",
                self.engine_path,
            )
            self.mock_mode = True
            return

        self._ensure_loop()
        try:
            await self._submit(self._start_impl())
            self.mock_mode = False
            logger.info("LC0 engine started successfully from %s", self.engine_path)
        except Exception as exc:
            logger.error(
                "Failed to start engine: %r — entering mock mode.", exc
            )
            self.engine = None
            self.mock_mode = True

    async def _start_impl(self) -> None:
        """Spawn the engine and apply UCI options. Runs on the engine loop."""
        # Build UCI options with high-throughput defaults for GPU execution
        uci_options: dict = {
            "UCI_ShowWDL": True,
            "PerPVCounters": True,
            "RamLimitMb": int(os.environ.get("LC0_RAM_LIMIT_MB", "8192")),
            "NNCacheSize": int(os.environ.get("LC0_NN_CACHE_SIZE", "500000")),
            # lc0's cuda/cuda-fp16 backend caps MinibatchSize at 1024; asking for
            # more is rejected and silently falls back to a small default (~256).
            # 1024 is the max these backends accept and gives the best batching
            # for our node-limited searches (fewer, larger GPU forwards).
            "MinibatchSize": 1024,
            "Threads": 4,
        }
        # Explicitly select the lc0 backend when requested. On a CUDA GPU,
        # LC0_BACKEND=cuda-fp16 uses the fp16 tensor-core path and is ~8x
        # faster than lc0's auto pick (measured on an A100: 168k vs 22k nps).
        # Unset = lc0 auto-detect, the safe default for CPU-only machines
        # (forcing a cuda backend there would fail to initialize).
        lc0_backend = os.environ.get("LC0_BACKEND")
        if lc0_backend:
            uci_options["Backend"] = lc0_backend
        if self.weights_path and self.weights_path.exists():
            uci_options["WeightsFile"] = str(self.weights_path)

        # Auto-detect weights in the engine directory if not specified
        if not self.weights_path:
            weights_candidates = list(ENGINE_DIR.glob("*.pb.gz"))
            if weights_candidates:
                uci_options["WeightsFile"] = str(weights_candidates[0])
                logger.info("Auto-detected weights: %s", weights_candidates[0])

        # Apply caller-supplied UCI options LAST so a pool can override defaults
        # per worker — e.g. BackendOptions="gpu=N" to pin each engine to its own
        # GPU. (Previously self.custom_uci_options was stored but never applied.)
        uci_options.update(self.custom_uci_options)

        # Build engine start command line passing weights file if available
        cmd = [str(self.engine_path)]
        if self.weights_path and self.weights_path.exists():
            cmd.append(f"--weights={str(self.weights_path)}")

        # Start engine natively. When gpu_id is set, isolate THIS engine's subprocess
        # to that physical GPU via CUDA_VISIBLE_DEVICES — OS-level and unignorable,
        # unlike lc0's BackendOptions="gpu=N" (which lc0 ignored, so a pool piled every
        # worker onto GPU0). Child-only env; the parent process's torch model is
        # unaffected. Each engine then sees a single GPU and uses it as device 0.
        popen_kwargs: dict = {}
        if self.gpu_id is not None:
            popen_kwargs["env"] = {**os.environ, "CUDA_VISIBLE_DEVICES": str(self.gpu_id)}
        transport, engine = await chess.engine.popen_uci(cmd, **popen_kwargs)

        # Ensure WeightsFile option is placed first if present in uci_options
        ordered_options = {}
        if "WeightsFile" in uci_options:
            ordered_options["WeightsFile"] = uci_options.pop("WeightsFile")
        ordered_options.update(uci_options)

        # Apply UCI options (with fallback for unsupported flags)
        for key, value in ordered_options.items():
            try:
                await engine.configure({key: value})
            except Exception as opt_err:
                logger.warning("Could not set UCI option %s=%s: %s", key, value, opt_err)

        self.engine = engine

    async def stop(self) -> None:
        """Quit the engine subprocess cleanly and stop the engine loop."""
        if self.engine is not None:
            try:
                await self._submit(self.engine.quit())
                logger.info("Engine stopped.")
            except Exception as exc:
                logger.warning("Error while stopping engine: %s", exc)
            finally:
                self.engine = None
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None
            self._thread = None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def get_policy_distribution(self, fen: str, nodes: int = 1) -> list[dict]:
        """
        Return LC0's raw policy-head distribution for a position.
        Each entry: {"uci","san","from","to","p","q","n","wdl"}
        Sorted descending by p. p is a float in [0,1] (fraction, not percent).
        Returns [] in mock mode.
        """
        if self.mock_mode or self.engine is None:
            return []

        return await self._submit(self._get_policy_distribution_impl(fen, nodes))

    async def _get_policy_distribution_impl(self, fen: str, nodes: int = 1) -> list[dict]:
        """Body of get_policy_distribution. Runs on the engine loop."""
        async with self._lock:
            verbose_set = False
            try:
                board = chess.Board(fen)
                if board.is_checkmate() or board.is_stalemate():
                    # No legal moves -> no policy. lc0 emits 'bestmove a1a1' here,
                    # which crashes the analysis stream (same a1a1 bug as analyze).
                    return []
                await self.engine.configure({'VerboseMoveStats': True})
                verbose_set = True
                policies = []
                
                # regex to match: e2e4  (322 ) N:       0 (+ 0) (P: 22.22%) ...
                pattern = re.compile(r'^([a-h][1-8][a-h][1-8][qrbn]?)\s+.*?N:\s*(\d+).*?\(P:\s*([\d.]+)%\)')
                
                with await self.engine.analysis(board, chess.engine.Limit(
                        nodes=nodes, time=NODE_LIMIT_SAFETY_SECONDS)) as analysis:
                    async for info in analysis:
                        if 'string' in info:
                            line = info['string']
                            if line.startswith('node'):
                                continue
                                
                            m = pattern.search(line)
                            if m:
                                uci_str = m.group(1)
                                n_val = int(m.group(2))
                                p_pct = float(m.group(3))
                                
                                try:
                                    move = chess.Move.from_uci(uci_str)
                                    san_str = board.san(move)
                                except Exception:
                                    san_str = uci_str
                                    
                                policies.append({
                                    "uci": uci_str,
                                    "san": san_str,
                                    "from": uci_str[:2],
                                    "to": uci_str[2:4],
                                    "p": p_pct / 100.0,
                                    "q": 0.0,
                                    "n": n_val,
                                    "wdl": None
                                })
                
                # Sort descending by p
                policies.sort(key=lambda x: x['p'], reverse=True)
                return policies

            except Exception as exc:
                logger.error("Failed to get policy distribution: %s", exc)
                return []
            finally:
                # Always restore VerboseMoveStats. The old reset lived inside the
                # try AFTER the loop, so a mid-stream error skipped it and left the
                # flag ON for every later search (state leak per the a1a1 review).
                if verbose_set:
                    try:
                        await self.engine.configure({'VerboseMoveStats': False})
                    except Exception:
                        pass

    def is_available(self) -> bool:
        """Return True if a real engine connection is active."""
        return self.engine is not None and not self.mock_mode

    async def search_lines(self, fen: str, time_limit: float = 5.0, multipv: int = 3) -> list[dict]:
        """
        Run a timed multipv search and return the top PV lines as move sequences,
        for Calculation Glow aggregation. Each item:
            {"moves": [chess.Move, ...], "weight": float}
        weight is a simple rank decay (top line heaviest). [] in mock mode.
        """
        if self.mock_mode or self.engine is None:
            return []
        return await self._submit(self._search_lines_impl(fen, time_limit, multipv))

    async def _search_lines_impl(self, fen: str, time_limit: float, multipv: int) -> list[dict]:
        """Body of search_lines. Runs on the engine loop."""
        async with self._lock:
            try:
                board = chess.Board(fen)
                if board.is_checkmate() or board.is_stalemate():
                    return []   # no legal moves -> lc0 'a1a1' would crash the search
                infos = await self.engine.analyse(
                    board,
                    chess.engine.Limit(time=time_limit),
                    multipv=max(1, min(multipv, 10)),
                )
                if not isinstance(infos, list):
                    infos = [infos]
                lines = []
                for rank, info in enumerate(infos):
                    pv = info.get("pv", [])
                    if not pv:
                        continue
                    lines.append({"moves": list(pv), "weight": 1.0 / (rank + 1)})
                return lines
            except Exception as exc:
                logger.error("search_lines failed: %s", exc)
                return []

    async def analyze(
        self,
        fen: str,
        depth: int = 20,
        multipv: int = 3,
        time_limit: float = 2.0,
        nodes: Optional[int] = None,
    ) -> dict:
        """
        Analyze a chess position. Acquires the engine lock and waits
        if another analysis is in progress.

        If ``nodes`` is given, the search is node-limited (deterministic depth,
        wall time scales with backend speed) and both ``time_limit`` and
        ``depth`` are ignored. Otherwise it is time-limited as before.
        """
        if self.mock_mode or self.engine is None:
            return get_mock_analysis(fen)

        return await self._submit(self._analyze_impl(fen, depth, multipv, time_limit, nodes))

    async def _analyze_impl(self, fen, depth, multipv, time_limit, nodes=None) -> dict:
        """Body of analyze. Runs on the engine loop."""
        async with self._lock:
            return await self._do_analyze(fen, depth, multipv, time_limit, nodes)

    async def fast_analyze(
        self,
        fen: str,
        depth: int = 20,
        multipv: int = 1,
        time_limit: float = 1.0,
    ) -> dict:
        """
        Non-blocking analyze: if the engine is busy (lock held),
        immediately returns mock data instead of waiting.
        """
        if self.mock_mode or self.engine is None:
            return get_mock_analysis(fen)

        return await self._submit(self._fast_analyze_impl(fen, depth, multipv, time_limit))

    async def _fast_analyze_impl(self, fen, depth, multipv, time_limit) -> dict:
        """Body of fast_analyze. Runs on the engine loop."""
        if self._lock.locked():
            logger.info("Engine busy — returning mock data for fast_analyze")
            return get_mock_analysis(fen)

        async with self._lock:
            return await self._do_analyze(fen, depth, multipv, time_limit)

    async def _do_analyze(
        self,
        fen: str,
        depth,
        multipv: int,
        time_limit: float,
        nodes: Optional[int] = None,
    ) -> dict:
        """Internal: run the actual engine analysis. Caller must hold _lock."""
        try:
            board = chess.Board(fen)
            # Terminal positions (no legal moves) make lc0 emit "bestmove a1a1",
            # which python-chess rejects -> EngineError that can corrupt the
            # protocol and crash the whole diagnosis. A candidate move that mates
            # or stalemates lands here. Return a synthetic eval instead of asking
            # the engine to "search" a position with nothing to search.
            if board.is_checkmate() or board.is_stalemate():
                return terminal_analysis(board)
            if nodes is not None:
                # Node-limited: deterministic search depth regardless of backend
                # speed. Ignores depth so quality is hardware-independent, but
                # keeps a generous wall-clock cap so a stalled engine can't hang
                # a paid run (the engine stops at whichever limit is hit first;
                # a normal node search finishes far under the cap).
                limit_kwargs = {
                    "nodes": nodes,
                    "time": max(time_limit or 0.0, NODE_LIMIT_SAFETY_SECONDS),
                }
            else:
                limit_kwargs = {"time": time_limit}
                if depth is not None:
                    limit_kwargs["depth"] = depth
            infos = await self.engine.analyse(
                board,
                chess.engine.Limit(**limit_kwargs),
                multipv=multipv,
            )
            
            if not isinstance(infos, list):
                infos = [infos]

            best_moves = []
            pv_lines = []
            evaluation = 0
            nodes = 0
            wdl = None

            for idx, info in enumerate(infos):
                score_obj = info.get("score")
                pv = info.get("pv", [])
                info_nodes = info.get("nodes", 0)

                if score_obj is not None:
                    pov_score = score_obj.white()
                    if pov_score.is_mate():
                        score_cp = f"M{pov_score.mate()}"
                    else:
                        score_cp = pov_score.score()
                else:
                    score_cp = 0

                wdl_obj = info.get("wdl")
                info_wdl = None
                if wdl_obj is not None:
                    try:
                        info_wdl = [wdl_obj.white().wins, wdl_obj.white().draws, wdl_obj.white().losses]
                    except Exception:
                        info_wdl = None

                if idx == 0:
                    evaluation = score_cp
                    nodes = info_nodes
                    wdl = info_wdl

                if pv:
                    move = pv[0]
                    san = board.san(move)
                    best_moves.append({
                        "move": move.uci(),
                        "san": san,
                        "score": score_cp,
                        "nodes": info_nodes,
                        "wdl": info_wdl
                    })

                    pv_san_parts = []
                    temp_board = board.copy()
                    for m in pv:
                        try:
                            pv_san_parts.append(temp_board.san(m))
                            temp_board.push(m)
                        except Exception:
                            break
                    pv_lines.append(" ".join(pv_san_parts))

            return {
                "evaluation": evaluation,
                "best_moves": best_moves,
                "pv_lines": pv_lines,
                "nodes": nodes,
                "wdl": wdl,
            }

        except Exception as exc:
            logger.error("Engine analysis failed: %s — falling back to mock.", exc)
            return get_mock_analysis(fen)
