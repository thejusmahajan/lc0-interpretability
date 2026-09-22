"""Tests for puzzle_sets module: streak ordering, sessions, convention guard, and move validation."""

import os
import chess
import pytest

from backend.training import puzzle_regime, puzzle_sets, store


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Ensure all tests operate within a temporary directory and never touch data/puzzles/regime/."""
    regime_dir = tmp_path / "regime"
    sets_dir = regime_dir / "sets"
    sessions_dir = regime_dir / "sessions"
    sets_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(puzzle_sets, "REGIME_DIR", str(regime_dir))
    monkeypatch.setattr(puzzle_sets, "SETS_DIR", str(sets_dir))
    monkeypatch.setattr(puzzle_sets, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(puzzle_regime, "REGIME_DIR", str(regime_dir))
    monkeypatch.setattr(puzzle_regime, "DECKS_DIR", str(regime_dir / "decks"))


def test_streak_order_non_decreasing_buckets():
    """streak_order must bucket into 50-point bins and concatenate in ascending order."""
    puzzles = [
        {"id": "p1", "rating": 1980},
        {"id": "p2", "rating": 1510},
        {"id": "p3", "rating": 1620},
        {"id": "p4", "rating": 1540},
        {"id": "p5", "rating": 1600},
        {"id": "p6", "rating": 1950},
        {"id": "p7", "rating": 1750},
        {"id": "p8", "rating": 1820},
        {"id": "p9", "rating": 1500},
        {"id": "p10", "rating": 1790},
    ]
    ordered = puzzle_sets.streak_order(puzzles, seed=42)
    assert len(ordered) == len(puzzles)
    assert {p["id"] for p in ordered} == {p["id"] for p in puzzles}

    ratings = [p["rating"] for p in ordered]
    buckets = [r // 50 for r in ratings]
    assert all(b1 <= b2 for b1, b2 in zip(buckets, buckets[1:]))


def test_streak_order_seed_reshuffle_preserves_monotonicity():
    """Different seeds must randomize tied ratings, while both strictly preserve monotonicity."""
    puzzles = []
    for b in range(30, 40):  # 1500 to 1999 in 50-point bins
        for i in range(5):
            puzzles.append({"id": f"p_{b}_{i}", "rating": b * 50})

    order1 = puzzle_sets.streak_order(puzzles, seed=1)
    order2 = puzzle_sets.streak_order(puzzles, seed=2)

    ids1 = [p["id"] for p in order1]
    ids2 = [p["id"] for p in order2]
    assert ids1 != ids2, "Different seeds must produce different tie-breakings for equal ratings"

    ratings1 = [p["rating"] for p in order1]
    ratings2 = [p["rating"] for p in order2]
    assert all(r1 <= r2 for r1, r2 in zip(ratings1, ratings1[1:]))
    assert all(r1 <= r2 for r1, r2 in zip(ratings2, ratings2[1:]))


def _create_mock_set(set_id: str, puzzle_rows: list[dict]) -> dict:
    os.makedirs(puzzle_sets.SETS_DIR, exist_ok=True)
    deck = {
        "id": set_id,
        "name": set_id,
        "min_rating": 1500,
        "max_rating": 2000,
        "themes": [],
        "size": len(puzzle_rows),
        "created": "2026-08-15T00:00:00",
        "puzzles": puzzle_rows,
    }
    store._write_json_atomic(os.path.join(puzzle_sets.SETS_DIR, f"{set_id}.json"), deck)
    return deck


def test_full_correct_playthrough_solves_and_increments_streak():
    """A full correct playthrough of a multi-move puzzle solves it and increments streak."""
    # Puzzle 013Jo: moves are e3e4 (blunder), f6f4 (solver), e4f4 (reply), f8f4 (solver)
    row = {
        "id": "013Jo",
        "fen": "rnb2rk1/ppp3pp/3bpq2/4N3/2BPpB2/4Q3/PPP2PPP/R3K2R w KQ - 2 12",
        "moves": "e3e4 f6f4 e4f4 f8f4",
        "rating": 1500,
        "popularity": 94,
        "themes": "advantage middlegame short",
    }
    _create_mock_set("test-multi", [row])

    sess = puzzle_sets.start_session("test-multi", seed=1)
    session_id = sess["id"]

    assert sess["streak"] == 0
    assert sess["alive"] is True
    assert sess["index"] == 0

    # First solver move
    res1 = puzzle_sets.submit_move(session_id, "f6f4")
    assert res1["correct"] is True
    assert res1["solved"] is False
    assert res1["opponent_uci"] == "e4f4"
    assert res1["ply"] == 2
    assert res1["alive"] is True

    # Second and final solver move
    res2 = puzzle_sets.submit_move(session_id, "f8f4")
    assert res2["correct"] is True
    assert res2["solved"] is True
    assert res2["streak"] == 1
    assert res2["best_streak"] == 1
    assert res2["alive"] is True


def test_session_size_varies_content_but_never_the_difficulty_ramp(monkeypatch):
    """Variety must come from which puzzles are drawn, never from the ordering.

    Ordering stays strictly ascending; two sessions of the same set should
    still differ in content. Uses the stored-puzzle fallback path so the test
    does not depend on the puzzle database being present.
    """
    rows = [
        {"id": f"p{i}", "rating": 1500 + i * 7,
         "fen": "rnb2rk1/ppp3pp/3bpq2/4N3/2BPpB2/4Q3/PPP2PPP/R3K2R w KQ - 2 12",
         "moves": "e3e4 f6f4 e4f4 f8f4", "popularity": 90, "themes": "middlegame"}
        for i in range(60)
    ]
    _create_mock_set("test-pool", rows)

    # Keep the test off the real puzzle database: force the stored-puzzle
    # fallback, and serve row lookups from these synthetic rows.
    by_id = {r["id"]: r for r in rows}
    monkeypatch.setattr(puzzle_sets, "draw_from_pool", lambda *a, **k: [])
    monkeypatch.setattr(puzzle_sets, "_rows_for",
                        lambda ids: [by_id[i] for i in ids if i in by_id])

    a = puzzle_sets.start_session("test-pool", seed=1, session_size=20)
    b = puzzle_sets.start_session("test-pool", seed=2, session_size=20)

    assert len(a["order"]) == 20 and len(b["order"]) == 20
    assert a["order"] != b["order"], "different seeds must draw different puzzles"

    for sess in (a, b):
        ratings = [by_id[pid]["rating"] for pid in sess["order"]]
        assert all(x <= y for x, y in zip(ratings, ratings[1:])), \
            "difficulty must never step backwards within a session"


def test_orientation_is_fixed_for_the_whole_puzzle():
    """Orientation must not follow the live board turn.

    Regression: it was derived from board.turn, so the final solver move — which
    hands the turn to the opponent — flipped the board at the instant the puzzle
    was solved. 013Jo is black-to-move, which makes the flip visible.
    """
    row = {
        "id": "013Jo",
        "fen": "rnb2rk1/ppp3pp/3bpq2/4N3/2BPpB2/4Q3/PPP2PPP/R3K2R w KQ - 2 12",
        "moves": "e3e4 f6f4 e4f4 f8f4",
        "rating": 1500,
        "popularity": 94,
        "themes": "advantage middlegame short",
    }
    _create_mock_set("test-orient", [row])

    sess = puzzle_sets.start_session("test-orient", seed=1)
    session_id = sess["id"]
    assert sess["orientation"] == "black"

    mid = puzzle_sets.submit_move(session_id, "f6f4")
    assert mid["orientation"] == "black"

    solved = puzzle_sets.submit_move(session_id, "f8f4")
    assert solved["solved"] is True
    assert solved["orientation"] == "black"


def test_wrong_move_ends_streak_and_returns_solution():
    """A wrong move sets alive: False, records streak end, and returns the full solution SAN."""
    row = {
        "id": "013Jo",
        "fen": "rnb2rk1/ppp3pp/3bpq2/4N3/2BPpB2/4Q3/PPP2PPP/R3K2R w KQ - 2 12",
        "moves": "e3e4 f6f4 e4f4 f8f4",
        "rating": 1500,
        "popularity": 94,
        "themes": "advantage middlegame short",
    }
    _create_mock_set("test-wrong", [row])

    sess = puzzle_sets.start_session("test-wrong", seed=1)
    session_id = sess["id"]

    # Submit illegal or incorrect move
    res = puzzle_sets.submit_move(session_id, "a7a6")
    assert res["correct"] is False
    assert res["solved"] is False
    assert res["alive"] is False
    assert res["streak_ended_at"] == 0
    assert res["solution"] == ["f6f4", "e4f4", "f8f4"]
    assert isinstance(res["solution_san"], str)
    assert len(res["solution_san"]) > 0


def test_convention_guard_off_by_one_ply_trap():
    """Regression test: puzzle_position(row) applies blunder and returns solver to move with moves[1]."""
    row = {
        "id": "013Jo",
        "fen": "rnb2rk1/ppp3pp/3bpq2/4N3/2BPpB2/4Q3/PPP2PPP/R3K2R w KQ - 2 12",
        "moves": "e3e4 f6f4 e4f4 f8f4",
        "rating": 1500,
    }
    raw_board = chess.Board(row["fen"])
    assert raw_board.turn == chess.WHITE, "Position before blunder is White to move"

    board, solution = puzzle_regime.puzzle_position(row)
    assert board.turn == chess.BLACK, "Solver must be Black to move after blunder"
    assert solution[0] == "f6f4"
    assert solution[0] == row["moves"].split()[1], "First solver move must equal moves[1]"


def test_promotion_suffix_required():
    """Submitting promotion move requires the piece suffix (...q); bare move is rejected."""
    # Puzzle 005jR: White plays g1f2 (blunder), Black solver plays b2b1q
    row = {
        "id": "005jR",
        "fen": "8/5p1k/1P4pp/3Qn3/4BP2/6P1/1p2P2P/2q3K1 w - - 1 34",
        "moves": "g1f2 b2b1q e4b1 e5g4 f2f3 c1h1",
        "rating": 2785,
        "themes": "advancedPawn crushing endgame long promotion",
    }
    _create_mock_set("test-promo", [row])

    # Test bare move without suffix
    sess1 = puzzle_sets.start_session("test-promo", seed=1)
    res_bare = puzzle_sets.submit_move(sess1["id"], "b2b1")
    assert res_bare["correct"] is False
    assert res_bare["alive"] is False

    # Test full move with promotion suffix
    sess2 = puzzle_sets.start_session("test-promo", seed=2)
    res_promo = puzzle_sets.submit_move(sess2["id"], "b2b1q")
    assert res_promo["correct"] is True
    assert res_promo["alive"] is True
