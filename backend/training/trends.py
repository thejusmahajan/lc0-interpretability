"""T2 — Longitudinal trend report.

Composes the profile history (store.list_profiles) with the training log
(attempts) into the numbers that answer "am I actually improving":
blindness rates and confirmed-blunders-per-100-moves over time, per-motif
trajectories, training accuracy per motif, and regressions flagged by the
escalation rule.

OWNERSHIP: leader. Deterministic, no engine calls.
"""

from __future__ import annotations

from collections import defaultdict

from backend.training import attempts, store

TOP_MOTIFS = 6


def trend_report() -> dict:
    history = store.list_profiles()

    series = [{
        "id": m["id"],
        "created": m["created"],
        "games": m["games"],
        "moves": m["moves"],
        "intuitive_blindness_rate": m["intuitive_blindness_rate"],
        "attention_blindness_rate": m["attention_blindness_rate"],
        "confirmed_per_100": m["confirmed_per_100"],
        "regressions": m["regressions"],
    } for m in history]

    # Per-motif blind counts across profiles, for the motifs that matter
    # most in the latest profile.
    motif_series: dict[str, list] = {}
    if history:
        latest = history[-1]["by_motif"]
        ranked = sorted(latest.items(),
                        key=lambda kv: -(2 * kv[1].get("blind", 0)
                                         + kv[1].get("missed", 0)))
        for motif, _stats in ranked[:TOP_MOTIFS]:
            motif_series[motif] = [
                m["by_motif"].get(motif, {}).get("blind", 0) for m in history]

    # Training log rollup.
    log = attempts.attempts_log()
    per_motif = defaultdict(lambda: {"attempts": 0, "correct": 0})
    per_source = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for rec in log:
        for tag in rec.get("tags", []):
            per_motif[tag]["attempts"] += 1
            per_motif[tag]["correct"] += 1 if rec.get("correct") else 0
        src = rec.get("source") or "unknown"
        per_source[src]["attempts"] += 1
        per_source[src]["correct"] += 1 if rec.get("correct") else 0

    def with_accuracy(d):
        return {k: dict(v, accuracy=round(v["correct"] / v["attempts"], 3)
                        if v["attempts"] else 0.0)
                for k, v in d.items()}

    from backend.training import sac_drill, intuition
    srs = attempts.load_srs()
    return {
        "profiles": series,
        "motif_blind_series": motif_series,
        "training": {
            "total_attempts": len(log),
            "total_correct": sum(1 for r in log if r.get("correct")),
            "by_motif": with_accuracy(per_motif),
            "by_source": with_accuracy(per_source),
            "due_now": len(attempts.due_drills()),
            "tracked_drills": len(srs),
            "total_lapses": sum(e.get("lapses", 0) for e in srs.values()),
        },
        "latest_regressions": series[-1]["regressions"] if series else [],
        "srs_stats": attempts.get_stats(),
        "sac_stats": sac_drill.get_stats(),
        "intuition_stats": intuition.get_stats(),
    }
