import os
import pytest
from fastapi.testclient import TestClient

from backend.training import store, eco_backfill
from backend.app import app


@pytest.fixture
def backfill_env(tmp_path, monkeypatch):
    """Fixture creating synthetic profile and a temporary corpus PGN file."""
    training_dir = str(tmp_path / "training")
    monkeypatch.setattr(store, "TRAINING_DIR", training_dir)
    store._ensure_dirs()

    # Create temporary PGN with 2 games
    pgn_path = str(tmp_path / "test_corpus.pgn")
    pgn_content = """[Event "Test Event 1"]
[Site "Lichess"]
[Date "2026.07.21"]
[White "derdiedasdie"]
[Black "OpponentA"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0

[Event "Test Event 2"]
[Site "Lichess"]
[Date "2026.07.21"]
[White "OpponentB"]
[Black "derdiedasdie"]
[Result "0-1"]

1. d2d4 d7d5 2. c2c4 e7e6 0-1
"""
    with open(pgn_path, "w", encoding="utf-8") as f:
        f.write(pgn_content)

    # Synthetic profile with '???' ECOs
    mock_profile = {
        "player_name": "derdiedasdie",
        "games_analyzed": 2,
        "findings": [
            {
                "id": "g000-p004",
                "game": {"white": "derdiedasdie", "black": "OpponentA", "date": "2026.07.21"},
                "ply": 4,
                "severity": "missed",
                "opening": {"eco": "???", "name": "Unknown"},
            },
            {
                "id": "g001-p004",
                "game": {"white": "OpponentB", "black": "derdiedasdie", "date": "2026.07.21"},
                "ply": 4,
                "severity": "blind",
                "opening": {"eco": "???", "name": "Unknown"},
            },
        ],
        "steer_findings": [
            {
                "id": "s-000-p004",
                "game": {"white": "derdiedasdie", "black": "OpponentA", "date": "2026.07.21"},
                "ply": 4,
                "had_sharp_move": True,
                "opening": {"eco": "???", "name": "Unknown"},
            },
        ],
        "aggregates": {
            "by_opening": {
                "???": {"moves": 10, "moves_white": 5, "moves_black": 5, "missed": 1, "blind": 1, "blind_rate": 0.1}
            }
        },
    }

    store.save_profile(mock_profile)
    return pgn_path, mock_profile


def test_eco_backfill_resolves_ecos_and_regroups_aggregates(backfill_env):
    """Verify backfill_ecos replaces '???' with real ECO codes and updates by_opening aggregates."""
    pgn_path, profile = backfill_env

    enriched, summary = eco_backfill.backfill_ecos(profile, pgn_path)

    # Check findings resolved
    f0_eco = enriched["findings"][0]["opening"]["eco"]
    f1_eco = enriched["findings"][1]["opening"]["eco"]
    assert f0_eco != "???"
    assert f1_eco != "???"

    # Check steer findings resolved
    s0_eco = enriched["steer_findings"][0]["opening"]["eco"]
    assert s0_eco == f0_eco

    # Check aggregates by_opening recomputed with real ECOs
    by_opening = enriched["aggregates"]["by_opening"]
    assert f0_eco in by_opening
    assert f1_eco in by_opening
    assert by_opening[f0_eco]["missed"] > 0
    assert any(st["moves"] > 0 for st in by_opening.values())

    # Summary check
    assert len(summary["openings"]) > 0
    assert summary["unresolved"] == 0
    assert summary["discrepancies"] == 0


def test_alignment_mismatch_fallback_search(tmp_path, monkeypatch):
    """Verify index mismatch falls back to header matching and reports discrepancy."""
    training_dir = str(tmp_path / "training")
    monkeypatch.setattr(store, "TRAINING_DIR", training_dir)
    store._ensure_dirs()

    pgn_path = str(tmp_path / "mismatch_corpus.pgn")
    pgn_content = """[Event "Game 0"]
[White "derdiedasdie"]
[Black "PlayerZero"]
[Date "2026.07.21"]

1. e4 e5 2. Nf3 Nc6 1-0

[Event "Game 1"]
[White "derdiedasdie"]
[Black "PlayerOne"]
[Date "2026.07.21"]

1. d4 d5 2. c4 e6 0-1
"""
    with open(pgn_path, "w", encoding="utf-8") as f:
        f.write(pgn_content)

    # Finding id 'g000' has headers matching Game 1 (PlayerOne), not Game 0 (PlayerZero)
    profile = {
        "player_name": "derdiedasdie",
        "games_analyzed": 2,
        "findings": [
            {
                "id": "g000-p004",  # index 0 points to PlayerZero, but headers say PlayerOne
                "game": {"white": "derdiedasdie", "black": "PlayerOne", "date": "2026.07.21"},
                "severity": "missed",
                "opening": {"eco": "???", "name": "Unknown"},
            }
        ],
    }

    enriched, summary = eco_backfill.backfill_ecos(profile, pgn_path)

    # Must find PlayerOne game (1.d4 d5 2.c4 => D06/D30) via fallback header match
    eco = enriched["findings"][0]["opening"]["eco"]
    assert eco.startswith("D")
    assert summary["discrepancies"] == 1


def test_unclassifiable_opening_remains_unknown(tmp_path):
    """Verify unclassifiable position stays '???' gracefully."""
    pgn_path = str(tmp_path / "empty_game_corpus.pgn")
    pgn_content = """[Event "Empty Game"]
[White "derdiedasdie"]
[Black "Opponent"]
[Date "2026.07.21"]

*
"""
    with open(pgn_path, "w", encoding="utf-8") as f:
        f.write(pgn_content)

    profile = {
        "player_name": "derdiedasdie",
        "games_analyzed": 1,
        "findings": [
            {
                "id": "g000-p001",
                "game": {"white": "derdiedasdie", "black": "Opponent", "date": "2026.07.21"},
                "severity": "missed",
                "opening": {"eco": "???", "name": "Unknown"},
            }
        ],
    }

    enriched, summary = eco_backfill.backfill_ecos(profile, pgn_path)
    assert enriched["findings"][0]["opening"]["eco"] == "???"
    assert summary["unresolved"] == 1



def test_backfill_ecos_api_endpoint(backfill_env, monkeypatch):
    """Integration test for POST /api/training/openings/backfill-ecos endpoint."""
    pgn_path, profile = backfill_env
    client = TestClient(app)

    monkeypatch.setattr("backend.app._corpus_pgn", lambda: pgn_path)

    res = client.post("/api/training/openings/backfill-ecos")
    assert res.status_code == 200
    data = res.json()

    assert "openings" in data
    assert "unresolved" in data
    assert data["unresolved"] == 0

    # Verify profile on disk was saved with new ECOs
    saved_profile = store.load_profile()
    assert saved_profile is not None
    assert saved_profile["findings"][0]["opening"]["eco"] != "???"
