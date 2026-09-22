"""
Concurrency identity gate for Phase B (parallel Stage B / TS2).

The core Phase-B guarantee: running the pipeline with N parallel engine workers
produces output IDENTICAL to a single worker — parallelism changes *when* a
position is evaluated, never *what* the profile contains.

Design (deliberately cache-INDEPENDENT and store-ISOLATED, unlike a naive
"replay the real cache" gate, which our truncated 76%-steering cache can't
satisfy and which would clobber the real profile):
  - DetEngine returns evals/policy as a PURE FUNCTION of the FEN, and is TOTAL
    (never raises), so both runs see identical per-position data regardless of
    completion order. Any n=1 vs n=4 difference is therefore a pure concurrency
    bug (ordering, in-flight dedup, or budget race) — exactly what we must catch.
  - store dirs are monkeypatched to tmp, so no real data is touched and the two
    runs don't share a cache.

Mutation-checked by the leader: removing the result `.sort(...)` in pipeline.py
(Stage B or TS2) makes this fail with an ID-order mismatch.
"""
import asyncio
import hashlib
from pathlib import Path

import chess
import pytest

from backend.engine_pool import EnginePool
from backend.training import store, pipeline, metrics

_PGN = Path("games_of_derdiedasdie/test_subset.pgn")


def _first_n_games(pgn_text: str, n: int) -> str:
    """First n games of a multi-game PGN (keeps the gate fast but multi-game,
    so cross-game ordering is still exercised)."""
    parts = pgn_text.split("\n[Event ")
    games = [parts[0]] + ["[Event " + p for p in parts[1:]]
    return "\n".join(games[:n])


def _det_int(fen: str, lo: int, hi: int) -> int:
    """Deterministic int in [lo, hi] from the FEN."""
    h = int(hashlib.sha1(fen.encode()).hexdigest(), 16)
    return lo + (h % (hi - lo + 1))


class DetEngine:
    """Deterministic, total engine: same FEN -> same output on any worker."""

    n = 1

    async def start(self):
        pass

    async def stop(self):
        pass

    def is_available(self):
        return True

    async def get_policy_distribution(self, fen, nodes=1):
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
        # Deterministic, FEN-dependent delay so concurrent tasks COMPLETE out of
        # submission order — this is what makes the result `.sort()` load-bearing
        # and the gate actually sensitive to an ordering bug (verified: without
        # this, disabling the TS2 sort does not fail the gate).
        await asyncio.sleep((_det_int(fen, 0, 9) + 1) * 0.001)
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


async def _run(job_id, engine, tmp_dir, monkeypatch):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_dir))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_dir))
    pgn_text = _first_n_games(_PGN.read_text(encoding="utf-8"), 6)
    await pipeline.run_diagnosis(job_id, pgn_text, "derdiedasdie", engine, DetVision())
    prof = store.load_profile()
    assert prof is not None
    return ([f["id"] for f in prof.get("findings", [])],
            [s["id"] for s in prof.get("steer_findings", [])])


@pytest.mark.anyio
async def test_parallel_identity_workers_1_vs_4(tmp_path, monkeypatch):
    assert _PGN.exists(), "test_subset.pgn required"

    # Force steer emission for ANY playable candidate so the TS2 concurrency path
    # is actually exercised (mirrors the steer unit tests; test-scoped, not an
    # edit to leader-owned metrics.py). Restored by the finally.
    cfg = metrics.DEFAULT_CONFIG
    saved = (cfg.steer_highlight_complexity, cfg.steer_search_budget)
    object.__setattr__(cfg, "steer_highlight_complexity", 0.0)
    object.__setattr__(cfg, "steer_search_budget", 100000)
    try:
        w1 = tmp_path / "w1"
        w1.mkdir()
        f1, s1 = await _run("gate_w1", DetEngine(), w1, monkeypatch)

        pool = EnginePool(4, DetEngine)
        await pool.start()
        w4 = tmp_path / "w4"
        w4.mkdir()
        f4, s4 = await _run("gate_w4", pool, w4, monkeypatch)
        await pool.stop()
    finally:
        object.__setattr__(cfg, "steer_highlight_complexity", saved[0])
        object.__setattr__(cfg, "steer_search_budget", saved[1])

    # The gate must exercise real work, or it proves nothing.
    assert len(f1) > 0, "no findings produced — gate is vacuous"
    assert len(s1) > 0, "no steer findings produced — TS2 not exercised"

    # Parallelism must not change the profile: identical counts AND ID ordering.
    assert f1 == f4, f"findings differ n1 vs n4: {len(f1)} vs {len(f4)}"
    assert s1 == s4, f"steer_findings differ n1 vs n4: {len(s1)} vs {len(s4)}"
