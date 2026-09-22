# Chess Speak Out Loud — User Manual

> How to *use* the app. For how to *start* it (servers, conda env, ports), see
> [`HOW_TO_RUN.md`](../../HOW_TO_RUN.md). For the HTTP API, see
> [`docs/api_contract.md`](docs/api_contract.md).

The app has two modes, toggled in the header:

- **Analysis Mode** — explore any game with LC0's raw intuition (policy
  arrows) and BT3's attention (saliency glow).
- **Training Mode** — the Elite Training System: diagnose your weaknesses
  from your own games, then drill them.

---

## 1. Analysis Mode

Paste a PGN into the text area and press **Load Game**, then step through
with **Next** and **Take-back / Prev**.

| Control | What it does |
|---|---|
| **Show Top 20 Arrows** | Overlays LC0's policy distribution — arrow thickness = how strongly the network's intuition likes each move *before any search*. |
| **Thinking time** | How long "Think Deeper" searches (2s Normal by default). |
| **Think Deeper** | Runs a real search for the evaluation instead of raw policy. |
| **Intuition Glow** | BT3 attention heatmap: which squares the network is *looking at* in this position. Instant. |
| **Calculation Glow** + **Compute (~15s)** | Attention aggregated over the network's calculation — slower, deeper picture. |
| **Evaluation** | White-POV score of the current position. |

**Tip:** the difference between the two glows is the point — Intuition Glow
is "what catches the eye", Calculation Glow is "what mattered after
thinking". When they disagree, that's where humans blunder too.

---

## 2. Training Mode

Three tabs: **Diagnose PGN → Weakness Profile → Training Drills**. That
order is the workflow.

### 2.1 Diagnose PGN

1. Export your games as PGN (Lichess: your profile → *Export games*;
   Chess.com works too).
