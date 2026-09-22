"""
Build a small, clean, DETERMINISTIC test-case PGN from the full lichess export.

The full corpus is ~9000 games, 97% bullet (heavily hit by the time-scramble
filter), with repetitive openings. For iterating on the pipeline + UI we want a
compact subset that actually exercises every surface:
  - prefer blitz/rapid over bullet (more moves survive the 20s scramble filter)
  - balance the player's White and Black games (both-color repertoires)
  - diversify openings by ECO (repertoire trees need variety, not 30 Londons)
  - only real games (>= MIN_PLIES) so there is something to diagnose

Deterministic: same input PGN -> same subset (sorted, capped per ECO). Run:
    python colab/build_test_subset.py
Writes games_of_derdiedasdie/test_subset.pgn (path printed at the end).
"""
import re
from pathlib import Path

SRC = Path("games_of_derdiedasdie/lichess_derdiedasdie_2026-07-21.pgn")
OUT = Path("games_of_derdiedasdie/test_subset.pgn")
PLAYER = "derdiedasdie"
TARGET = 30            # total games in the subset
MIN_PLIES = 20        # >= 10 full moves = a real game, not an abort
MAX_PER_ECO = 2       # opening diversity cap
SPEED_RANK = {"rapid": 0, "blitz": 1, "bullet": 2}  # preference order


def _h(block, tag):
    m = re.search(rf'\[{tag} "([^"]*)"\]', block)
    return m.group(1) if m else ""


def main():
    text = SRC.read_text(encoding="utf-8", errors="replace")
    blocks = text.split("\n[Event ")
    games = [(b if i == 0 else "[Event " + b) for i, b in enumerate(blocks)]

    parsed = []
    for g in games:
        if PLAYER.lower() not in g.lower():
            continue
        event = _h(g, "Event").lower()
        speed = ("rapid" if "rapid" in event else
                 "blitz" if "blitz" in event else
                 "bullet" if "bullet" in event else "other")
        plies = g.count("[%clk")               # one clock stamp per ply
        if plies < MIN_PLIES:
            continue
        white = _h(g, "White")
        color = "white" if white.lower() == PLAYER.lower() else "black"
        parsed.append({
            "text": g.rstrip() + "\n",
            "speed": speed,
            "color": color,
            "eco": _h(g, "ECO") or "?",
            "opening": _h(g, "Opening"),
            "date": _h(g, "UTCDate"), "time": _h(g, "UTCTime"),
            "plies": plies,
        })

    # deterministic order: slower time controls first (more analyzable), then
    # longer games, then newest — so the pick is stable across runs.
    parsed.sort(key=lambda x: (SPEED_RANK.get(x["speed"], 9), -x["plies"],
                               x["date"], x["time"]), reverse=False)

    picked, per_eco, per_color = [], {}, {"white": 0, "black": 0}
    # two passes: first enforce ECO diversity + rough color balance, then fill.
    for want_balance in (True, False):
        for g in parsed:
            if len(picked) >= TARGET:
                break
            if g in picked:
                continue
            if per_eco.get(g["eco"], 0) >= MAX_PER_ECO:
                continue
            if want_balance and per_color[g["color"]] >= TARGET // 2:
                continue
            picked.append(g)
            per_eco[g["eco"]] = per_eco.get(g["eco"], 0) + 1
            per_color[g["color"]] += 1
        if len(picked) >= TARGET:
            break

    OUT.write_text("\n\n".join(p["text"] for p in picked) + "\n", encoding="utf-8")

    from collections import Counter
    print(f"wrote {len(picked)} games -> {OUT}")
    print("  by speed :", dict(Counter(p["speed"] for p in picked)))
    print("  by color :", dict(Counter(p["color"] for p in picked)))
    print("  distinct ECOs:", len(set(p["eco"] for p in picked)))
    print("  total plies  :", sum(p["plies"] for p in picked),
          f"(avg {sum(p['plies'] for p in picked)//max(1,len(picked))}/game)")


if __name__ == "__main__":
    main()
