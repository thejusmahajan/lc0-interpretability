import os
import json
import pytest
from fastapi.testclient import TestClient

from backend.training import store, intuition
from backend.app import app


@pytest.fixture
def intuition_env(tmp_path, monkeypatch):
    """Fixture that sets up a clean temporary TRAINING_DIR with a synthetic policy cache."""
    training_dir = str(tmp_path / "training")
    monkeypatch.setattr(store, "TRAINING_DIR", training_dir)
    store._ensure_dirs()

    # Create synthetic policy cache with 4 positions:
    # 1. Normal position (top p = 0.45, 3 moves) -> ELIGIBLE
    # 2. Near-forced position (top p = 0.95, 2 moves) -> EXCLUDED (top p >= 0.9)
    # 3. Single-move position (top p = 0.50, 1 move) -> EXCLUDED (len(policy) < 2)
    # 4. Another normal position (top p = 0.60, 4 moves) -> ELIGIBLE
    cache_file = os.path.join(training_dir, "cache", "policy.jsonl")

    records = [
        {
            "epd": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -",
            "policy": [
                {"uci": "e7e5", "san": "e5", "from": "e7", "to": "e5", "p": 0.45},
                {"uci": "c7c5", "san": "c5", "from": "c7", "to": "c5", "p": 0.35},
                {"uci": "e7e6", "san": "e6", "from": "e7", "to": "e6", "p": 0.20},
            ],
        },
        {
            "epd": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -",
            "policy": [
                {"uci": "f1b5", "san": "Bb5", "from": "f1", "to": "b5", "p": 0.95},
                {"uci": "d2d4", "san": "d4", "from": "d2", "to": "d4", "p": 0.05},
            ],
        },
        {
            "epd": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -",
            "policy": [
                {"uci": "e2e4", "san": "e4", "from": "e2", "to": "e4", "p": 0.50},
            ],
        },
        {
            "epd": "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -",
            "policy": [
                {"uci": "e4d5", "san": "exd5", "from": "e4", "to": "d5", "p": 0.60},
                {"uci": "e4e5", "san": "e5", "from": "e4", "to": "e5", "p": 0.25},
                {"uci": "b1c3", "san": "Nc3", "from": "b1", "to": "c3", "p": 0.10},
                {"uci": "d2d4", "san": "d4", "from": "d2", "to": "d4", "p": 0.05},
            ],
        },
    ]

    with open(cache_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    return training_dir, records


def test_epd_cache_keys(intuition_env):
    """Verify EpdCache.keys() returns all loaded EPD keys."""
    cache = store.EpdCache("policy")
    keys = cache.keys()
    assert len(keys) == 4
    assert "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -" in keys


def test_sampling_filters_forced_and_single(intuition_env):
    """Verify sampling excludes near-forced (top p >= 0.9) and single-move positions."""
    session = intuition.build_session(count=10)
    # Only records #1 and #4 are eligible
    assert len(session) == 2
    epds = [item["epd"] for item in session]

    # Excluded: #2 (p=0.95) and #3 (len=1)
    assert "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -" not in epds
    assert "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -" not in epds

    # Included: #1 and #4
    assert "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -" in epds
    assert "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -" in epds


def test_build_session_does_not_leak_answers(intuition_env):
    """Verify build_session returns fen and epd only, and no policy/solution info."""
    session = intuition.build_session(count=5)
    for item in session:
        assert "epd" in item
        assert "fen" in item
        assert "policy" not in item
        assert "top_move" not in item
        assert "solution" not in item
        # Ensure FEN is valid reconstructed string
        assert isinstance(item["fen"], str) and len(item["fen"]) > 10


def test_score_guess_top1_match_and_rank(intuition_env):
    """Verify score_guess logic: correct=True only for top move, rank calculation."""
    epd = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -"

    # 1. Correct guess (top-1 match: e7e5)
    res_top = intuition.score_guess(epd, "e7e5")
    assert res_top["correct"] is True
    assert res_top["rank"] == 1
    assert res_top["your_move"]["uci"] == "e7e5"
    assert res_top["your_move"]["p"] == 0.45
    assert res_top["top_move"]["uci"] == "e7e5"
    assert len(res_top["top_policy"]) == 3

    # 2. Ranked second guess (c7c5)
    res_second = intuition.score_guess(epd, "c7c5")
    assert res_second["correct"] is False
    assert res_second["rank"] == 2
    assert res_second["your_move"]["uci"] == "c7c5"
    assert res_second["your_move"]["p"] == 0.35
    assert res_second["top_move"]["uci"] == "e7e5"

    # 3. Off-list move (a7a6 - not in top 20)
    res_off = intuition.score_guess(epd, "a7a6")
    assert res_off["correct"] is False
    assert res_off["rank"] is None
    assert res_off["your_move"] is None
    assert res_off["top_move"]["uci"] == "e7e5"


def test_stats_accuracy_logging(intuition_env):
    """Verify get_stats computes total, correct, accuracy, and recent_accuracy."""
    epd = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -"

    # Initial stats should be zeros
    s0 = intuition.get_stats()
    assert s0["total"] == 0
    assert s0["correct"] == 0
    assert s0["accuracy"] == 0.0

    # Log 3 guesses: 2 correct, 1 wrong
    intuition.score_guess(epd, "e7e5")  # Correct
    intuition.score_guess(epd, "c7c5")  # Wrong
    intuition.score_guess(epd, "e7e5")  # Correct

    s1 = intuition.get_stats()
    assert s1["total"] == 3
    assert s1["correct"] == 2
    assert s1["accuracy"] == 0.6667
    assert s1["recent_accuracy"] == 0.6667


def test_api_endpoints_integration(intuition_env):
    """Integration test for /session, /guess, /stats FastAPI endpoints."""
    client = TestClient(app)

    # 1. POST /api/training/intuition/session
    res_session = client.post("/api/training/intuition/session", json={"count": 5})
    assert res_session.status_code == 200
    items = res_session.json()
    assert isinstance(items, list)
    assert len(items) == 2

    epd = items[0]["epd"]

    # 2. POST /api/training/intuition/guess
    res_guess = client.post("/api/training/intuition/guess", json={"epd": epd, "uci": "e7e5"})
    assert res_guess.status_code == 200
    guess_data = res_guess.json()
    assert "correct" in guess_data
    assert "top_policy" in guess_data

    # 3. GET /api/training/intuition/stats
    res_stats = client.get("/api/training/intuition/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total"] == 1
