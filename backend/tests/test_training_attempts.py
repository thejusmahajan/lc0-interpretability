"""T1/T2 gates: SRS ladder, due ordering, escalation, profile history."""

import datetime

from backend.training import attempts, store, trends

NOW = datetime.datetime(2026, 7, 19, 12, 0, 0)


def _patch_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path / "training"))


def drill(did="d-1", tags=("fork",)):
    return {"id": did, "source": "own_game", "tags": list(tags),
            "solution_uci": "e2e4"}


def test_srs_ladder_and_lapse(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    e = attempts.record_attempt("s1", drill(), correct=False, now=NOW)
    assert e["step"] == 0 and e["lapses"] == 1
    assert e["due"] == (NOW + datetime.timedelta(minutes=10)).isoformat()

    e = attempts.record_attempt("s1", drill(), correct=True, now=NOW)
    assert e["step"] == 1
    assert e["due"] == (NOW + datetime.timedelta(days=1)).isoformat()

    for _ in range(10):  # ladder caps at the top step
        e = attempts.record_attempt("s1", drill(), correct=True, now=NOW)
    assert e["step"] == len(attempts.LADDER_MINUTES) - 1
    assert len(attempts.attempts_log()) == 12


def test_due_ordering_lapses_first(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    attempts.record_attempt("s1", drill("d-clean"), True,
                            now=NOW - datetime.timedelta(days=3))
    attempts.record_attempt("s1", drill("d-lapsed"), False,
                            now=NOW - datetime.timedelta(days=2))

    due = attempts.due_drills(now=NOW)
    assert [d["drill_id"] for d in due] == ["d-lapsed", "d-clean"]


def test_not_due_yet_excluded(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    attempts.record_attempt("s1", drill(), True, now=NOW)
    assert attempts.due_drills(now=NOW) == []
    assert len(attempts.due_drills(now=NOW + datetime.timedelta(days=2))) == 1


def make_profile(created, blind_motifs=(), moves=100):
    return {
        "created": created,
        "games_analyzed": 2,
        "moves_analyzed": moves,
        "findings": [],
        "aggregates": {
            "by_motif": {m: {"blind": 3, "missed": 1} for m in blind_motifs},
            "intuitive_blindness_rate": 0.1,
            "attention_blindness_rate": 0.01,
        },
    }


def test_escalation_resets_trained_motifs(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    attempts.record_attempt("s1", drill("d-fork", tags=("fork",)), True, now=NOW)
    attempts.record_attempt("s1", drill("d-pin", tags=("pin",)), False, now=NOW)

    later = NOW + datetime.timedelta(days=5)
    regressed = attempts.escalate_regressions(
        make_profile("2026-07-24T12:00:00", blind_motifs=("fork", "skewer")),
        now=later)

    # fork was trained-correct and is blind again -> regressed.
    # pin was never answered correctly; skewer was never trained.
    assert regressed == ["fork"]
    srs = attempts.load_srs()
    assert srs["d-fork"]["due"] == later.isoformat()
    assert srs["d-fork"]["lapses"] == 1
    assert srs["d-pin"]["lapses"] == 1  # untouched


def test_profile_history_and_trends(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    store.save_profile(make_profile("2026-07-19T10:00:00",
                                    blind_motifs=("fork",)))
    store.save_profile(make_profile("2026-07-20T10:00:00",
                                    blind_motifs=("fork", "pin")))

    history = store.list_profiles()
    assert [m["created"] for m in history] == [
        "2026-07-19T10:00:00", "2026-07-20T10:00:00"]
    assert store.load_profile()["created"] == "2026-07-20T10:00:00"

    report = trends.trend_report()
    assert len(report["profiles"]) == 2
    assert report["motif_blind_series"]["fork"] == [3, 3]
    assert report["motif_blind_series"]["pin"] == [0, 3]


def test_legacy_profile_migrates_once(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    import json
    import os
    os.makedirs(store.TRAINING_DIR, exist_ok=True)
    with open(os.path.join(store.TRAINING_DIR, "profile.json"), "w") as f:
        json.dump(make_profile("2026-07-18T09:00:00"), f)

    assert len(store.list_profiles()) == 1
    assert len(store.list_profiles()) == 1  # idempotent
