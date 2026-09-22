"""
Tests for GET /api/training/weakness-ranking endpoint.
Exercises the REAL metrics.weakness_ranking_all + serialization end-to-end.
"""

from fastapi.testclient import TestClient
from backend.app import app
from backend.training import store

# Use TestClient WITHOUT a `with` block so lifespan engine doesn't start
client = TestClient(app)


def test_weakness_ranking_all_three_keys_present(monkeypatch):
    """
    1. All three keys present: A profile with by_opening + by_phase + by_clock
    returns non-empty ranking, phase, and clock lists, each item serialized
    with full shape including kind.
    """
    mock_profile = {
        "games_analyzed": 50,
        "aggregates": {
            "by_opening": {
                "C60": {"moves": 100, "blind_rate": 0.10},
                "C61": {"moves": 120, "blind_rate": 0.40},
            },
            "by_phase": {
                "opening": {"moves": 200, "blind_rate": 0.14},
                "middlegame": {"moves": 300, "blind_rate": 0.25},
                "endgame": {"moves": 150, "blind_rate": 0.08},
            },
            "by_clock": {
                "fast": {"moves": 100, "blind_rate": 0.30},
                "normal": {"moves": 400, "blind_rate": 0.12},
                "slow": {"moves": 50, "blind_rate": 0.05},
            },
        }
    }
    monkeypatch.setattr(store, "load_profile", lambda: mock_profile)

    res = client.get("/api/training/weakness-ranking")
    assert res.status_code == 200
    data = res.json()

    assert "ranking" in data
    assert "phase" in data
    assert "clock" in data

    assert len(data["ranking"]) > 0
    assert len(data["phase"]) > 0
    assert len(data["clock"]) > 0

    expected_keys = {"dim", "value", "count", "ref_value", "grade", "importance", "kind"}
    for section in ("ranking", "phase", "clock"):
        for item in data[section]:
            assert set(item.keys()) == expected_keys
            assert item["kind"] in ("weakness", "strength")


def test_weakness_ranking_phase_clock_empty_when_absent(monkeypatch):
    """
    2. phase/clock empty when absent: A profile with only by_opening (no by_phase/by_clock)
    returns phase == [] and clock == [], and ranking non-empty.
    """
    mock_profile = {
        "games_analyzed": 50,
        "aggregates": {
            "by_opening": {
                "A00": {"moves": 50, "blind_rate": 0.05},
                "B12": {"moves": 80, "blind_rate": 0.35},
            }
        }
    }
    monkeypatch.setattr(store, "load_profile", lambda: mock_profile)

    res = client.get("/api/training/weakness-ranking")
    assert res.status_code == 200
    data = res.json()
    assert data["phase"] == []
    assert data["clock"] == []
    assert len(data["ranking"]) > 0


def test_weakness_ranking_back_compat_and_leak_first(monkeypatch):
    """
    3. Back-compat: ranking is still the openings list (dims are ECOs), unchanged from before.
    Surfaces the biggest opening leak first.
    """
    mock_profile = {
        "games_analyzed": 50,
        "aggregates": {
            "by_opening": {
                "C60": {"moves": 100, "blind_rate": 0.10},
                "C61": {"moves": 120, "blind_rate": 0.40},  # the leak
                "C62": {"moves": 110, "blind_rate": 0.11},
                "C63": {"moves": 105, "blind_rate": 0.09},
            }
        }
    }
    monkeypatch.setattr(store, "load_profile", lambda: mock_profile)

    res = client.get("/api/training/weakness-ranking")
    assert res.status_code == 200
    data = res.json()
    assert "ranking" in data
    ranking = data["ranking"]
    assert len(ranking) > 0

    top_item = ranking[0]
    assert top_item["dim"] == "C61"
    assert top_item["kind"] == "weakness"
    assert top_item["grade"] < 0
    assert top_item["value"] == 0.40


def test_weakness_ranking_empty_or_no_profile(monkeypatch):
    """
    4. No profile -> all three empty, HTTP 200.
    Tested for:
      1. load_profile returns None
      2. load_profile returns profile with empty by_opening
    """
    monkeypatch.setattr(store, "load_profile", lambda: None)
    res = client.get("/api/training/weakness-ranking")
    assert res.status_code == 200
    assert res.json() == {"ranking": [], "phase": [], "clock": []}

    empty_profile = {"games_analyzed": 0, "aggregates": {"by_opening": {}}}
    monkeypatch.setattr(store, "load_profile", lambda: empty_profile)
    res = client.get("/api/training/weakness-ranking")
    assert res.status_code == 200
    assert res.json() == {"ranking": [], "phase": [], "clock": []}


def test_weakness_ranking_n_param_honored(monkeypatch):
    """
    `n` is honored: A profile with 8 openings and ?n=4 returns at most 4 items.
    """
    mock_by_opening = {
        f"ECO_{i}": {"moves": 50 + i * 5, "blind_rate": 0.05 + i * 0.05}
        for i in range(8)
    }
    mock_profile = {"games_analyzed": 100, "aggregates": {"by_opening": mock_by_opening}}
    monkeypatch.setattr(store, "load_profile", lambda: mock_profile)

    res = client.get("/api/training/weakness-ranking?n=4")
    assert res.status_code == 200
    data = res.json()
    assert len(data["ranking"]) <= 4

