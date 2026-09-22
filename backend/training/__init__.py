"""
Elite Training System package.

Modules:
    metrics.py            — NORMATIVE metric definitions (leader-owned; do not edit)
    store.py              — on-disk cache + job state          (Gemini-owned)
    pipeline.py           — Diagnostician batch pipeline       (Gemini-owned)
    puzzle_db.py          — Lichess puzzle DB mining           (Gemini-owned)
    openings.py           — ECO/opening prefix matcher         (Gemini-owned)
    drills.py             — Drill set assembly                 (Gemini-owned)
    gems.py               — Hidden-gem detector                (Claude-owned)
    select_repertoire.py  — Repertoire backwards selection     (Claude-owned)

See TRAINING_SYSTEM_PLAN.md at repo root for the authoritative design.
"""
