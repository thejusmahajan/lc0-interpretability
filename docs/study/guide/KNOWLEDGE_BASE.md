# KNOWLEDGE BASE — *Inside LC0's Mind: A Visual Guide* (v2, illustrated)

**Status:** authoritative. Everything in this file has been verified against a real artefact in
this repository (a JSON file of measured engine output, a script that reproduces it, or a
compile test that was actually run on this machine on 2026-08-07).

**Companion file:** `kb/ADDENDUM.md` closes gaps found by auditing a real study session — which
network produced which number (§A), why `N(node) = 1 + Σ n` (§B), the `+1` in the `c_puct` numerator
(§C), what was switched off during measurement (§D), the declared gaps (§H), and what smart pruning
does to every ladder in this corpus (§J). **On conflict the addendum wins**, and one point it
corrects is stated ambiguously in this very file: every measured
number here came from **791556** (15 SE-ResNet blocks × 192 filters), *not* from BT3, even though
`kb/ENGINE_REFERENCE.md` labels BT3 "Primary".

**§J applies to every table below.** All ladders were collected with `SmartPruningFactor` at its
default `1.33`, so `nodes_requested` overstates the search (800 → a tree of 620) and a ladder's
terminal `S` column may rank first a move the engine had already excluded from selection.

**Rule for anyone building the guide from this file:** if a number, a chess claim, or a
mechanism is not in this file and not in one of the data files it points at, **you may not put
it in the document.** Ask instead. This project has been burned once by a worker inventing
plausible content (see `LEADER_BIBLE.md`, failure catalog), and a diagram is far more
convincing — and therefore far more dangerous — than a sentence.

---

## 0. The single most important thing on this page

**The existing `neural_mcts_visual_guide.tex` describes a position that does not exist, using
numbers that were never measured.** It must not be carried forward.

| | Current guide (v1) | Reality (measured) |
|---|---|---|
| Position | White Ke4, Pe5; Black Ke7 | White **Ke6**, Pe5; Black **Ke8** |
| FEN | *(none given)* | `4k3/8/4K3/4P3/8/8/8/8 w - - 0 1` |
| Candidate moves | Kd5 70%, Kf5 25%, **e6+ 5%** | Kd6 45.13%, Kf6 44.23%, Kf5 5.38%, Kd5 5.26% |
| Root value | "+0.80" | **+0.97602** |
| Narrative spine | "e6+ is the tempting blunder" | **e6+ is not a legal move at the root** |

In the real position the pawn on e5 **cannot advance**: its own king stands on e6, directly in
front of it. There are exactly **four** legal moves, all king moves. The entire "Iteration 10:
The Tempting Blunder (e6+)" chapter of v1 is fiction and is deleted in v2.

The real position contains a *better* trap than the invented one, and it is documented below.

---

## 1. The subject position (used for the whole spine of the guide)

```
FEN:  4k3/8/4K3/4P3/8/8/8/8 w - - 0 1
White: Ke6, pawn e5      Black: Ke8      White to move
Legal moves (all four):  Kd6, Kf6, Kd5, Kf5
```

**Why this position.** Four legal moves means the entire search tree fits on one page — you can
draw *every* node, not a schematic. It is not a toy: two of the four moves win and two throw the
win away, so the search has real work to do.

**Independent ground truth (Stockfish 16.1, depth 30 — not Leela, not an LLM):**

| Move | Stockfish d30 | Verdict |
|---|---|---|
| **Kd6** | mate in 12 | wins |
| **Kf6** | mate in 18 | also wins, less efficiently |
| Kd5 | `0.00` | **throws the win away** |
| Kf5 | `0.00` | **throws the win away** |

Stockfish PVs (quotable verbatim):
- Kd6: `1. Kd6 Kf7 2. e6+ Kf6 3. e7 Kf5 4. e8=Q Kf4 5. Kd5 Kf5`
- Kf5: `1. Kf5 Ke7 2. Ke4 Ke6 3. Kd4 Ke7`

Source: `docs/study/book/data/engine_data.json` → `positions.kp_endgame.stockfish`.

---

## 2. The measured search — every number the tree figures need

### 2.1 The network's opening statement (one forward pass, zero search)

```
V(root) = +0.97602        d (draw probability) = 0.024
P(Kd6) = 45.13%   P(Kf6) = 44.23%   P(Kf5) = 5.38%   P(Kd5) = 5.26%
```

