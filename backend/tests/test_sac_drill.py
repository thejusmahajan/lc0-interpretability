import os
import json
import pytest
from fastapi.testclient import TestClient

from backend.training import store, sac_drill
from backend.app import app


@pytest.fixture
def sac_env(tmp_path, monkeypatch):
    """Fixture that sets up a temporary TRAINING_DIR with a synthetic profile containing steer_findings."""
    training_dir = str(tmp_path / "training")
    monkeypatch.setattr(store, "TRAINING_DIR", training_dir)
    store._ensure_dirs()

    # Synthetic profile with 4 steer_findings:
    # 1. had_sharp_move=True, complexity=4.5 -> ELIGIBLE
    # 2. had_sharp_move=False, complexity=5.0 -> EXCLUDED (no sharp move)
    # 3. had_sharp_move=True, complexity=2.0 -> ELIGIBLE
    # 4. Duplicate EPD of #1, complexity=3.0 -> EXCLUDED (duplicate board EPD)
    mock_profile = {
        "player_name": "TestPlayer",
        "steer_findings": [
            {
                "id": "s-001-p020",
                "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
                "best": {"uci": "f1b5", "san": "Bb5", "eval_cp": 30, "complexity": 1.2},
                "steer": {"uci": "d2d4", "san": "d4", "eval_cp": 15, "complexity": 4.5},
                "playable_candidates": [
                    {"uci": "d2d4", "complexity": 4.5, "eval_cp": 15},
                    {"uci": "c2c3", "complexity": 2.1, "eval_cp": 25},
                ],
                "eval_loss_cp": 15,
                "had_sharp_move": True,
                "opening": {"eco": "D02", "name": "London System"},
            },
            {
                "id": "s-002-p015",
                "fen_before": "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
                "best": {"uci": "b8c6", "san": "Nc6", "eval_cp": 0, "complexity": 0.8},
                "steer": {"uci": "b8c6", "san": "Nc6", "eval_cp": 0, "complexity": 0.8},
                "playable_candidates": [{"uci": "b8c6", "complexity": 0.8, "eval_cp": 0}],
                "eval_loss_cp": 0,
                "had_sharp_move": False,
                "opening": {"eco": "D02", "name": "London System"},
            },
            {
                "id": "s-003-p030",
                "fen_before": "r1bq1rk1/pp3pb1/2n3pp/2ppn3/5B2/2P1PN1P/PPBN1PP1/R2Q1RK1 w - - 0 12",
                "best": {"uci": "f3e5", "san": "Nxe5", "eval_cp": 50, "complexity": 1.0},
                "steer": {"uci": "f4h6", "san": "Bxh6", "eval_cp": -20, "complexity": 2.0},
                "playable_candidates": [
                    {"uci": "f4h6", "complexity": 2.0, "eval_cp": -20},
                    {"uci": "f3e5", "complexity": 1.0, "eval_cp": 50},
                ],
                "eval_loss_cp": 70,
                "had_sharp_move": True,
                "opening": {"eco": "C44", "name": "King's Pawn Game"},
            },
            {
                "id": "s-004-p020",
                "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",  # Same EPD as s-001
                "best": {"uci": "f1c4", "san": "Bc4", "eval_cp": 20, "complexity": 1.0},
                "steer": {"uci": "b1c3", "san": "Nc3", "eval_cp": 10, "complexity": 3.0},
                "playable_candidates": [{"uci": "b1c3", "complexity": 3.0, "eval_cp": 10}],
                "eval_loss_cp": 10,
                "had_sharp_move": True,
            },
        ],
    }

    store.save_profile(mock_profile)
    return training_dir, mock_profile


def test_selection_filters_had_sharp_move_and_dedupes(sac_env):
    """Verify build_sac_session includes ONLY had_sharp_move=True and dedupes by board EPD."""
    session = sac_drill.build_sac_session(count=10)
    assert len(session) == 2  # s-001 (comp=4.5) and s-003 (comp=2.0)

    ids = [item["id"] for item in session]

    # Included: s-001 and s-003
    assert "s-001-p020" in ids
    assert "s-003-p030" in ids

    # Excluded: s-002 (had_sharp_move=False) and s-004 (duplicate EPD of s-001)
    assert "s-002-p015" not in ids
    assert "s-004-p020" not in ids


