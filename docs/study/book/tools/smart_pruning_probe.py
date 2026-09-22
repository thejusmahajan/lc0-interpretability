"""Isolate what `SmartPruningFactor` does to the K+P ladder.

The question it answers (ADDENDUM.md §J): at `go nodes 800` the engine reports
Kf5 with the *highest* S of all four moves and only one visit, and never selects
it again. Is that a proven/terminal value being protected, or is it smart
pruning excluding the move?

    python tools/smart_pruning_probe.py            # control vs variant at 800
    python tools/smart_pruning_probe.py 470        # any single budget

Control = exactly the flags `collect_engine_data.py` uses (which do NOT override
smart pruning, so it runs at its default 1.33).
Variant = the same flags plus `--smart-pruning-factor=0`, i.e. pruning off.

Requires: engine/lc0.exe + engine/791556.pb.gz. No python-chess, no conda env.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ENGINE_DIR = REPO / "engine"
LC0 = ENGINE_DIR / "lc0.exe"
NET_SMALL = ENGINE_DIR / "791556.pb.gz"

KP_FEN = "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1"

# Identical to collect_engine_data.py:146-157 minus the weights argument.
BASE_FLAGS = [
    "--verbose-move-stats",
    "--threads=1",
    "--minibatch-size=1",
    "--max-collision-events=1",
    "--max-collision-visits=1",
    "--out-of-order-eval=false",
    "--task-workers=0",
    "--backend=blas",
]

MOVE_RE = re.compile(r"^info string ([a-h][1-8][a-h][1-8][qrbn]?|node)\s+\(")


def _field(line: str, name: str):
    m = re.search(r"\(" + name + r":\s*(-?[\d.]+)%?", line)
    return float(m.group(1)) if m else None


def parse_verbose(lines: list[str]) -> dict:
    """Same parser as collect_engine_data.py:117-141, so the columns are comparable."""
    moves, root = [], None
    for line in lines:
        if not MOVE_RE.match(line):
            continue
        name = line.split()[2]
        rec = {
            "move": name,
            "N": int(re.search(r"N:\s*(\d+)", line).group(1)),
            "P": _field(line, "P"), "WL": _field(line, "WL"),
            "D": _field(line, "D"), "M": _field(line, "M"),
            "Q": _field(line, "Q"), "U": _field(line, "U"),
            "S": _field(line, "S"), "V": _field(line, "V"),
        }
        if name == "node":
            root = rec
        else:
            moves.append(rec)
    moves.sort(key=lambda r: (-r["N"], -(r["P"] or 0)))
    return {"moves": moves, "root": root}


def run(fen: str, nodes: int, extra=(), timeout: int = 600) -> dict:
    cmd = [str(LC0), f"--weights={NET_SMALL}"] + BASE_FLAGS + list(extra)
    script = f"uci\nisready\nposition fen {fen}\ngo nodes {nodes}\n"
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, cwd=str(ENGINE_DIR), bufsize=1,
    )
    assert proc.stdin and proc.stdout
    proc.stdin.write(script)
    proc.stdin.flush()

    lines, deadline, bestmove = [], time.time() + timeout, None
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip())
        if line.startswith("bestmove"):
            bestmove = line.split()[1]
            break
    try:
        proc.stdin.write("quit\n")
        proc.stdin.flush()
    except Exception:
        pass
    proc.kill()

    out = parse_verbose(lines)
    out["bestmove"] = bestmove
    return out


def show(tag: str, r: dict) -> None:
    root = r["root"]
    sum_n = sum(m["N"] for m in r["moves"])
    print(f"\n=== {tag}   bestmove={r['bestmove']}  tree N={root['N']}  sum n_a={sum_n}")
    print(f"    root Q={root['Q']:.5f} D={root['D']}")
    for m in sorted(r["moves"], key=lambda m: -m["S"]):
        q = m["Q"] if m["Q"] is not None else float("nan")
        print(f"    {m['move']}  n={m['N']:<4} P={m['P']:>6} Q={q:+.5f} "
              f"U={m['U']:.5f} S={m['S']:.5f} D={m['D']} V={m['V']}")


def main() -> None:
    nodes = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    results = {}
    for tag, extra in (
        ("CONTROL (SmartPruningFactor at default 1.33)", ()),
        ("VARIANT (--smart-pruning-factor=0)", ("--smart-pruning-factor=0",)),
    ):
        r = run(KP_FEN, nodes, extra)
        show(f"{tag} @ go nodes {nodes}", r)
        results[tag] = r
    print(json.dumps({k: v["root"]["N"] for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