The policy put **89.36%** of its attention on the two moves that win, and still gave **10.64%**
to two moves that throw away a won game. *The policy is a good guess, not an oracle.* That
sentence is the thesis of the first third of the guide, and it is a measured fact, not a
rhetorical flourish.

### 2.2 The PUCT constants actually used

```
c_puct(N) = 1.745 + 3.894 · ln((N + 38740) / 38739)
Q_FPU     = Q(root) − 0.33 · sqrt( Σ P over visited children )
S(a)      = Q(a) + c_puct(N) · P(a) · sqrt(max(N,1)) / (1 + n_a)
```
`N` = total visits already spent on the root's children. `sqrt(max(N,1))` — so the very first
selection is decided by the priors alone.

### 2.3 The eight iterations — the spine of the animation

Reproduced exactly by `docs/study/book/tools/simulate_search.py`, which cross-checks
itself against `lc0.exe go nodes 8` and prints `MISMATCH` if it ever drifts. **Run it; do not
retype these.** Full per-iteration `Q`, `U`, `S` for all four moves is in its stdout.

| It. | root Q before | Q_FPU | c_puct | Selected | Line walked | Backs up |
|---:|---|---|---|---|---|---|
| 1 | 0.97602 | 0.97602 | 1.7451 | **Kd6** | `Kd6` | +0.96766 |
| 2 | 0.97184 | 0.75015 | 1.7452 | **Kf6** | `Kf6` | +0.98598 |
| 3 | 0.97655 | 0.66460 | 1.7453 | **Kf6** | `Kf6 Kf8` | +0.95129 |
| 4 | 0.97024 | 0.65829 | 1.7454 | **Kd6** | `Kd6 Kd8` | +0.99759 |
| 5 | 0.97571 | 0.66376 | 1.7455 | **Kd6** | `Kd6 Kf7` | +0.99992 |
| 6 | 0.97974 | 0.66779 | 1.7456 | **Kf6** | `Kf6 Kf8 e6` | +0.97860 |
| 7 | 0.97958 | 0.66763 | 1.7457 | **Kd6** | `Kd6 Kd8 e6` | +0.97060 |
| 8 | 0.97846 | 0.66651 | 1.7458 | **Kf6** | *(state only — the chapter stops here)* | — |

Final state after 7 backed-up values, hand arithmetic vs. the engine at `go nodes 8`:

| Move | n (hand) | Q (hand) | n (lc0) | Q (lc0) |
|---|---:|---:|---:|---:|
| Kd6 | 4 | 0.98394 | 4 | 0.98394 |
| Kf6 | 3 | 0.97196 | 3 | 0.97196 |
| Kf5 | 0 | 0.66651 | 0 | 0.66652 |
| Kd5 | 0 | 0.66651 | 0 | 0.66652 |

(The last-digit difference on the unvisited moves is because the priors above are printed to
four figures. Nothing conceptual is missing.)

**Two facts the animation exists to make visible:**

1. **Iteration 2 is the whole of PUCT in one frame.** Kd6 has just returned the *best* measured
   value in the position (0.96766, against a mere guess of 0.75015 for everything else) — and
   the search does **not** pick it again. Its `U` halved the instant it was visited, because the
   denominator went from `1+0` to `1+1`. *Measuring something makes it less urgent to measure
   again.* If the reader takes one thing from the guide, it is this frame.
2. **The search deepened without being told to.** Iterations 1–2 stop at the root's children;
   3–5 reach two plies; 6–7 reach three. Leela has **no depth parameter at all**. Depth is what
   happens when `U` collapses wherever visits pile up.

### 2.4 The refutation — visit counts across the whole budget ladder

Source: `engine_data.json` → `positions.kp_endgame.ladder.<budget>`. This table *is* the
storyboard for the refutation figure family; every column is a frame.

| Budget | Kd6 | Kf6 | Kf5 | Kd5 |
|---:|---:|---:|---:|---:|
| 1 | 0 | 0 | 0 | 0 |
| 2 | 1 | 0 | 0 | 0 |
| 4 | 1 | 2 | 0 | 0 |
| 8 | 4 | 3 | 0 | 0 |
| 16 | 8 | 7 | 0 | 0 |
| 32 | 16 | 15 | 0 | 0 |
| 64 | 31 | 24 | **0** | **0** |
| 128 | 62 | 58 | **1** | **1** |
| 800 | 377 | 240 | **1** | **1** |

