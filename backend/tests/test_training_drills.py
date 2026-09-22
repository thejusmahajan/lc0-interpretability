"""Attempt judging: Lichess-style line walking in drills.check_attempt.

The stored line must be followed move by move; the drill completes only at
the end of the line; any checkmate wins immediately; ply-0 engine
alternatives count as correct (and end the drill, since they leave the line).
"""

import pytest

from backend.training import drills

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def make_drill(**overrides):
    d = {
        "id": "d-test",
        "fen": START,
        "setup_move_uci": "e2e4",
        "solution_uci": "e7e5",
        "line_uci": ["e7e5", "g1f3", "b8c6"],
        "alt_solution_ucis": [],
    }
    d.update(overrides)
    return d


def test_first_move_correct_returns_reply_not_complete():
    v = drills.check_attempt(make_drill(), 0, "e7e5")
    assert v == {"correct": True, "complete": False, "reply_uci": "g1f3"}


def test_last_move_completes_line():
    v = drills.check_attempt(make_drill(), 2, "b8c6")
    assert v == {"correct": True, "complete": True, "reply_uci": None}


def test_wrong_move_fails():
    v = drills.check_attempt(make_drill(), 0, "a7a6")
    assert v == {"correct": False, "complete": False, "reply_uci": None}


def test_wrong_move_mid_line_fails():
    v = drills.check_attempt(make_drill(), 2, "g8f6")
    assert v == {"correct": False, "complete": False, "reply_uci": None}


@pytest.mark.parametrize("ply", [-2, 1, 3, 4])
def test_ply_must_address_a_user_move(ply):
    with pytest.raises(ValueError):
        drills.check_attempt(make_drill(), ply, "e7e5")


def test_legacy_drill_without_line_is_single_move():
    d = make_drill(setup_move_uci=None, solution_uci="e2e4")
    del d["line_uci"]
    assert drills.check_attempt(d, 0, "e2e4") == {
        "correct": True, "complete": True, "reply_uci": None}


def test_alt_solution_at_ply0_completes_off_line():
    d = make_drill(alt_solution_ucis=["d7d5"])
    v = drills.check_attempt(d, 0, "d7d5")
    assert v == {"correct": True, "complete": True, "reply_uci": None}


def test_alt_solutions_not_accepted_mid_line():
    d = make_drill(alt_solution_ucis=["g8f6"])
    v = drills.check_attempt(d, 2, "g8f6")
    assert v["correct"] is False


def test_promotion_move_accepted():
    d = make_drill(fen="8/6P1/8/8/8/1k6/8/1K6 w - - 0 1",
                   setup_move_uci=None,
                   solution_uci="g7g8q", line_uci=["g7g8q"])
    v = drills.check_attempt(d, 0, "g7g8q")
    assert v == {"correct": True, "complete": True, "reply_uci": None}
    # A promotion UCI without the piece letter is not a legal move and
    # must be judged incorrect, not crash the endpoint.
    v = drills.check_attempt(d, 0, "g7g8")
    assert v["correct"] is False


def test_any_checkmate_wins_immediately():
    # Scholar's mate position: stored line says d2d3, but Qxf7# is mate.
    fen = ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/"
           "RNB1K1NR w KQkq - 0 4")
    d = make_drill(fen=fen, setup_move_uci=None,
                   solution_uci="d2d3", line_uci=["d2d3"])
    v = drills.check_attempt(d, 0, "f3f7")
    assert v == {"correct": True, "complete": True, "reply_uci": None}


@pytest.mark.anyio
async def test_generated_steer_drill_carries_and_accepts_bounded_alt(monkeypatch, tmp_path):
    """End-to-end steer-drill path: generate_drill_set turns a had_tal_move
    steer finding into a source='steer' drill whose alt_solution_ucis include
    the finding's bounded-sharp playable candidates, and check_attempt then
    accepts one of those alts at the decision ply.

    check_attempt has no steer-specific branch, so acceptance rides the generic
    ply-0 alt path (covered by test_alt_solution_at_ply0_completes_off_line).
    The new coverage here is the GENERATION step attaching the bounded alts --
    which is what 'steer drill accepts a bounded alt' actually depends on.
    """
    from backend.training import store, puzzle_db

    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    # This unit exercises only the steer branch; keep the corpus branch inert.
    monkeypatch.setattr(puzzle_db, "sample_puzzles", lambda *a, **k: [])

    # Black to move after 1.e4 e5 2.Nf3: Nf6 (steer/sharp), Nc6 (best), d6 (a
    # bounded-sharp sideline) are all legal.
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    profile = {
        "steer_findings": [{
            "id": "s-000-p003",
            "fen_before": fen,
            "had_sharp_move": True,
            "best": {"uci": "b8c6", "san": "Nc6", "eval_cp": 20, "complexity": 0.2, "components": {}},
            "steer": {"uci": "g8f6", "san": "Nf6", "eval_cp": 10, "complexity": 0.8, "components": {}},
            "playable_candidates": [
                {"uci": "g8f6", "complexity": 0.8, "eval_cp": 10},
                {"uci": "d7d6", "complexity": 0.5, "eval_cp": 5},
            ],
            "opening": {"eco": "C20"},
        }],
        "findings": [],
    }

    drill_set = await drills.generate_drill_set(
        count=1, profile=profile, repertoire={}, engine=None, vision=None, steer_weight=1.0)

    steer_drills = [d for d in drill_set["drills"] if d["source"] == "steer"]
    assert len(steer_drills) == 1
    d = steer_drills[0]

    # generation attached the bounded-sharp sideline as an accepted alt
    assert "d7d6" in d["alt_solution_ucis"]

    # and check_attempt accepts that bounded alt at the decision ply
    v = drills.check_attempt(d, 0, "d7d6")
    assert v == {"correct": True, "complete": True, "reply_uci": None}
