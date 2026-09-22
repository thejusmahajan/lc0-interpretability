# Puzzle Storm / Racer regime — 1500–2000 band

For `derdiedasdie`. Puzzle rating >2350 untimed, but the 1500–2000 band goes
missing under Storm/Racer time pressure.

## The diagnosis

A 2350 rating with 1500–2000 failures under a clock is **not** a calculation
problem. Untimed, you calculate your way to the answer, and the rating
reflects that. At 10 seconds there is no time to calculate — you either
recognise the shape or you don't. The regime therefore trains *retrieval
speed*, and the log records **time-to-answer**, not just correctness.

Expect accuracy to plateau early and median time to keep dropping. The median
time is the number that matters; it is the Storm improvement.

## What the data says

Measured over all **1,361,207** puzzles rated 1500–2000 with popularity ≥ 80
(`data/puzzles/puzzles.sqlite`). `quiet%` = share of puzzles whose **first
solution move is neither a check nor a capture** — i.e. invisible to a player
who scans forcing moves first, which is what everyone does on a clock.

| theme | pool | quiet% | |
|---|---:|---:|---|
| trappedPiece | 29,564 | 83.2% | ← quiet blindness |
| quietMove | 58,586 | 75.1% | |
| pawnEndgame | 53,406 | 73.4% | |
| zugzwang | 16,355 | 64.9% | |
| bishopEndgame | 21,083 | 62.9% | |
| knightEndgame | 12,117 | 53.8% | |
| promotion | 33,642 | 50.5% | |
| defensiveMove | 94,647 | 50.1% | |
| advancedPawn | 98,791 | 48.1% | |
| rookEndgame | 65,194 | 37.7% | |
| skewer | 28,645 | 25.9% | |
| pin | 110,137 | 25.3% | |
| clearance | 23,485 | 20.0% | |
| fork | 172,026 | 15.8% | |
| discoveredAttack | 81,514 | 10.8% | ← forcing, but indirect |
| capturingDefender | 14,585 | 10.6% | |
| deflection | 73,639 | 9.0% | |
| intermezzo | 26,633 | 8.2% | |
| sacrifice | 143,290 | 7.7% | |
| attraction | 81,755 | 3.1% | |
| mateIn2 | 99,809 | 1.5% | |
| hangingPiece | 48,605 | 0.0% | ← pure recognition |

These were first computed on a 74,051-puzzle sample and re-measured on the full
database. Nothing moved by more than ~1 percentage point and no conclusion
changed, which is worth stating plainly: the sample was adequate, and the
re-measurement was a check rather than a correction.

Two conclusions, and they set the whole plan:

1. **27.3% of the band opens with a quiet move** (371,662 of 1,361,207), and in the top block it is
   50–84%. This is the single biggest structural trap in Storm.
2. The motifs usually filed together as "hard" split into two unrelated
   failure modes. `deflection`/`attraction`/`intermezzo` are 3–9% quiet —
   the candidate move is *easy to find*; the cost is **verifying** it two or
   three ply out while the clock runs. `trappedPiece`/`zugzwang`/`quietMove`
   are the opposite: trivial to verify once seen, but you never look at them.
   Drilling both the same way wastes half the reps, so they get separate
   blocks and different clocks.

## The decks

27 decks, 960 puzzles, in `data/puzzles/regime/decks/`. All rated 1500–2000,
popularity ≥ 80 (filters out puzzles the community flagged as ambiguous),
seeded so they rebuild identically.

| deck | n | clock | purpose |
|---|---:|---:|---|
| `diag-mixed` | 60 | 20s | Phase 0 baseline |
| `quiet-*` (6) | 30 | 15s | quiet blindness — the top block above |
| `indirect-*` (7) | 30 | 10s | forcing but indirect — verification speed |
| `trap-*` (3) | 40 | 15s | **derived**, see below |
| `endgame-*` (6) | 30–40 | 15s | 45% of the band is endgames |
| `racer-*` (4) | 50 | 10s | mixed simulation |

