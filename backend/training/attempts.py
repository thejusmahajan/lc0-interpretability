"""T1 — Training memory + spaced repetition.

Every drill attempt is recorded (timestamped, append-only) and drives an
SM-2-lite scheduler: correct answers climb an interval ladder, failures
reset to the bottom and count as lapses. Lapsed drills outrank merely-due
ones in the review queue ("it must be more critical").

Escalation across diagnoses: when a new profile shows blind findings for a
motif the user had previously answered correctly in training, every drill
carrying that motif is reset to due-now with an extra lapse.

Storage (all under data/training/):
  attempts.jsonl — one record per attempt, append-only
  srs.json       — scheduler state per drill id

OWNERSHIP: leader. Deterministic, no engine calls.
"""

from __future__ import annotations

import datetime
import json
import os

from backend.training import store

# Interval ladder in minutes: fail -> step 0 (retry in 10 min);
# each success climbs one step.
LADDER_MINUTES = [10, 24 * 60, 3 * 24 * 60, 7 * 24 * 60, 21 * 24 * 60]


def _attempts_path() -> str:
    return os.path.join(store.TRAINING_DIR, "attempts.jsonl")


def _srs_path() -> str:
    return os.path.join(store.TRAINING_DIR, "srs.json")


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def load_srs() -> dict:
    if os.path.exists(_srs_path()):
        with open(_srs_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_srs(srs: dict):
    store._ensure_dirs()
    store._write_json_atomic(_srs_path(), srs)


def attempts_log() -> list[dict]:
    if not os.path.exists(_attempts_path()):
        return []
    records = []
    with open(_attempts_path(), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def record_attempt(set_id: str, drill: dict, correct: bool, now=None) -> dict:
    """Append the attempt and update the drill's schedule. Returns the SRS
    entry (including the next due time) for the response payload."""
    now = now or _now()
    record = {
        "ts": now.isoformat(),
        "set_id": set_id,
        "drill_id": drill["id"],
        "source": drill.get("source"),
        "tags": drill.get("tags", []),
        "solution_uci": drill.get("solution_uci"),
        "correct": bool(correct),
    }
    store._ensure_dirs()
    with open(_attempts_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    srs = load_srs()
    entry = srs.get(drill["id"]) or {
        "set_id": set_id, "step": 0, "lapses": 0, "reps": 0,
        "tags": drill.get("tags", []),
    }
    entry["reps"] += 1
    if correct:
        entry["step"] = min(entry["step"] + 1, len(LADDER_MINUTES) - 1)
    else:
        entry["lapses"] += 1
        entry["step"] = 0
    entry["due"] = (now + datetime.timedelta(
        minutes=LADDER_MINUTES[entry["step"]])).isoformat()
    entry["last_ts"] = now.isoformat()
    srs[drill["id"]] = entry
    _save_srs(srs)
    return dict(entry, drill_id=drill["id"])


def due_drills(now=None) -> list[dict]:
    """Drills whose review is due, most critical first: higher lapse count
    outranks, then most overdue."""
    now = now or _now()
    cutoff = now.isoformat()
    due = [dict(entry, drill_id=drill_id)
           for drill_id, entry in load_srs().items()
           if entry.get("due") and entry["due"] <= cutoff]
    due.sort(key=lambda e: (-e.get("lapses", 0), e["due"]))
    return due


def escalate_regressions(profile: dict, now=None) -> list[str]:
    """Motifs the user had answered correctly in training that reappear as
    blind findings in a new profile. Their drills reset to due-now with an
    extra lapse. Returns the regressed motif names (stored on the profile
    by the pipeline for the trend report)."""
    by_motif = (profile or {}).get("aggregates", {}).get("by_motif", {})
    blind = {m for m, s in by_motif.items() if s.get("blind", 0) > 0}
    trained = set()
    for rec in attempts_log():
        if rec.get("correct"):
            trained.update(rec.get("tags", []))
    regressed = sorted(blind & trained)
    if not regressed:
        return []

    now = now or _now()
    srs = load_srs()
    changed = False
    for entry in srs.values():
        if set(entry.get("tags", [])) & set(regressed):
            entry["step"] = 0
            entry["lapses"] = entry.get("lapses", 0) + 1
            entry["due"] = now.isoformat()
            changed = True
    if changed:
        _save_srs(srs)
    return regressed


def get_stats() -> dict:
    """Summary stats of SRS attempt history."""
    log = attempts_log()
    total = len(log)
    correct = sum(1 for r in log if r.get("correct"))
    accuracy = (correct / total) if total > 0 else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 3),
        "due_now": len(due_drills()),
    }
