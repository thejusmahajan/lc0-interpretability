"""
Unit tests for backend/training/usual_suspects.py and the /api/training/usual-suspects endpoint.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app import app
from backend.training.usual_suspects import (
    usual_suspects,
    get_broad_aggregates,
    GENERIC_MOTIFS,
    SEVERITY_CAP,
    MIN_GAMES_FLOOR,
)

client = TestClient(app)


def _make_finding(f_id: str, game_prefix: str, motifs: list, swing_cp: int = 400, confirmed: bool = True, severity: str = "missed"):
    return {
        "id": f"{game_prefix}-{f_id}",
        "motifs": motifs,
        "severity": severity,
        "confirmation": {
            "swing_cp": swing_cp,
            "confirmed": confirmed,
        },
        "opening": {"eco": "C50"},
        "game": {"white": "derdiedasdie", "black": "opponent"},
        "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    }


def test_theme_in_3_games_clusters_with_games_3_and_1_game_excluded():
    findings = [
        _make_finding("p01", "g001", ["fork"]),
        _make_finding("p02", "g002", ["fork"]),
        _make_finding("p03", "g003", ["fork"]),
        _make_finding("p04", "g001", ["pin"]),
    ]
    profile = {"findings": findings}

    res = usual_suspects(profile)

    # "fork" appears in 3 distinct games -> included
    # "pin" appears in 1 game -> excluded by >=2 floor
    themes = [item["theme"] for item in res]
    assert "fork" in themes
    assert "pin" not in themes

    fork_item = next(item for item in res if item["theme"] == "fork")
    assert fork_item["games"] == 3
    assert fork_item["occurrences"] == 3


def test_rank_score_hand_computed_exact():
    # "fork" in 2 games (g001, g002)
    # g001: swing_cp=400, confirmed=True -> sev = 400 * 1.0 = 400
    # g002: swing_cp=600, confirmed=True -> sev = 600 * 1.0 = 600
    # mean_severity = (400 + 600) / 2 = 500.0
    # rank_score = 2 * 500.0 = 1000.0
    findings = [
        _make_finding("p01", "g001", ["fork"], swing_cp=400, confirmed=True),
        _make_finding("p02", "g002", ["fork"], swing_cp=600, confirmed=True),
    ]
    profile = {"findings": findings}

    res = usual_suspects(profile)
    assert len(res) == 1
    item = res[0]
    assert item["theme"] == "fork"
    assert item["games"] == 2
    assert item["occurrences"] == 2
    assert item["mean_severity"] == 500.0
    assert item["rank_score"] == 1000.0
    assert item["severity_label"] == "high"
    assert item["finding_ids"] == ["g001-p01", "g002-p02"]


def test_generic_motifs_never_appear():
    findings = [
        _make_finding("p01", "g001", ["advantage", "veryLong", "quietMove", "skewer"]),
        _make_finding("p02", "g002", ["advantage", "veryLong", "quietMove", "skewer"]),
    ]
    profile = {"findings": findings}

    res = usual_suspects(profile)
    themes = [item["theme"] for item in res]
    assert "skewer" in themes
    for generic in GENERIC_MOTIFS:
        assert generic not in themes


def test_unconfirmed_findings_weigh_half_and_severity_cap():
    # "clearance" in 2 games (g001, g002)
    # g001: swing_cp=400, confirmed=False -> sev = 400 * 0.5 = 200.0
    # g002: swing_cp=1200 (exceeds cap 800), confirmed=True -> sev = min(1200, 800) * 1.0 = 800.0
    # mean_sev = (200.0 + 800.0) / 2 = 500.0
    # rank_score = 2 * 500.0 = 1000.0
    findings = [
        _make_finding("p01", "g001", ["clearance"], swing_cp=400, confirmed=False),
        _make_finding("p02", "g002", ["clearance"], swing_cp=1200, confirmed=True),
    ]
    profile = {"findings": findings}

    res = usual_suspects(profile)
    assert len(res) == 1
    item = res[0]
    assert item["mean_severity"] == 500.0
    assert item["rank_score"] == 1000.0


def test_sort_order_by_rank_score_descending():
    findings = [
        # doubleAttack: 2 games, mean 600 -> rank_score 1200
        _make_finding("p01", "g001", ["doubleAttack"], swing_cp=600, confirmed=True),
        _make_finding("p02", "g002", ["doubleAttack"], swing_cp=600, confirmed=True),
        # fork: 3 games, mean 500 -> rank_score 1500
        _make_finding("p03", "g001", ["fork"], swing_cp=500, confirmed=True),
        _make_finding("p04", "g002", ["fork"], swing_cp=500, confirmed=True),
        _make_finding("p05", "g003", ["fork"], swing_cp=500, confirmed=True),
        # discoveredAttack: 2 games, mean 200 -> rank_score 400
        _make_finding("p06", "g001", ["discoveredAttack"], swing_cp=200, confirmed=True),
        _make_finding("p07", "g002", ["discoveredAttack"], swing_cp=200, confirmed=True),
    ]
    profile = {"findings": findings}

    res = usual_suspects(profile)
    themes = [item["theme"] for item in res]
    assert themes == ["fork", "doubleAttack", "discoveredAttack"]
    scores = [item["rank_score"] for item in res]
    assert scores == [1500.0, 1200.0, 400.0]


def test_empty_profile_or_no_clusters_clearing_floor():
    assert usual_suspects({}) == []
    assert usual_suspects({"findings": []}) == []

    # Single game findings only
    single_game = [
        _make_finding("p01", "g001", ["fork"]),
        _make_finding("p02", "g001", ["pin"]),
    ]
    assert usual_suspects({"findings": single_game}) == []


def test_api_endpoint_usual_suspects():
    with patch("backend.training.store.load_profile") as mock_load:
        mock_load.return_value = None
        resp = client.get("/api/training/usual-suspects")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Profile not found"

    sample_profile = {
        "findings": [
            _make_finding("p01", "g001", ["fork"], swing_cp=400, confirmed=True),
            _make_finding("p02", "g002", ["fork"], swing_cp=400, confirmed=True),
        ],
        "aggregates": {
            "by_phase": {"middlegame": {"moves": 50, "blind": 5}},
            "by_concept": {"kingSafety": {"missed": 3}},
        },
    }

    with patch("backend.training.store.load_profile") as mock_load:
        mock_load.return_value = sample_profile
        resp = client.get("/api/training/usual-suspects")
        assert resp.status_code == 200
        data = resp.json()
        assert "suspects" in data
        assert "by_phase" in data
        assert "by_concept" in data
        assert len(data["suspects"]) == 1
        assert data["suspects"][0]["theme"] == "fork"