### The derived decks

These have **no lichess equivalent** — they are computed here with
python-chess by replaying each puzzle and inspecting the first solution move:

- **`trap-quiet-first`** (401,437 puzzles in band, 27.3%) — solution opens with
  no check and no capture.
- **`trap-declined-capture`** (283,441, 19.3%) — a capture was available and the
  solution *declined* it. The hardest reflex to unlearn on a clock.
- **`trap-retreat-first`** (39,095, 2.7%) — solution opens by moving a piece
  *backwards*. Rare, and almost never found under time pressure.

If you drill nothing else, drill these three.

## The schedule — 6 weeks, ~20 min/day

**Week 0, one session.** `diag-mixed` at 20s. Don't rush it; this is the
baseline. Then `report --by theme` to see your real leak profile rather than
my predicted one. **Re-order everything below by what that says.**

**Weeks 1–2 — quiet blindness.** One `quiet-*` block per session (30 puzzles,
15s). Rotate through all six, then repeat. Rule for these two weeks: *before
you move, name one non-forcing candidate.* Even when the forcing move is
right. The point is to build the habit of the second look.

**Weeks 2–3 — verification speed.** One `indirect-*` block per session at 10s.
Different instruction: here you *do* take the forcing move first, and train
yourself to confirm it in one glance. If you can't confirm in 10s, you've
found a real gap — it'll show up as a leech.

**Weeks 3–4 — the traps + endgames.** Alternate `trap-*` and `endgame-*`.
The endgame blocks are the most underrated item on this list: 45% of the band,
high quiet rate, and everyone trains them last.

**Weeks 4–6 — simulation and leeches.** `racer-1..4` at 10s, plus a leech deck
rebuilt each session:

```
python -m backend.training.puzzle_regime leeches --build
python -m backend.training.puzzle_regime drill leeches
```

Leeches are puzzles you've failed twice or more. Once you have a few sessions
logged, **the leech deck is the curriculum** and everything above is
scaffolding.

## Running it

From the repo root, in the `cszero` env:

```bash
# one-time (already done)
python -m backend.training.puzzle_regime cache      # derived flags for the band
python -m backend.training.puzzle_regime plan       # build all 27 decks

# a session
python -m backend.training.puzzle_regime drill quiet-trappedPiece
python -m backend.training.puzzle_regime drill racer-1 -n 25 --clock 8

# progress
python -m backend.training.puzzle_regime report --by theme
python -m backend.training.puzzle_regime report --by deck
python -m backend.training.puzzle_regime leeches

# custom block
python -m backend.training.puzzle_regime deck my-forks -n 40 --themes fork pin --clock 8
python -m backend.training.puzzle_regime urls trap-quiet-first    # lichess links
```

In a drill: type SAN (`Nxe5`, `O-O`) or UCI (`g1f3`). Empty line gives up, `q`
quits. The board is always oriented to the side to move. Misses print the
full solution line and a lichess link.

The clock is **not** a hard cutoff — answers over it are logged as `TIME` and
count as failures. Interrupting `input()` portably on Windows isn't worth the
complexity, and being honest about the overrun trains the same thing.

Failed and timed-out puzzles enter an SM-2 ladder (`10min → 1d → 3d → 7d →
21d`, same ladder as `backend/training/attempts.py`) in
`data/puzzles/regime/srs.json`. Every attempt lands in `sessions.jsonl` with
its elapsed time.

Prefer lichess' own board? `urls <deck>` prints
`https://lichess.org/training/<id>` for every puzzle in the deck — same
curation, real UI, no local logging.

## Two things this can't fix

- **Input speed.** A real component of Racer scores. Click-click beats
  drag-and-drop; premoves don't exist in puzzles. Worth 20 minutes of
  deliberate attention once, then forget it.
- **Tilt after a miss.** Storm punishes the two puzzles *after* a failure more
  than the failure itself. The local drill can't reproduce that pressure —
  only Storm can. Which is why weeks 4–6 are simulation, not more blocks.
