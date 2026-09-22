"""
Hang-preproduction and completion test for Stage TS2 under heavy transposition load.
"""
import asyncio
import hashlib
import pytest
from pathlib import Path
import chess

from backend.engine_pool import EnginePool
from backend.training import store, pipeline, metrics

_PGN_PATH = Path("games_of_derdiedasdie/test_subset.pgn")


def _det_int(fen: str, lo: int, hi: int) -> int:
    h = int(hashlib.sha1(fen.encode()).hexdigest(), 16)
    return lo + (h % (hi - lo + 1))


class SlowDetEngine:
    """Deterministic engine with sleep to widen in-flight race window under transposition load."""
    n = 1

    async def start(self):
        pass

    async def stop(self):
        pass

    def is_available(self):
        return True

    async def get_policy_distribution(self, fen, nodes=1):
        await asyncio.sleep(0.003)
        board = chess.Board(fen)
        moves = list(board.legal_moves)
        if not moves:
            return []
        base = _det_int(fen, 1, 97)
        out = []
        for i, m in enumerate(moves):
            p = ((base + i * 7) % 100 + 1)
            out.append({"uci": m.uci(), "san": board.san(m), "p": float(p),
                        "from": m.uci()[:2], "to": m.uci()[2:4]})
        total = sum(x["p"] for x in out)
        for x in out:
            x["p"] /= total
        out.sort(key=lambda x: x["p"], reverse=True)
        return out

    async def analyze(self, fen, depth=20, multipv=3, time_limit=2.0, nodes=None):
        await asyncio.sleep(0.003)
        board = chess.Board(fen)
        if board.is_checkmate() or board.is_stalemate():
            return {"evaluation": 0, "best_moves": [], "pv_lines": [], "nodes": 0,
                    "wdl": [0, 1000, 0]}
        ev = _det_int(fen, -300, 300)
        moves = list(board.legal_moves)
        best_moves = [
            {"move": m.uci(), "san": board.san(m), "score": ev - i * 25,
             "nodes": 0, "wdl": None}
            for i, m in enumerate(moves[:max(1, multipv)])
        ]
        pv = board.san(moves[0]) if moves else ""
        return {"evaluation": ev, "best_moves": best_moves, "pv_lines": [pv],
                "nodes": 0, "wdl": [333, 334, 333]}


class DetVision:
    def saliency_absolute(self, fen):
        return {"e4": 0.5, "d4": 0.5}

    def saliency_absolute_batch(self, fens):
        return [{"e4": 0.5, "d4": 0.5} for _ in fens]


def _build_transposition_pgn(repeat_count: int = 5) -> str:
    raw_pgn = _PGN_PATH.read_text(encoding="utf-8")
    parts = raw_pgn.split("\n[Event ")
    first_6 = [parts[0]] + ["[Event " + p for p in parts[1:6]]
    single_block = "\n".join(first_6)
    return "\n\n".join(single_block for _ in range(repeat_count))


@pytest.mark.anyio
async def test_ts2_no_hang_under_heavy_transposition(tmp_path, monkeypatch):
    assert _PGN_PATH.exists(), "test_subset.pgn required"

    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    cfg = metrics.DEFAULT_CONFIG
    saved = (cfg.steer_highlight_complexity, cfg.steer_search_budget)
    object.__setattr__(cfg, "steer_highlight_complexity", 0.0)
    object.__setattr__(cfg, "steer_search_budget", 100000)

    try:
        pgn_text = _build_transposition_pgn(5)
        pool = EnginePool(4, SlowDetEngine)
        await pool.start()

        try:
            await asyncio.wait_for(
                pipeline.run_diagnosis("test_ts2_hang_job", pgn_text, "derdiedasdie", pool, DetVision()),
                timeout=60.0
            )
        finally:
            await pool.stop()

        prof = store.load_profile()
        assert prof is not None, "Profile was not saved"
        steer_findings = prof.get("steer_findings", [])
        assert len(steer_findings) > 0, "No steer findings produced"

    finally:
        object.__setattr__(cfg, "steer_highlight_complexity", saved[0])
        object.__setattr__(cfg, "steer_search_budget", saved[1])


class CancellingTranspositionEngine(SlowDetEngine):
    _cancelled = False

    async def analyze(self, fen, depth=20, multipv=3, time_limit=2.0, nodes=None):
        await asyncio.sleep(0.005)
        if not CancellingTranspositionEngine._cancelled and "r1bqk2r" in fen:
            CancellingTranspositionEngine._cancelled = True
            raise asyncio.CancelledError("Simulated engine cancellation")
        return await super().analyze(fen, depth, multipv, time_limit, nodes)


@pytest.mark.anyio
async def test_ts2_orphan_future_cancellation_handled(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    cfg = metrics.DEFAULT_CONFIG
    saved = (cfg.steer_highlight_complexity, cfg.steer_search_budget)
    object.__setattr__(cfg, "steer_highlight_complexity", 0.0)
    object.__setattr__(cfg, "steer_search_budget", 100000)

    try:
        pgn_text = _build_transposition_pgn(3)
        pool = EnginePool(4, CancellingTranspositionEngine)
        await pool.start()

        try:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(
                    pipeline.run_diagnosis("test_ts2_orphan_job", pgn_text, "derdiedasdie", pool, DetVision()),
                    timeout=10.0
                )
        finally:
            await pool.stop()
    finally:
        object.__setattr__(cfg, "steer_highlight_complexity", saved[0])
        object.__setattr__(cfg, "steer_search_budget", saved[1])