2. Paste the PGN, enter your **player name exactly as it appears in the PGN
   headers** (e.g. `derdiedasdie` — case doesn't matter, but spelling does).
3. **Start Diagnosis** and watch the progress bar.

What happens under the hood (two-stage pipeline):

- **Stage A** — every move you played is compared against LC0's raw policy.
  A move is flagged when the network's best move had a much higher prior
  than yours (divergence ≥ 0.15).
- **Stage B** — only flagged moves (typically 10–20%) get the expensive
  treatment: a real search to confirm the mistake in centipawns, a BT3
  attention snapshot, and tactical-motif + concept tagging of the line you
  missed.

**Sizing guidance:** ~20–30 games per run is the sweet spot. Stage A costs
one fast engine call per move you played; Stage B costs ~6 seconds per
flagged move. A 24-game batch takes roughly 20–40 minutes on this machine.
Positions are cached by position (EPD), so **re-running over overlapping
games is much faster** — only new positions pay full price.

**Errors are informative:** if no games match your player name, the job
fails with a message listing the names that *are* in the PGN. Only one
diagnosis can run at a time (a second request gets a 409).

### 2.2 Weakness Profile

The report at the top:

- **Games / Moves analyzed** — coverage of this profile.
- **Intuitive Blindness Rate** — share of your moves where the engine's
  choice *never even occurred* to your pattern recognition (severity
  "blind": your move's prior ≤ 0.05 while a much better move existed).
- **Attention Blindness Rate** — the stricter structural version: the
  network's attention was hot (≥ 0.6) on the squares of the move you
  missed, while your move engaged only cold squares (≤ 0.25). These are the
  most valuable findings — you weren't just wrong, you were *looking at the
  wrong part of the board*.

Tables:

- **Top Motifs Missed** — tactical patterns (fork, pin, discoveredAttack …)
  ranked by how often you were blind to them. Findings confirmed by search
  (eval swing ≥ 90cp) count double.
- **Top Openings** — ECO codes where your blind-rate is worst. High
  blind-rate in one opening = you don't know its typical tactics yet.
- **Top Concepts** — positional themes you undervalue.

**Findings list:** each card is one mistake — click it to load the position
on the board with the policy arrows (red = what you should have played) and
the attention hot-squares overlaid. Severities: `missed` = you considered
it but undervalued it; `blind` = it never crossed your mind.

### 2.3 Training Drills

**Generate Drills** builds a set from three sources:

- **own_game** (~40%) — your worst confirmed mistakes, replayed as puzzles.
  Duplicates (same position or same solution move) are filtered out,
  strongest mistakes first.
- **corpus** (~40%) — Lichess puzzles matching your worst motifs, rating
  1600–2300. If the puzzle starts with an opponent move you'll see it
  animate before you're allowed to move.
- **hidden_gem** (~20%) — quiet positions (eval ≈ 0.00) where the network
  nevertheless strongly "feels" one move and its attention is concentrated.
  These only appear when suitable quiet candidate positions exist, so small
  sets often contain none — that's normal, not a bug.

Play your move on the board. You get the verdict, the eval swing (or
"decisive (mate)"), the engine line, and the full policy + attention
overlay of what you should have seen. **Both castling notations are
accepted** — drop the king on g1 or on the rook, either counts.

### 2.4 Repertoire (API only for now)

The Repertoire Architect picks openings *backwards*: it finds the openings
whose master-game structures most often produce exactly the tactical
patterns you currently miss, then keeps only lines LC0 rates as sound
(≥ −50cp for your side) and sharp (< 45% draw share). No UI yet — use the
API:

```powershell
# after a diagnosis has produced a profile:
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/training/repertoire `
  -ContentType application/json -Body '{"color": "white", "build": true}'
# omit "build" (or set false) to read the stored repertoire
```

Each recommendation comes with a deterministic rationale, e.g. *"Play the
French Defense: Advance Variation (1. e4 e6 2. d4 d5 3. e5). Structures
from this opening produce advantage in 12.7% of tagged master-game puzzles;
LC0 holds the tabiya at 24cp with a 41% draw share…"*

---

## 3. Tips & tricks

- **Feed it your normal time control.** Policy divergence measures
  *intuition*, and bullet is nearly pure intuition — bullet games are
  legitimate diagnostic input. Just expect more "blind" findings from time
  scrambles; the Stage-B confirmation (eval swing) separates real pattern
  gaps from panic.
- **Iterate in batches.** Diagnose 20–30 games, drill for a while, then
  diagnose the *next* batch. Each diagnosis overwrites the previous
  profile, so drill before you re-diagnose (drill sets themselves are kept
  on disk and stay loadable).
- **The EPD caches are your friend.** `data/training/cache/*.jsonl` stores
  every policy and Stage-B result keyed by position. Re-analysis of
  familiar structures (your pet openings) gets cheaper over time. Safe to
  delete if you want a cold start; they just repopulate.
- **Read "blind + confirmed" findings first.** Blind means your intuition
  never surfaced the move; confirmed means it cost ≥ 90cp. That
  intersection is the highest-value training signal in the system.
- **Attention findings beat eval findings.** If the attention-blindness
  flag is set, the fix isn't "calculate more" — it's "look at that region
  of the board at all". The hot-square overlay on the finding shows you
  exactly where.
- **Repertoire per color.** Build white and black separately; the soundness
  gate flips sign correctly for black.

## 4. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Start Diagnosis does nothing, then an error about player names | Your name isn't in the PGN headers — the error lists what is. Use that spelling. |
| `409 A diagnosis job is already running` | One at a time. Wait for the running job; a server restart clears orphaned jobs automatically. |
| Job fails with "engine in mock mode" | LC0 didn't start — see HOW_TO_RUN.md; check `/api/health` says `"engine_mode": "live"`. |
| Drill set smaller than requested | Not enough distinct findings (own_game), or no quiet candidates (hidden_gem). Diagnose more games. |
| Profile shows 0 games after a run | Fixed in G5.1 — a zero-match run now errors instead of overwriting your profile. Update if you see this. |
| Everything is slow | BT3 saliency is ~1.5s per position on CPU; Stage B ~6s per flagged move. It's the physics of this machine, not a hang — watch the progress bar. |

## 5. Where your data lives

```
data/training/profile.json      current weakness profile (overwritten per diagnosis)
data/training/repertoire.json   current repertoire
data/training/drills/*.json     drill sets (kept forever, reveals included)
data/training/jobs/*.json       diagnosis job records
data/training/cache/*.jsonl     EPD-keyed engine caches (append-only)
data/puzzles/puzzles.sqlite     Lichess puzzle mine (300k puzzles, popularity ≥ 70)
data/openings/*.tsv             ECO opening lines
```

All of `data/` is gitignored — your games and profiles never leave this
machine.
