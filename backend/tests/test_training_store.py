import os
import json
import pytest
from backend.training import store

@pytest.fixture(autouse=True)
def mock_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    training_dir = data_dir / "training"
    monkeypatch.setattr(store, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(store, "TRAINING_DIR", str(training_dir))
    return data_dir

def test_epd_cache():
    cache = store.EpdCache("test_policy")
    cache.put("epd1", {"p": 0.5})
    assert cache.get("epd1")["p"] == 0.5
    
    # test reload
    cache2 = store.EpdCache("test_policy")
    assert cache2.get("epd1")["p"] == 0.5

def test_jobs():
    job_id = store.create_job()
    job = store.read_job(job_id)
    assert job["id"] == job_id
    assert job["status"] == "queued"
    
    store.update_job(job_id, status="done", progress={"stage_a_done": 5})
    job2 = store.read_job(job_id)
    assert job2["status"] == "done"
    assert job2["progress"]["stage_a_done"] == 5

def test_profile():
    store.save_profile({"version": 1})
    p = store.load_profile()
    assert p["version"] == 1

def test_repertoire():
    store.save_repertoire({"targets": ["fork"]})
    assert os.path.exists(os.path.join(store.TRAINING_DIR, "repertoire.json"))

def test_drills():
    ds = {"id": "set1", "drills": [{"source": "corpus"}, {"source": "own_game"}]}
    store.save_drill_set(ds)
    loaded = store.load_drill_set("set1")
    assert loaded["id"] == "set1"
    
    sets = store.list_drill_sets()
    assert len(sets) == 1
    assert sets[0]["id"] == "set1"
    assert sets[0]["size"] == 2
    assert "corpus" in sets[0]["sources"]

def test_atomic_write_retries_windows_lock(monkeypatch, tmp_path):
    """os.replace is denied while a reader/antivirus holds the target open
    (WinError 5) — the write must retry, not kill a multi-hour job."""
    import os as _os
    real_replace = _os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(5, "Access is denied", dst)
        return real_replace(src, dst)

    monkeypatch.setattr(store.os, "replace", flaky_replace)
    monkeypatch.setattr(store.time, "sleep", lambda s: None)
    path = str(tmp_path / "job.json")
    store._write_json_atomic(path, {"ok": True})
    assert calls["n"] == 3
    import json as _json
    with open(path, encoding="utf-8") as f:
        assert _json.load(f) == {"ok": True}


def test_atomic_write_gives_up_eventually(monkeypatch, tmp_path):
    def always_denied(src, dst):
        raise PermissionError(5, "Access is denied", dst)

    monkeypatch.setattr(store.os, "replace", always_denied)
    monkeypatch.setattr(store.time, "sleep", lambda s: None)
    import pytest as _pytest
    with _pytest.raises(PermissionError):
        store._write_json_atomic(str(tmp_path / "job.json"), {})

def test_repertoire_variants_coexist(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path / "training"))
    for style in ("weakness", "sacrificial"):
        for color in ("white", "black"):
            store.save_repertoire({"style": style, "color": color,
                                   "created": f"2026-07-20T{len(style):02d}:00:00",
                                   "recommendations": [{"eco": "C20"}]})
    variants = store.list_repertoires()
    assert len(variants) == 4  # all four persist, no clobber
    # specific-variant load
    r = store.load_repertoire("sacrificial", "black")
    assert r["style"] == "sacrificial" and r["color"] == "black"
    # legacy no-arg load returns the last-written build
    assert store.load_repertoire() is not None
