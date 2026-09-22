from __future__ import annotations

import json
import os
from datetime import datetime
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.training.profile_retag import retag_profile

ROOT_DIR = Path(__file__).parent.parent
PROFILE_PATH = ROOT_DIR / "data" / "training" / "profile.json"
RETAGGED_PROFILE_PATH = ROOT_DIR / "data" / "training" / "profile_retagged.json"
REPORT_PATH = ROOT_DIR / "data" / "training" / "retag_report.md"
PROFILES_DIR = ROOT_DIR / "profiles"
PGN_PATH = ROOT_DIR / "games_of_derdiedasdie" / "lichess_derdiedasdie_2026-07-21.pgn"


def main():
    print(f"Loading live profile from {PROFILE_PATH}...")
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        profile = json.load(f)

    today_str = datetime.now().strftime("%Y-%m-%d")
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = PROFILES_DIR / f"profile_pre_retag_{today_str}.json"
    print(f"Creating safety backup at {backup_path}...")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    print(f"Running retag_profile with PGN corpus {PGN_PATH}...")
    retagged_profile, summary = retag_profile(profile, str(PGN_PATH))

    print(f"Saving retagged profile to NEW file {RETAGGED_PROFILE_PATH}...")
    with open(RETAGGED_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(retagged_profile, f, indent=2)

    resolved = summary["resolved_count"]
    unresolved = summary["unresolved_count"]
    before_counts = summary["before_motif_counts"]
    after_counts = summary["after_motif_counts"]
    missed_sacs = summary["missed_sacrifices"]

    # Top motifs sorted by before count
    all_motifs = sorted(
        set(before_counts.keys()).union(after_counts.keys()),
        key=lambda m: before_counts.get(m, 0),
        reverse=True
    )
    top_motifs = all_motifs[:15]

    report_lines = [
        "# RETAG VALIDATION REPORT — Theme-Tagger Phase C-A",
        "",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Source Profile**: `data/training/profile.json` (backed up to `profiles/profile_pre_retag_{today_str}.json`)",
        f"**Output Retagged Profile**: `data/training/profile_retagged.json`",
        "",
        "## C-A1 Backfill & Alignment Summary",
        f"- **Resolved Findings**: {resolved}",
        f"- **Unresolved Findings**: {unresolved}",
        f"- **Total Findings**: {resolved + unresolved}",
        "",
        "## Before → After Motif Distribution (Top Motifs)",
        "",
        "| Motif | Before (Old Bogus Profile) | After (Corrected Retagged Profile) | Notes |",
        "| :--- | :---: | :---: | :--- |"
    ]

    for m in top_motifs:
        b_cnt = before_counts.get(m, 0)
        a_cnt = after_counts.get(m, 0)
        note = ""
        if m in {"advantage", "crushing", "equality"}:
            note = "Stripped (unrecoverable eval tier)"
        elif m == "sacrifice":
            note = "Corrected material-over-line tagger"
        report_lines.append(f"| `{m}` | {b_cnt} | {a_cnt} | {note} |")

    report_lines.extend([
        "",
        f"## Sacrifices You Missed ({len(missed_sacs)} Total)",
        "",
        "Table of every finding whose corrected motifs include `sacrifice`:",
        "",
        "| # | Game | Move # | Sac Move (SAN) | Full PV Line | FEN Before |",
        "| :---: | :--- | :---: | :---: | :--- | :--- |"
    ])

    for i, s in enumerate(missed_sacs, 1):
        white = s.get("white", "?")
        black = s.get("black", "?")
        date = s.get("date", "?")
        game_str = f"{white} vs {black} ({date})"
        move_num = s.get("move_number") or s.get("ply", "?")
        sac_san = f"`{s.get('sac_san')}`"
        pv_str = ", ".join([f"`{m}`" for m in s.get("pv_san", [])])
        fen = f"`{s.get('fen_before')}`"
        report_lines.append(f"| {i} | {game_str} | {move_num} | {sac_san} | {pv_str} | {fen} |")

    report_lines.append("")
    report_content = "\n".join(report_lines)

    print(f"Writing report dump to {REPORT_PATH}...")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"SUCCESS: Retagged profile written to {RETAGGED_PROFILE_PATH}")
    print(f"Report summary: {resolved} resolved, {unresolved} unresolved, {len(missed_sacs)} missed sacrifices found.")


if __name__ == "__main__":
    main()