With `Q`:

| Budget | Kd6 Q | Kf6 Q | Kf5 Q | Kd5 Q |
|---:|---:|---:|---:|---:|
| 64 | 0.99344 | 0.95335 | *(unvisited, FPU 0.664)* | *(unvisited, FPU 0.664)* |
| 128 | 0.97932 | 0.96332 | **0.000** | **0.000** |
| 800 | 0.95610 | 0.92742 | **0.000** | **0.000** |

**The story:** somewhere between 64 and 128 nodes the two drawing moves each received
**exactly one visit**, returned `Q = 0.000` with draw probability `1.000`, and were **never
visited again in the next 672 nodes**. Two visits out of eight hundred permanently eliminated
half the legal moves in the position — correctly, as Stockfish independently confirms.

The honest caveat that must accompany this (it is in the book and must survive into the guide):
this worked because the *value head* recognised the drawn structure in a single forward pass. In
a position where the refutation is five moves deep, that first visit returns an encouraging
number and the search has to build a subtree to find the truth. **The engine's blind spots are
exactly the positions where both heads are wrong at once** — which is not a rare corner case,
it is the definition of a hard position.

### 2.5 Child and grandchild nodes (needed to draw depth 2 and 3)

`docs/study/book/data/children_data.json`

| Node | FEN | Ladders available |
|---|---|---|
| after Kf6 | `4k3/8/5K2/4P3/8/8/8/8 b - - 1 1` | 1, 16 |
| after Kd6 | `4k3/8/3K4/4P3/8/8/8/8 b - - 1 1` | 1, 16 |
| after Kf5 | `4k3/8/8/4PK2/8/8/8/8 b - - 1 1` | 1, 16 |
| after Kd5 | `4k3/8/8/3KP3/8/8/8/8 b - - 1 1` | 1, 16 |
| after Kd6 Kd8 | `3k4/8/3K4/4P3/8/8/8/8 w - - 2 2` | 1 |
| after Kf6 Kf8 | `5k2/8/5K2/4P3/8/8/8/8 w - - 2 2` | 1 |

