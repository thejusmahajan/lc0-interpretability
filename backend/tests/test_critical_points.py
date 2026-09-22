"""
Unit tests for Critical Points — selector, cache-hit proof, eval POV, mock-safety.

Each test is mutation-checked: it fails if the behavior under test is broken.
No real engine — uses an async stub with a call-counter.
"""

import os
import asyncio
import pytest

import chess

from backend.training import store, critical_points


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_finding(
    f_id: str,
    swing_cp: int,
    confirmed: bool = True,
    user_color: str = "white",
    fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    played_uci: str = "e2e4",
    played_san: str = "e4",
    best_uci: str = "d2d4",
    best_san: str = "d4",
) -> dict:
    return {
        "id": f_id,
        "ply": 1,
        "user_color": user_color,
        "fen_before": fen,
        "played": {"uci": played_uci, "san": played_san, "p": 0.27},
        "best": {"uci": best_uci, "san": best_san, "p": 0.13},
        "move_number": 1,
        "opening": {"eco": "A00", "name": "Start"},
        "confirmation": {"swing_cp": swing_cp, "confirmed": confirmed},
        "pv_san": ["e4", "d4"],
        "motifs": [],
        "severity": "missed",
    }


class FakeEngine:
    """Async stub that returns canned multipv output and counts calls."""

    def __init__(self, best_moves=None, pv_lines=None, evaluation=50):
        self._best_moves = best_moves if best_moves is not None else [
            {"move": "d2d4", "san": "d4", "score": 30, "nodes": 1000, "wdl": [400, 400, 200]},
            {"move": "e2e4", "san": "e4", "score": 25, "nodes": 900, "wdl": [380, 400, 220]},
            {"move": "c2c4", "san": "c4", "score": 20, "nodes": 800, "wdl": [360, 400, 240]},
            {"move": "g1f3", "san": "Nf3", "score": 15, "nodes": 700, "wdl": [340, 400, 260]},
        ]
        self._pv_lines = pv_lines if pv_lines is not None else [
            "d4 d5 c4 e6",
            "e4 e5 Nf3 Nc6",
            "c4 e5 Nc3 Nf6",
            "Nf3 d5 d4 Nf6",
        ]
        self._evaluation = evaluation
        self.call_count = 0

    async def analyze(self, fen, multipv=1, nodes=None, time_limit=2.0):
        self.call_count += 1
        if multipv == 1:
            # Return a single-line result (for the user's played move eval)
            return {
                "evaluation": self._evaluation,
                "best_moves": self._best_moves[:1] if self._best_moves else [],
                "pv_lines": self._pv_lines[:1] if self._pv_lines else [],
                "nodes": nodes or 4000,
            }
        return {
            "evaluation": self._evaluation,
            "best_moves": self._best_moves[:multipv],
            "pv_lines": self._pv_lines[:multipv],
            "nodes": nodes or 4000,
        }

    def is_available(self):
        return True


