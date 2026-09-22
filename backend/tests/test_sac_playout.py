import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

from backend.training import store, sac_drill
from backend.app import app, lc0_engine


@pytest.fixture
def sac_playout_env(tmp_path, monkeypatch):
    """Fixture that sets up synthetic profile with WHITE and BLACK attacker steer findings."""
    training_dir = str(tmp_path / "training")
    monkeypatch.setattr(store, "TRAINING_DIR", training_dir)
    store._ensure_dirs()

    # White attacker position: White plays sac d2d4
    # fen_before = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3"
    
    # Black attacker position: Black plays sac c7c5
    # fen_before = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"

    mock_profile = {
        "player_name": "TestPlayer",
        "steer_findings": [
            {
                "id": "s-white-001",
                "fen_before": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
                "best": {"uci": "f1b5", "san": "Bb5", "eval_cp": 30},
                "steer": {"uci": "d2d4", "san": "d4", "eval_cp": 15},
                "had_sharp_move": True,
            },
            {
                "id": "s-black-001",
                "fen_before": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
                "best": {"uci": "e7e5", "san": "e5", "eval_cp": 0},
                "steer": {"uci": "c7c5", "san": "c5", "eval_cp": -20},
                "had_sharp_move": True,
            },
        ],
    }

    store.save_profile(mock_profile)
    return training_dir, mock_profile


def test_black_attacker_pov_conversion(sac_playout_env, monkeypatch):
    """Verify BLACK-attacker position converts negative white-POV eval to positive attacker-POV eval."""
    client = TestClient(app)

    monkeypatch.setattr(lc0_engine, "is_available", lambda: True)

    async def mock_analyze(fen, nodes=None):
        # Return negative white-cp (e.g. -150 white-cp => Black is up +150)
        return {
            "evaluation": -150,
            "best_moves": ["g1f3"],
            "pv_lines": [["g1f3"]],
            "nodes": 4000,
            "wdl": [0.1, 0.2, 0.7],
        }

    monkeypatch.setattr(lc0_engine, "analyze", AsyncMock(side_effect=mock_analyze))

    res = client.post("/api/training/sac/playout/start", json={"finding_id": "s-black-001"})
    assert res.status_code == 200
    data = res.json()

    assert data["attacker_is_white"] is False
    # White eval -150 => Attacker (Black) eval +150
    assert data["attacker_eval_cp"] == 150
    assert data["ply"] == 2
    assert "best_moves" not in data
    assert "lc0_best_attack" not in data


def test_start_does_not_leak_best_attacking_move(sac_playout_env, monkeypatch):
    """Verify start endpoint returns position after LC0 defense and does NOT leak best attacking move."""
    client = TestClient(app)

    monkeypatch.setattr(lc0_engine, "is_available", lambda: True)

    async def mock_analyze(fen, nodes=None):
        return {
            "evaluation": 50,
            "best_moves": ["e5d4"],
            "pv_lines": [["e5d4"]],
            "nodes": 4000,
            "wdl": [0.6, 0.3, 0.1],
        }

    monkeypatch.setattr(lc0_engine, "analyze", AsyncMock(side_effect=mock_analyze))

    res = client.post("/api/training/sac/playout/start", json={"finding_id": "s-white-001"})
    assert res.status_code == 200
    data = res.json()

    assert data["finding_id"] == "s-white-001"
    assert data["attacker_is_white"] is True
    assert data["line"] == ["d2d4", "e5d4"]
    assert data["ply"] == 2
    assert data["user_to_move"] is True
    assert "lc0_best_attack" not in data
    assert "best_moves" not in data


