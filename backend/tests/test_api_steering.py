"""Tests for configuration steering API integration in backend/app.py."""

import chess
import pytest
from fastapi.testclient import TestClient

from backend.app import app, compute_steering_analysis


@pytest.fixture
def client():
    return TestClient(app)


def test_compute_steering_analysis_structure():
    board = chess.Board("r1bqrnk1/pp2bppp/2p2n2/3p2B1/3P4/2NBPN2/PPQ2PPP/R4RK1 w - - 4 11")
    best_moves = [
        {"move": "h2h3", "san": "h3", "score": 48},
        {"move": "f3e5", "san": "Ne5", "score": 31},
        {"move": "a1b1", "san": "Rab1", "score": 26},
    ]
    pv_lines = [
        "h3 h6 Bf4 Bd6",
        "Ne5 Ng4 Bxe7 Qxe7",
        "Rab1 h6",
    ]

    result = compute_steering_analysis(board, best_moves, pv_lines)
    assert "current_phi" in result
    assert "objective_line" in result
    assert "tactical_lines" in result

    # Objective best is h3 (+0.48)
    assert result["objective_line"]["san"] == "h3"
    assert result["objective_line"]["eval"] == "+0.48"

    # Tactical line has Ne5
    tactical_sans = [c["san"] for c in result["tactical_lines"]]
    assert "Ne5" in tactical_sans


def test_analyze_endpoint_returns_steering(client):
    fen = "r1bqrnk1/pp2bppp/2p2n2/3p2B1/3P4/2NBPN2/PPQ2PPP/R4RK1 w - - 4 11"
    response = client.post(
        "/api/analyze",
        json={"fen": fen, "depth": 10, "multipv": 3, "time_limit": 1.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert "steering" in data
    steering = data["steering"]
    if steering:  # If engine/scorer produced candidates
        assert "current_phi" in steering
        assert "objective_line" in steering
        assert "tactical_lines" in steering
