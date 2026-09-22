"""
Unit tests for usual suspects approval gate and severity-blended deck generation.
"""

import os
import datetime
import hashlib
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
import chess

from backend.app import app
from backend.training import store, usual_suspects, drills, attempts

client = TestClient(app)


def _make_finding(f_id: str, game_prefix: str, motifs: list, swing_cp: int = 400, confirmed: bool = True, fen: str = None):
    if not fen:
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    return {
        "id": f"{game_prefix}-{f_id}",
        "motifs": motifs,
        "severity": "missed",
        "confirmation": {
            "swing_cp": swing_cp,
            "confirmed": confirmed,
        },
        "opening": {"eco": "C50"},
        "game": {"white": "derdiedasdie", "black": "opponent"},
        "fen_before": fen,
        "best": {"uci": "e2e4", "san": "e4"},
    }


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Use a temporary directory for store data in tests."""
    data_dir = str(tmp_path / "data")
    monkeypatch.setenv("CSZERO_DATA_DIR", data_dir)
    store.DATA_DIR = data_dir
    store.TRAINING_DIR = os.path.join(data_dir, "training")
    store._ensure_dirs()
    yield data_dir


def test_approve_persists_and_unknown_theme_400():
    sample_profile = {
        "findings": [
            _make_finding("p01", "g001", ["fork"]),
            _make_finding("p02", "g002", ["fork"]),
        ]
    }
    with patch("backend.training.store.load_profile", return_value=sample_profile):
        # 1. Approve valid theme "fork"
        resp = client.post("/api/training/usual-suspects/approve", json={"themes": ["fork"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["themes"] == ["fork"]

        # GET approved returns stored approval
        resp_get = client.get("/api/training/usual-suspects/approved")
        assert resp_get.status_code == 200
        assert resp_get.json()["themes"] == ["fork"]

        # 2. Unknown theme -> 400
        resp_err = client.post("/api/training/usual-suspects/approve", json={"themes": ["invalid_theme"]})
        assert resp_err.status_code == 400
        assert "Unknown theme" in resp_err.json()["detail"]


def test_blending_higher_rank_score_gets_strictly_more_slots():
    # "sacrifice": 3 games, swing 800 -> mean 800, rank_score = 2400
    # "fork": 2 games, swing 400 -> mean 400, rank_score = 800
    # Total rank_score = 3200. Target count = 8.
    # Expected slots: sacrifice = 6 (75%), fork = 2 (25%)
    findings = [
        # 6 distinct findings for sacrifice
        _make_finding("s01", "g001", ["sacrifice"], swing_cp=800, fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
        _make_finding("s02", "g002", ["sacrifice"], swing_cp=800, fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"),
        _make_finding("s03", "g003", ["sacrifice"], swing_cp=800, fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
        _make_finding("s04", "g001", ["sacrifice"], swing_cp=800, fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"),
        _make_finding("s05", "g002", ["sacrifice"], swing_cp=800, fen="r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"),
        _make_finding("s06", "g003", ["sacrifice"], swing_cp=800, fen="r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"),
        # 3 distinct findings for fork across 2 games
        _make_finding("f01", "g001", ["fork"], swing_cp=400, fen="r1bqk2r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"),
        _make_finding("f02", "g002", ["fork"], swing_cp=400, fen="r1bqk2r/pppp1ppp/2n2n2/4p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R b KQkq - 0 4"),
        _make_finding("f03", "g001", ["fork"], swing_cp=400, fen="r1bqk2r/pppp1ppp/5n2/4p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 5"),
    ]
    profile = {"findings": findings}
    approved = ["sacrifice", "fork"]

    deck = usual_suspects.build_suspects_deck(profile, approved, count=8)
    drills = deck["drills"]
    assert len(drills) == 8

    sac_drills = [d for d in drills if d.get("suspect_theme") == "sacrifice"]
    fork_drills = [d for d in drills if d.get("suspect_theme") == "fork"]

    assert len(sac_drills) == 6
    assert len(fork_drills) == 2
    assert len(sac_drills) > len(fork_drills)


def test_every_deck_drill_origin_belongs_to_approved_findings():
    findings = [
        _make_finding("p01", "g001", ["fork"], fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
        _make_finding("p02", "g002", ["fork"], fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"),
        _make_finding("p03", "g001", ["pin"], fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
        _make_finding("p04", "g002", ["pin"], fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"),
    ]
    profile = {"findings": findings}

    # Approve only "fork"
    deck = usual_suspects.build_suspects_deck(profile, ["fork"], count=10)
    approved_finding_ids = {"g001-p01", "g002-p02"}

    for d in deck["drills"]:
        assert d["origin"]["finding_id"] in approved_finding_ids
        assert d["suspect_theme"] == "fork"


def test_epd_dedupe_prevents_duplicate_positions():
    # 2 findings with exact same position FEN
    fen_same = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    findings = [
        _make_finding("p01", "g001", ["fork"], fen=fen_same),
        _make_finding("p02", "g002", ["fork"], fen=fen_same),
    ]
    profile = {"findings": findings}

    deck = usual_suspects.build_suspects_deck(profile, ["fork"], count=10)
    drills = deck["drills"]

    # Dedupe should yield only 1 drill
    assert len(drills) == 1
    seen_epds = set()
    for d in drills:
        epd = chess.Board(d["fen"]).epd()
        assert epd not in seen_epds
        seen_epds.add(epd)


def test_deck_size_equal_count_or_less_when_thin():
    f_thin = [
        _make_finding("p01", "g001", ["fork"], fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
        _make_finding("p02", "g002", ["fork"], fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"),
    ]
    profile = {"findings": f_thin}

    # Request count=10 when only 2 findings exist -> size <= count (2)
    deck = usual_suspects.build_suspects_deck(profile, ["fork"], count=10)
    assert len(deck["drills"]) == 2 <= 10


def test_deck_retrievable_via_store():
    findings = [
        _make_finding("p01", "g001", ["fork"], fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
        _make_finding("p02", "g002", ["fork"], fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"),
    ]
    profile = {"findings": findings}
    store.save_profile(profile)
    store.save_approved_suspects(["fork"])

    resp = client.post("/api/training/usual-suspects/deck", json={"count": 5})
    assert resp.status_code == 200
    deck = resp.json()
    set_id = deck["id"]

    # Retrievable via load_drill_set
    loaded = store.load_drill_set(set_id)
    assert loaded is not None
    assert loaded["id"] == set_id
    assert len(loaded["drills"]) == len(deck["drills"])

    # Appears in list_drill_sets
    all_sets = store.list_drill_sets()
    set_ids = [s["id"] for s in all_sets]
    assert set_id in set_ids


def test_empty_approval_returns_empty_drills_no_error():
    sample_profile = {
        "findings": [
            _make_finding("p01", "g001", ["fork"]),
            _make_finding("p02", "g002", ["fork"]),
        ]
    }
    store.save_profile(sample_profile)
    store.save_approved_suspects([])

    resp = client.post("/api/training/usual-suspects/deck", json={"count": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert data["drills"] == []


def test_deterministic_drill_ids():
    """Verify that build_drill_from_finding generates a stable, deterministic drill ID."""
    finding = _make_finding("p01", "g001", ["fork"])
    d1 = drills.build_drill_from_finding(finding, source="usual_suspects", suspect_theme="fork")
    d2 = drills.build_drill_from_finding(finding, source="usual_suspects", suspect_theme="fork")

    assert d1["id"] == d2["id"]
    assert d1["id"].startswith("d-")
    expected_hash = hashlib.sha1(finding["id"].encode("utf-8")).hexdigest()[:12]
    assert d1["id"] == f"d-{expected_hash}"

    # Fallback path for finding without 'id'
    finding_no_id = {k: v for k, v in finding.items() if k != "id"}
    d3 = drills.build_drill_from_finding(finding_no_id, source="usual_suspects")
    d4 = drills.build_drill_from_finding(finding_no_id, source="usual_suspects")
    assert d3["id"] == d4["id"]
    assert d3["id"].startswith("d-")


def test_srs_aware_deck_ordering():
    """Verify SRS buckets: UNSEEN -> DUE -> NOT-DUE, retaining NOT-DUE drills."""
    f1 = _make_finding("p01", "g001", ["fork"], swing_cp=500, fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    f2 = _make_finding("p02", "g002", ["fork"], swing_cp=400, fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    f3 = _make_finding("p03", "g003", ["fork"], swing_cp=300, fen="rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")

    profile = {"findings": [f1, f2, f3]}

    d1_id = f"d-{hashlib.sha1(f1['id'].encode('utf-8')).hexdigest()[:12]}"
    d2_id = f"d-{hashlib.sha1(f2['id'].encode('utf-8')).hexdigest()[:12]}"
    d3_id = f"d-{hashlib.sha1(f3['id'].encode('utf-8')).hexdigest()[:12]}"

    now = datetime.datetime.utcnow()
    past_due_iso = (now - datetime.timedelta(hours=2)).isoformat()
    future_due_iso = (now + datetime.timedelta(days=7)).isoformat()

    # Seed SRS state:
    # d1 (f1): UNSEEN (not in SRS)
    # d2 (f2): DUE (due in the past)
    # d3 (f3): NOT-DUE (due in the future)
    mock_srs = {
        d2_id: {"due": past_due_iso, "step": 1, "lapses": 0, "reps": 1},
        d3_id: {"due": future_due_iso, "step": 3, "lapses": 0, "reps": 3},
    }
    attempts._save_srs(mock_srs)

    deck = usual_suspects.build_suspects_deck(profile, ["fork"], count=10)
    drills_list = deck["drills"]

    assert len(drills_list) == 3
    drill_ids = [d["id"] for d in drills_list]

    # 1. UNSEEN (d1) is before NOT-DUE (d3)
    assert drill_ids.index(d1_id) < drill_ids.index(d3_id)

    # 2. DUE (d2) is before NOT-DUE (d3)
    assert drill_ids.index(d2_id) < drill_ids.index(d3_id)

    # 3. NOT-DUE (d3) is still present in the deck (deprioritized to the end)
    assert d3_id in drill_ids
    assert drill_ids[-1] == d3_id


def test_rebuild_selection_prefers_unseen_over_solved_highsev():
    """SELECTION (not just ordering) must be SRS-aware: on a tight deck, an already-solved
    high-severity finding must NOT crowd out an UNSEEN lower-severity one — otherwise every
    rebuild re-selects the same solved drills and untouched ones never surface.

    Mutation guard: fails on the old severity-only selection (which would pick f_solved).
    """
    f_solved = _make_finding("p01", "g001", ["fork"], swing_cp=800,
                             fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    f_unseen = _make_finding("p02", "g002", ["fork"], swing_cp=300,
                             fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    profile = {"findings": [f_solved, f_unseen]}

    d_solved = f"d-{hashlib.sha1(f_solved['id'].encode('utf-8')).hexdigest()[:12]}"
    d_unseen = f"d-{hashlib.sha1(f_unseen['id'].encode('utf-8')).hexdigest()[:12]}"

    now = datetime.datetime.utcnow()
    future_due_iso = (now + datetime.timedelta(days=7)).isoformat()
    # f_solved = NOT-DUE (recently solved); f_unseen absent from SRS (UNSEEN)
    attempts._save_srs({d_solved: {"due": future_due_iso, "step": 3, "lapses": 0, "reps": 3}})

    # Tight deck: 1 slot. The UNSEEN finding must win selection despite lower severity.
    deck = usual_suspects.build_suspects_deck(profile, ["fork"], count=1)
    ids = [d["id"] for d in deck["drills"]]
    assert len(ids) == 1
    assert ids == [d_unseen], f"expected the UNSEEN finding selected, got {ids}"
    assert d_solved not in ids