class EmptyEngine:
    """Stub that simulates an unavailable/mock engine (empty best_moves)."""

    def __init__(self):
        self.call_count = 0

    async def analyze(self, fen, multipv=1, nodes=None, time_limit=2.0):
        self.call_count += 1
        return {
            "evaluation": 0,
            "best_moves": [],
            "pv_lines": [],
            "nodes": 0,
        }

    def is_available(self):
        return False


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Isolate store data to a temp directory."""
    data_dir = str(tmp_path / "data")
    monkeypatch.setenv("CSZERO_DATA_DIR", data_dir)
    store.DATA_DIR = data_dir
    store.TRAINING_DIR = os.path.join(data_dir, "training")
    store._ensure_dirs()
    yield data_dir


# ------------------------------------------------------------------
# Test 1 — Selector: threshold + sort
# ------------------------------------------------------------------

def test_select_critical_points_threshold_and_sort():
    """Findings with swing 150/250/900:
    - min_swing=200 → only 250 and 900 are returned
    - Sorted: 900 first, then 250
    Mutation: fails if threshold or sort is wrong.
    """
    f150 = _make_finding("g000-p001", swing_cp=150)
    f250 = _make_finding("g000-p002", swing_cp=250)
    f900 = _make_finding("g000-p003", swing_cp=900)

    profile = {"findings": [f150, f250, f900]}

    result = critical_points.select_critical_points(profile, min_swing=200)

    # Only the two above threshold
    assert len(result) == 2, f"Expected 2 results, got {len(result)}"

    # 150 excluded
    result_ids = [f["id"] for f in result]
    assert "g000-p001" not in result_ids, "150cp finding should be excluded"

    # Sorted by swing_cp DESC: 900 first
    assert result[0]["confirmation"]["swing_cp"] == 900
    assert result[1]["confirmation"]["swing_cp"] == 250

    # Mutation guard: exact threshold (200 should NOT be included with min_swing=200+1)
    result_exact = critical_points.select_critical_points(profile, min_swing=250)
    assert len(result_exact) == 2
    result_above = critical_points.select_critical_points(profile, min_swing=251)
    assert len(result_above) == 1
    assert result_above[0]["confirmation"]["swing_cp"] == 900


# ------------------------------------------------------------------
# Test 2 — Cache proof: second call skips the engine
# ------------------------------------------------------------------

def test_cache_hit_skips_engine():
    """Call critical_lines() TWICE for the same FEN.
    The stub call_count must be 2 after the first call (multipv + played)
    and still 2 after the second (cache hit, no engine).
    Mutation: fails if the cache is bypassed.
    """
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    engine = FakeEngine()

    # First call — engine should be invoked
    v1 = asyncio.run(
        critical_points.critical_lines(
            fen, "e2e4", "white", engine, multipv=4, nodes=4000
        )
    )
    calls_after_first = engine.call_count
    assert calls_after_first == 2, (
        f"First call should invoke engine exactly 2 times (multipv + played), got {calls_after_first}"
    )
    assert "error" not in v1
    assert "lines" in v1
    assert "played" in v1

    # Second call — should be a cache hit, NO engine invocation
    v2 = asyncio.run(
        critical_points.critical_lines(
            fen, "e2e4", "white", engine, multipv=4, nodes=4000
        )
    )
    calls_after_second = engine.call_count
    assert calls_after_second == 2, (
        f"Second call must NOT invoke engine (cache hit). "
        f"Expected 2 total calls, got {calls_after_second}"
    )

    # Verdicts must match
    assert v1["epd"] == v2["epd"]
    assert v1["lines"] == v2["lines"]
    assert v1["played"] == v2["played"]


# ------------------------------------------------------------------
# Test 3 — Eval POV: black player sees flipped eval
# ------------------------------------------------------------------

def test_eval_pov_black_player():
    """user_color='black', stub returns white-POV score=+300.
    The line's eval_cp must be -300 (mover POV).
    Mutation: fails if the color flip is dropped.
    """
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    engine = FakeEngine(
        best_moves=[
            {"move": "e7e5", "san": "e5", "score": 300, "nodes": 1000, "wdl": [400, 400, 200]},
            {"move": "d7d5", "san": "d5", "score": 250, "nodes": 900, "wdl": [380, 400, 220]},
        ],
        pv_lines=["e5 Nf3 Nc6 Bb5", "d5 exd5 Qxd5 Nc3"],
        evaluation=300,
    )

    verdict = asyncio.run(
        critical_points.critical_lines(
            fen, "e7e5", "black", engine, multipv=2, nodes=4000
        )
    )

    # Lines should show FLIPPED evals
    assert verdict["lines"][0]["eval_cp"] == -300, (
        f"Expected -300 for black mover, got {verdict['lines'][0]['eval_cp']}"
    )
    assert verdict["lines"][1]["eval_cp"] == -250

    # Played line eval should also be flipped
    assert verdict["played"]["eval_cp"] == -300


# ------------------------------------------------------------------
# Test 4 — Mock-safe: empty engine returns error, no cache write
# ------------------------------------------------------------------

def test_mock_engine_returns_error_no_cache():
    """Stub returns empty best_moves → critical_lines returns
    {"error": "engine_unavailable"} and writes NOTHING to the cache.
    Mutation: fails if the error path caches or returns a verdict.
    """
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    engine = EmptyEngine()

    result = asyncio.run(
        critical_points.critical_lines(
            fen, "e2e4", "white", engine, multipv=4, nodes=4000
        )
    )

    assert result.get("error") == "engine_unavailable", (
        f"Expected error='engine_unavailable', got {result}"
    )

    # Must NOT have cached
    epd = chess.Board(fen).epd()
    cache = store.EpdCache("critical_lines")
    assert cache.get(epd) is None, "Mock engine result must NOT be cached"

    # Engine was invoked only once (the multipv call), not the played-move call
    assert engine.call_count == 1