def test_session_payload_no_answers_leaked(sac_env):
    """Verify session payload contains id and fen ONLY (no steer, best, or eval info)."""
    session = sac_drill.build_sac_session(count=5)
    for item in session:
        assert "id" in item
        assert "fen" in item
        assert "steer" not in item
        assert "best" not in item
        assert "eval_loss_cp" not in item
        assert "playable_candidates" not in item


def test_score_sac_guess_correct_and_acceptable(sac_env):
    """Verify scoring logic: correct=True for sac move, acceptable=True for sound alt."""
    finding_id = "s-001-p020"

    # 1. Correct guess: sac move "d2d4"
    res_sac = sac_drill.score_sac_guess(finding_id, "d2d4")
    assert res_sac["correct"] is True
    assert res_sac["acceptable"] is False
    assert res_sac["sac_move"]["uci"] == "d2d4"
    assert res_sac["sac_move"]["san"] == "d4"
    assert res_sac["safe_move"]["san"] == "Bb5"
    assert res_sac["eval_loss_cp"] == 15

    # 2. Acceptable guess: sound alt "c2c3" (in playable_candidates, but not sac)
    res_alt = sac_drill.score_sac_guess(finding_id, "c2c3")
    assert res_alt["correct"] is False
    assert res_alt["acceptable"] is True
    assert res_alt["sac_move"]["uci"] == "d2d4"

    # 3. Miss guess: "a2a3" (not in playable_candidates)
    res_miss = sac_drill.score_sac_guess(finding_id, "a2a3")
    assert res_miss["correct"] is False
    assert res_miss["acceptable"] is False


def test_unknown_finding_id_returns_empty(sac_env):
    """Verify unknown finding_id returns empty dict {}."""
    res = sac_drill.score_sac_guess("unknown-id-123", "d2d4")
    assert res == {}


def test_stats_accuracy_logging(sac_env):
    """Verify get_stats tracks total, correct, acceptable, and accuracy."""
    # Initial stats should be empty
    s0 = sac_drill.get_stats()
    assert s0["total"] == 0
    assert s0["correct"] == 0
    assert s0["acceptable"] == 0
    assert s0["accuracy"] == 0.0

    # Log 3 guesses: 1 correct, 1 acceptable, 1 miss
    sac_drill.score_sac_guess("s-001-p020", "d2d4")  # Correct
    sac_drill.score_sac_guess("s-001-p020", "c2c3")  # Acceptable
    sac_drill.score_sac_guess("s-001-p020", "a2a3")  # Miss

    s1 = sac_drill.get_stats()
    assert s1["total"] == 3
    assert s1["correct"] == 1
    assert s1["acceptable"] == 1
    assert s1["accuracy"] == 0.3333
    assert s1["recent_accuracy"] == 0.3333


def test_api_endpoints_integration(sac_env):
    """Integration test for /sac/session, /sac/guess, /sac/stats FastAPI endpoints."""
    client = TestClient(app)

    # 1. POST /api/training/sac/session
    res_session = client.post("/api/training/sac/session", json={"count": 5})
    assert res_session.status_code == 200
    items = res_session.json()
    assert isinstance(items, list)
    assert len(items) == 2

    finding_id = items[0]["id"]

    # 2. POST /api/training/sac/guess
    res_guess = client.post("/api/training/sac/guess", json={"finding_id": finding_id, "uci": "d2d4"})
    assert res_guess.status_code == 200
    guess_data = res_guess.json()
    assert "correct" in guess_data
    assert "sac_move" in guess_data
    assert "safe_move" in guess_data

    # 3. GET /api/training/sac/stats
    res_stats = client.get("/api/training/sac/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total"] == 1

    # 4. Unknown finding_id -> 404
    res_404 = client.post("/api/training/sac/guess", json={"finding_id": "nonexistent", "uci": "e2e4"})
    assert res_404.status_code == 404


def test_sac_session_filtered_by_eco(sac_env):
    """Mutation check: eco='D02' returns ONLY D02 sacrifices."""
    session_d02 = sac_drill.build_sac_session(count=10, eco="D02")
    assert len(session_d02) == 1
    assert session_d02[0]["id"] == "s-001-p020"

    # API endpoint test with eco
    client = TestClient(app)
    res = client.post("/api/training/sac/session", json={"count": 10, "eco": "C44"})
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == "s-003-p030"

