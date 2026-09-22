import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.training import store, openings_sharpness

client = TestClient(app)


@pytest.fixture
def mock_profile_with_openings():
    return {
        "player_name": "derdiedasdie",
        "findings": [
            {
                "id": "g001-p004",
                "opening": {"eco": "D02", "name": "London System"},
                "severity": "missed",
            },
            {
                "id": "g002-p006",
                "opening": {"eco": "C44", "name": "King's Pawn Game"},
                "severity": "blind",
            },
            {
                "id": "g003-p002",
                "opening": {"eco": "???", "name": "Unknown"},
                "severity": "missed",
            },
        ],
        "steer_findings": [
            # D02 London System: 2 sharp positions (had_sharp_move=True), mean complexity = 0.80
            {
                "id": "s-001-p010",
                "opening": {"eco": "D02", "name": "London System"},
                "had_sharp_move": True,
                "steer": {"complexity": 0.90, "uci": "e2e4"},
            },
            {
                "id": "s-001-p014",
                "opening": {"eco": "D02", "name": "London System"},
                "had_sharp_move": True,
                "steer": {"complexity": 0.70, "uci": "d4d5"},
            },
            # C44 King's Pawn Game: 1 sharp position, mean complexity = 0.50
            {
                "id": "s-002-p008",
                "opening": {"eco": "C44", "name": "King's Pawn Game"},
                "had_sharp_move": True,
                "steer": {"complexity": 0.50, "uci": "g1f3"},
            },
            {
                "id": "s-002-p012",
                "opening": {"eco": "C44", "name": "King's Pawn Game"},
                "had_sharp_move": False,
                "steer": {"complexity": 0.30, "uci": "c2c3"},
            },
            # Unclassified opening ('???') - should be excluded
            {
                "id": "s-003-p005",
                "opening": {"eco": "???", "name": "Unknown"},
                "had_sharp_move": True,
                "steer": {"complexity": 0.95, "uci": "h2h3"},
            },
        ],
    }


def test_sac_count_and_mean_complexity_per_eco(mock_profile_with_openings):
    """Verify sharp count matches had_sharp_move count and mean complexity is exact."""
    results = openings_sharpness.sharpness_by_opening(mock_profile_with_openings)

    d02 = next(item for item in results if item["eco"] == "D02")
    assert d02["sharp_positions"] == 2
    assert d02["mean_complexity"] == 0.80  # (0.90 + 0.70) / 2
    assert d02["n_positions"] == 3  # 2 steer + 1 finding

    c44 = next(item for item in results if item["eco"] == "C44")
    assert c44["sacs"] == 1
    assert c44["mean_complexity"] == 0.40  # (0.50 + 0.30) / 2
    assert c44["n_positions"] == 3  # 2 steer + 1 finding


def test_openings_sorted_by_sharpness_score_descending(mock_profile_with_openings):
    """Verify openings are sorted by (sacs * mean_complexity) DESC."""
    results = openings_sharpness.sharpness_by_opening(mock_profile_with_openings)

    ecos = [item["eco"] for item in results]
    # D02 score = 2 * 0.80 = 1.60; C44 score = 1 * 0.40 = 0.40
    assert ecos == ["D02", "C44"]
    assert results[0]["sharpness_score"] > results[1]["sharpness_score"]


def test_unclassified_eco_excluded(mock_profile_with_openings):
    """Verify '???' ECO is excluded from sharpness results."""
    results = openings_sharpness.sharpness_by_opening(mock_profile_with_openings)

    ecos = [item["eco"] for item in results]
    assert "???" not in ecos
    assert len(results) == 2


def test_top_positions_sorted_by_complexity(mock_profile_with_openings):
    """Verify top_positions list contains steer finding IDs sorted by complexity DESC."""
    results = openings_sharpness.sharpness_by_opening(mock_profile_with_openings)

    d02 = next(item for item in results if item["eco"] == "D02")
    # s-001-p010 (0.90) should be before s-001-p014 (0.70)
    assert d02["top_positions"] == ["s-001-p010", "s-001-p014"]


def test_sharpness_and_recommendations_api_routes(mock_profile_with_openings, monkeypatch):
    """Integration test for GET /api/training/openings/sharpness and /recommendations."""
    monkeypatch.setattr("backend.training.store.load_profile", lambda: mock_profile_with_openings)

    # 1. Sharpness endpoint
    resp_sharp = client.get("/api/training/openings/sharpness")
    assert resp_sharp.status_code == 200
    sharp_data = resp_sharp.json()
    assert "openings" in sharp_data
    assert len(sharp_data["openings"]) == 2
    assert sharp_data["openings"][0]["eco"] == "D02"

    # 2. Recommendations endpoint (all)
    resp_rec = client.get("/api/training/openings/recommendations")
    assert resp_rec.status_code == 200
    recs = resp_rec.json()["recommendations"]
    assert len(recs) >= 10

    # 3. Recommendations endpoint (color filter)
    resp_white = client.get("/api/training/openings/recommendations?color=white")
    assert resp_white.status_code == 200
    white_recs = resp_white.json()["recommendations"]
    assert all(r["color"] == "white" for r in white_recs)
    assert len(white_recs) > 0

    resp_black = client.get("/api/training/openings/recommendations?color=black")
    assert resp_black.status_code == 200
    black_recs = resp_black.json()["recommendations"]
    assert all(r["color"] == "black" for r in black_recs)
    assert len(black_recs) > 0
