"""Reproduce, in plain arithmetic, the first iterations of Leela's own search.

This is the check behind chapter 7. Every leaf value below was measured from
lc0 itself (with correct move history -- see tools/history_probe notes in
appendix D); the script applies PUCT + FPU by hand and prints the table the
chapter typesets. Discrepancies against the engine's ladder are printed at the
end, so the chapter can never drift from the engine.

    python tools/simulate_search.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

CPUCT, CPUCT_BASE, CPUCT_FACTOR, FPU = 1.745, 38739.0, 3.894, 0.33

# Root priors and the root's own network value (measured).
PRIORS = {"Kd6": 0.4513, "Kf6": 0.4423, "Kf5": 0.0538, "Kd5": 0.0526}
ROOT_V = 0.97602

# The value that each search iteration backed up to the root edge, in White's
# frame, with the line that produced it. All measured from lc0 with history.
ITERATIONS = [
    ("Kd6", "Kd6",                 +0.96766),
    ("Kf6", "Kf6",                 +0.98598),
    ("Kf6", "Kf6 Kf8",             +0.95129),
    ("Kd6", "Kd6 Kd8",             +0.99759),
    ("Kd6", "Kd6 Kf7",             +0.99992),
    ("Kf6", "Kf6 Kf8 e6",          +0.97860),
    ("Kd6", "Kd6 Kd8 e6",          +0.97060),
]


def cpuct(n: float) -> float:
    return CPUCT + CPUCT_FACTOR * math.log((n + CPUCT_BASE + 1.0) / CPUCT_BASE)


def simulate() -> list[dict]:
    N = {m: 0 for m in PRIORS}
    W = {m: 0.0 for m in PRIORS}
    root_W, root_N = ROOT_V, 1
    rows = []

    for it in range(1, len(ITERATIONS) + 2):
        total = sum(N.values())
        root_q = root_W / root_N
        visited_p = sum(PRIORS[m] for m in PRIORS if N[m] > 0)
        q_fpu = root_q - FPU * math.sqrt(visited_p)
        c = cpuct(total)
        sqrt_n = math.sqrt(max(total, 1))

        state = {}
        for m in PRIORS:
            q = (W[m] / N[m]) if N[m] else q_fpu
            u = c * PRIORS[m] * sqrt_n / (1 + N[m])
            state[m] = {"N": N[m], "Q": q, "U": u, "S": q + u, "measured": N[m] > 0}
        pick = max(state, key=lambda m: state[m]["S"])

        rows.append(
            {
                "iteration": it,
                "total_child_visits": total,
                "root_q": root_q,
                "q_fpu": q_fpu,
                "cpuct": c,
                "state": state,
                "selected": pick,
            }
        )
        if it > len(ITERATIONS):
            break

        move, line, value = ITERATIONS[it - 1]
        rows[-1]["engine_selected"] = move
        rows[-1]["line"] = line
        rows[-1]["value"] = value
        N[move] += 1
        W[move] += value
        root_W += value
        root_N += 1
    return rows


def main() -> None:
    rows = simulate()
    for r in rows:
        print(f"--- iteration {r['iteration']}   (child visits so far: {r['total_child_visits']}, "
              f"root Q={r['root_q']:.5f}, FPU Q={r['q_fpu']:.5f}, c_puct={r['cpuct']:.4f})")
        for m, s in sorted(r["state"].items(), key=lambda kv: -kv[1]["S"]):
            tag = "" if s["measured"] else "  (FPU)"
            print(f"     {m:<4} N={s['N']:<2} Q={s['Q']:+.5f} U={s['U']:.5f} "
                  f"S={s['S']:.5f}{tag}")
        if "engine_selected" in r:
            ok = "OK" if r["selected"] == r["engine_selected"] else "MISMATCH"
            print(f"     -> select {r['selected']} [{ok}]  line: {r['line']}  "
                  f"backs up {r['value']:+.5f}")

    # Cross-check final state against the engine's own ladder.
    ladder = json.loads((DATA / "engine_data.json").read_text(encoding="utf-8"))
    lad = ladder["positions"]["kp_endgame"]["ladder"]
    print("\ncross-check against engine ladder:")
    final = rows[-1]["state"]
    for nodes in ("8",):
        eng = {m["san"]: m for m in lad[nodes]["moves"]}
        for m, s in final.items():
            e = eng[m]
            note = "OK" if e["N"] == s["N"] else "MISMATCH"
            eq = e["Q"] if e["Q"] is not None else float("nan")
            print(f"  nodes={nodes} {m:<4} hand N={s['N']} Q={s['Q']:+.5f} | "
                  f"engine N={e['N']} Q={eq:+.5f}  [{note}]")


if __name__ == "__main__":
    main()