def test_judging_thresholds_great_ok_drift(sac_playout_env, monkeypatch):
    """Verify move quality classification for great (drop <= 30), ok (drop <= 100), drift (drop > 100)."""
    client = TestClient(app)

    monkeypatch.setattr(lc0_engine, "is_available", lambda: True)

    eval_sequence = [
        {"evaluation": 100, "best_moves": ["f3d4"]},  # 1. Pre-user analyze (pre-move best is f3d4, eval 100)
        {"evaluation": 80, "best_moves": ["c6d4"]},   # 2. Post-user analyze for move 1 (drop = 20 <= 30 -> GREAT)
        {"evaluation": 80, "best_moves": ["f3d4"]},   # 3. Post-reply analyze for move 1
    ]
    call_idx = [0]

    async def mock_analyze(fen, nodes=None):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx < len(eval_sequence):
            return eval_sequence[idx]
        return {"evaluation": 50, "best_moves": ["a2a3"]}

    monkeypatch.setattr(lc0_engine, "analyze", AsyncMock(side_effect=mock_analyze))

    # Test move 1: User plays f3d4 (exact match / small drop) -> GREAT
    res1 = client.post(
        "/api/training/sac/playout/move",
        json={"finding_id": "s-white-001", "line": ["d2d4", "e5d4"], "user_uci": "f3d4"},
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["quality"] == "great"
    assert d1["lc0_best_attack"]["uci"] == "f3d4"

    # Test move 2: drop = 50 (100 -> 50) -> OK
    call_idx[0] = 0
    eval_sequence = [
        {"evaluation": 100, "best_moves": ["f3d4"]},
        {"evaluation": 50, "best_moves": ["c6d4"]},
        {"evaluation": 50, "best_moves": ["f3d4"]},
    ]
    res2 = client.post(
        "/api/training/sac/playout/move",
        json={"finding_id": "s-white-001", "line": ["d2d4", "e5d4"], "user_uci": "c2c3"},
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["quality"] == "ok"

    # Test move 3: drop = 150 (100 -> -50) -> DRIFT
    call_idx[0] = 0
    eval_sequence = [
        {"evaluation": 100, "best_moves": ["f3d4"]},
        {"evaluation": -50, "best_moves": ["c6d4"]},
        {"evaluation": -50, "best_moves": ["f3d4"]},
    ]
    res3 = client.post(
        "/api/training/sac/playout/move",
        json={"finding_id": "s-white-001", "line": ["d2d4", "e5d4"], "user_uci": "c2c3"},
    )
    assert res3.status_code == 200
    d3 = res3.json()
    assert d3["quality"] == "drift"


def test_is_complete_at_target_plies_and_summary(sac_playout_env, monkeypatch):
    """Verify is_complete fires when target plies reached and computes summary dict."""
    client = TestClient(app)

    monkeypatch.setattr(lc0_engine, "is_available", lambda: True)

    async def mock_analyze(fen, nodes=None):
        move = "f1c4" if " w " in fen else "d7d6"
        return {"evaluation": 150, "best_moves": [move]}

    monkeypatch.setattr(lc0_engine, "analyze", AsyncMock(side_effect=mock_analyze))

    # Line of 6 plies already played; adding user_uci + reply hits target_plies (8)
    line_6_plies = ["d2d4", "e5d4", "f3d4", "c6d4", "d1d4", "g8f6"]
    res = client.post(
        "/api/training/sac/playout/move",
        json={
            "finding_id": "s-white-001",
            "line": line_6_plies,
            "user_uci": "f1c4",
            "history": ["great", "great"],
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert data["is_complete"] is True
    assert "summary" in data
    summary = data["summary"]
    assert summary["moves"] == 3
    assert summary["great"] == 3
    assert summary["ok"] == 0
    assert summary["drift"] == 0
    assert summary["final_eval_cp"] == 150
    assert "kept the attack" in summary["verdict"]


def test_illegal_user_move_returns_400(sac_playout_env, monkeypatch):
    """Verify illegal UCI move returns HTTP 400 status code."""
    client = TestClient(app)

    monkeypatch.setattr(lc0_engine, "is_available", lambda: True)

    res = client.post(
        "/api/training/sac/playout/move",
        json={"finding_id": "s-white-001", "line": ["d2d4", "e5d4"], "user_uci": "e1g1"},  # King castling illegal here
    )
    assert res.status_code == 400


def test_engine_unavailable_returns_error_dict(sac_playout_env, monkeypatch):
    """Verify start and move endpoints return error dict when engine is unavailable."""
    client = TestClient(app)

    monkeypatch.setattr(lc0_engine, "is_available", lambda: False)

    res_start = client.post("/api/training/sac/playout/start", json={"finding_id": "s-white-001"})
    assert res_start.status_code == 200
    assert res_start.json() == {"error": "engine_unavailable"}

    res_move = client.post(
        "/api/training/sac/playout/move",
        json={"finding_id": "s-white-001", "line": ["d2d4", "e5d4"], "user_uci": "f3d4"},
    )
    assert res_move.status_code == 200
    assert res_move.json() == {"error": "engine_unavailable"}