Black's priors at the Kf6 node: **Kf8 52.05%, Kd7 25.89%, Kd8 22.05%**; the node's own value is
`−0.98168` (Black's frame).

### 2.6 The sign convention — get this wrong and every arrow in the book lies

Values are always **in the frame of the side to move at that node**. A value backing up the tree
flips sign at every ply.

Worked example, iteration 3 (this exact walk-through belongs in the figure):

- New leaf = the position after `1.Kf6 Kf8`, **White** to move. Its network value is
  `+0.95129` **from White's point of view**.
- Edge (Kf6-node → Kf8), where **Black** is to move, receives `−0.95129` — Black does not like it.
- Edge (root → Kf6), where **White** is to move, receives `+0.95129`.
- Kf6's running average becomes `(0.98598 + 0.95129)/2 = 0.968635`.

Draw the flip. Do not narrate it and hope.

---

## 3. The second worked position: the moment the engine changes its mind

`positions.opera_before_qb8` — Morphy–Duke of Brunswick & Count Isouard, Paris 1858, before
16.Qb8+.

```
FEN: 4kb1r/p2n1ppp/4q3/4p1B1/4P3/1Q6/PPP2PPP/2KR4 w k - 0 16
46 legal moves.
Stockfish d30: Qb8+ = mate in 2 (16.Qb8+ Nxb8 17.Rd8#).  Qb7 = +3.92.
```

Visit counts as the budget grows:

| Budget | Qb7 | **Qb8+** | Rxd7 | Qb5 | Qc3 | engine plays |
|---:|---:|---:|---:|---:|---:|---|
| 64 | 26 | **0** | 1 | 1 | 1 | Qb7 |
| 128 | 53 | **0** | 1 | 1 | 1 | Qb7 |
| 400 | 169 | **0** | 4 | 2 | 2 | Qb7 |
| 1600 | 172 | **3** | 4 | 2 | 2 | **Qb8+** |
| 6400 | 172 | **3** | 4 | 2 | 2 | **Qb8+** |

`P(Qb8+) = 1.60%` — the policy head barely considered the mate. `Q(Qb8+) = 1.0` at n=3;
`Q(Qb7) = 0.65874` at n=172.

**Three things this single table proves, all of them central to this project:**

1. **A move played on 3 visits beat a move examined 172 times.** Visit count is normally the
   search's considered opinion — *except* when a value is a **proof** rather than an average.
   Engines track proven wins separately, and a proof outranks any amount of sampling.
2. **The instinct nearly missed a mate in two.** 1.60% of policy attention on a forced mate.
   This is the measured, undeniable version of the "prior override" idea the project chases —
   and unlike the layer-8 probe story (§5), it needs no hypothesis at all.
3. **Between 400 and 1600 nodes the engine changed its mind, and then froze.** 1600 → 6400 is
   four times the thinking for zero change. Search stops when it has a proof.

---

## 4. Two more positions available if a figure needs them

| key | position | note |
|---|---|---|
| `startpos` | initial position | e4 532 / d4 451 / Nf3 230 visits at 1600 nodes — good for "what a normal fan of visits looks like" |
| `opposition_draw` | `8/8/4k3/4P3/4K3/8/8/8 w - - 0 1` | White Ke4 Pe5 vs Ke6. **All five moves draw**; visits split almost evenly (172/171/155/152/148). The visual opposite of the K+P position: when nothing matters, the search spreads out. A superb contrast frame. |

---

## 5. The confidence tiers — what is measured, what is published, what is ours

The book already has a four-tier apparatus (`\begin{established}`, `\begin{researchfinding}`,
`\begin{hypothesis}`, `\begin{realdata}`). **The visual guide must use it too, and colour-code
figures accordingly**, because the guide's later chapters are much softer than its early ones
and the reader has no way to tell from a picture.

| Claim | Tier | Notes |
|---|---|---|
| Everything in §1–§4 above | **real engine output** | measured on this machine, reproducible |
| PUCT / FPU formulas and constants | **established** | LC0 source; reproduced by our simulator |
| BT3 is a 15-layer transformer encoder, 768-dim tokens, 24 heads | **established** | `backend/neural_vision.py` hooks `encoder<N>/mha` |
| Middle layers of a chess network encode look-ahead 3–7 plies | **published research finding** | see `docs/research_learned_lookahead.md` — cite it, don't restate it as ours |
| "Layers 1–3 = pieces, 4–7 = geometry, 8–11 = look-ahead, 12–15 = strategy" | ⚠ **ILLUSTRATIVE ONLY** | We have **not** measured this layer-by-layer division. v1 states it as fact. In v2 it must be drawn as a labelled *cartoon* with the caption saying so. |
| The "Tal moment": layer 8 sees a winning sac, the final layer talks itself out of it | ⚠ **THIS PROJECT'S HYPOTHESIS — not verified** | We have **no** measured example. v1 asserts "the linear probe reveals Layer 8 internally calculates a 95% winning attack" with invented numbers. **Delete those numbers.** Draw the *shape* of the hypothesis and label it purple/hypothesis. |
| Attention maps are currently averaged over all layers and heads, hence diffuse | **established (our own system)** | stated in `GEMINI_DESIGN_SESSION_BRIEF.md` §2 |

**If you want a measured stand-in for the "suppressed win" story, use the Morphy table in §3.**
It says the same thing — the instinct nearly missed a mate — with real numbers and no hypothesis.
That substitution is the single biggest honesty upgrade available in this document.

---

## 6. A real, measured trap worth its own figure: the FEN-vs-history effect

The same board, asked two different ways, gets two different answers:

| How the position was given to the engine | V | d |
|---|---:|---:|
| `position fen 5k2/8/5K2/4P3/8/8/8/8 w - - 2 2` | +0.98838 | 0.012 |
| `position fen 4k3/… w - - 0 1 moves e6f6 e8f8` | **+0.95129** | **0.049** |

Same 32 squares, same side to move, same rights — evaluation differs by 0.037 with **four times
the draw probability**. Leela's input is not a position, it is a **position with history**: the
network sees the last several board states as extra input planes. Given a bare FEN the engine
fabricates a history by repeating the current position, and a repeated position is evidence of
shuffling.

The second number is the one the search actually used (it matches iteration 3 exactly).

This has a live consequence for the product: anywhere the backend evaluates by handing lc0 a
bare FEN, it is asking a slightly different question from the one the engine answers in a game.
Largest where repetition matters — fortresses, perpetuals, drawn endgames.

---

## 7. Data and tool inventory (paths are repo-relative)

| Path | What it is |
|---|---|
| `docs/study/book/data/engine_data.json` | measured ladders for 6 positions × many node budgets, plus Stockfish ground truth. **223 KB. The primary source of truth.** |
| `docs/study/book/data/children_data.json` | child and grandchild ladders for the K+P tree (depth 2–3) |
| `docs/study/book/data/corpus_stats.json` | corpus statistics |
| `docs/study/book/tools/collect_engine_data.py` | regenerates `engine_data.json` from `engine/lc0.exe` |
| `docs/study/book/tools/collect_children.py` | regenerates `children_data.json` |
| `docs/study/book/tools/simulate_search.py` | **reproduces the 8 iterations by hand arithmetic and refuses to disagree with the engine.** Note it replays *measured* leaf values (`ITERATIONS`, L28-36) — it validates the selection rule, not the evaluation |
| `docs/study/book/tools/smart_pruning_probe.py` | control vs `--smart-pruning-factor=0` on the K+P position; the experiment behind `kb/ADDENDUM.md` §J |
| `docs/study/book/preamble.tex` | the book's shared preamble: colours, tcolorbox tiers, xskak defaults |
| `docs/study/book/chapters/ch07_search_by_hand.tex` | the prose version of what the tree animation must show |
| `docs/study/book/chapters/ch09_reading_a_tree.tex` | how to read a tree — the guide's figures should agree with it |
| `docs/study/guide/tikz/mctsviz.sty` | **the drawing macros. Compile-tested. Use these; do not hand-roll TikZ.** |
| `docs/study/guide/tikz/_probe.tex` | the compile test that proves the macros work |

Regenerating engine data requires the `cszero` conda environment and `engine/lc0.exe` with
`791556.pb.gz` (see `HOW_TO_RUN.md`). **You should not need to regenerate anything** — the JSON
is committed and sufficient.

---

## 8. Toolchain facts, verified on this machine 2026-08-07

- **TeX Live 2019**, `pdflatex` at `C:/texlive/2019/bin/win32/pdflatex`. Also `lualatex`,
  `xelatex`, `latexmk`.
- Installed and confirmed present: `tikz`, `tcolorbox`, `xskak`, `chessboard`, `skak`, `forest`,
  `standalone`.
- `pdftoppm` is available for rendering pages to PNG (useful for checking your own figures).
- Build the guide with **`pdflatex` run twice** (TOC + `\ref`s). `latexmk -pdf` also works.

### 8.1 Three TeX traps that were hit and solved while building the macros

1. **`\chessboard` inside a TikZ node** fails with the misleading error
   *"A node must have a (possibly empty) label text"* unless the FEN is brace-wrapped in the key
   list (`setfen={<fen>}`) **and** the board is wrapped in `\mbox{…}`. `\vgboardnode` does both.
2. **Passing a coordinate to a macro.** `\newcommand{\x}[1]{\node at (#1) …}` called as
   `\x{(0,0)}` silently produces `at ((0,0))` and the same misleading error. The macros here
   take the coordinate **with its own parentheses**: `\vgboardnode{b}{(0,0)}{…}{11pt}`.
3. **`pgfstyle=color` + `markfields` DELETES PIECES.** Tinting the dark squares of the K+P
   position made the **e5 pawn disappear** from the diagram — no error, no warning, just a
   different position on the page from the one the numbers describe. **Never fill a square.**
   Outline it: `pgfstyle=border, color=PitfallRed, markfields={e7}`. Move arrows are safe:
   `pgfstyle=straightmove, color=GoldPath, arrow=to, markmoves={e6-f6}`.

Boards inside tree nodes must be **at least 11pt** (`boardfontsize=11pt`); below that the
default hatched dark squares turn to mush. Standalone diagrams: 15–19pt.

---

## 9. Who the reader is

A ~2100–2200 Lichess player. A serious student, not a professional and not a programmer. He
**works by visualisation** — this entire rewrite exists because v1 was a wall of text about a
tree and he needs to *see* the tree. Assume he can read chess notation fluently and has never
seen a PUCT formula. Assume he will not read a paragraph that a picture could have carried.

He values depth over polish and honesty over comfort, and he has explicitly said he is "not
interested in shiny stuff." Decoration is a cost, not a feature. Every mark on the page must
carry information.
