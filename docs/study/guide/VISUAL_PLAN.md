# VISUAL PLAN — *Inside LC0's Mind: A Visual Guide* (v2, illustrated)

Companion to `KNOWLEDGE_BASE.md` (what is true) and `LATEX_SPEC.md` (how to draw it).
This file is **what to draw, in what order, and what changes between one picture and the next.**

---

## 1. The governing idea

> The reader works by visualisation. He does not want a description of a search tree.
> He wants **the tree**, and then he wants to watch it change, one small change at a time,
> with a sentence telling him which change to look at.

Three rules follow, and they are not stylistic preferences — they are the whole design:

**Rule 1 — One canvas per idea.**
An idea gets *one* picture, drawn *once*, at *fixed coordinates*. Every subsequent step in the
explanation redraws that same picture with something changed. A node that exists in frame 3 sits
at exactly the same coordinates in frame 8. Nothing ever slides, re-flows, or re-scales between
frames of a family. The reader's eye must be able to lock onto a spot on the page and see only
the thing that moved.

**Rule 2 — At most two changes per frame.**
If three things change, split it into two frames. Eight small frames beat three clever ones. Page
count is cheap; a reader losing the thread is not.

**Rule 3 — Every frame has a one-line "what changed", and it names the change.**
Not "the search continues" — *"Kd6 was just measured, so its `U` halved and it lost the lead
despite having the best score."*

**Corollary — the text is the caption now.** Prose in v2 exists to point at a picture. If a
paragraph does not refer to something visible, cut it or draw it.

---

## 2. Physical layout

- **A4, one figure family per spread** where possible. Consecutive frames of a family go on the
  same page or on facing pages — never separated by a page turn that hides the previous frame.
- Frame anatomy, top to bottom:

```
  ┌──────────────────────────────────────────────────┐
  │  Iteration 3                        (frame title)│
  │                                                  │
  │              [ THE TREE  ]                       │   ← the canvas, fixed coords
  │                                                  │
  │              [ THE S-BARS ]                      │   ← the decision, same 4 columns
  │                                                  │
  │  ▸ What changed: Kf6 now has a child. Selection   │   ← one line, names the change
  │    did not stop at the root — it recursed.       │
  └──────────────────────────────────────────────────┘
```

- The **S-bar strip is always directly under the tree**, with its four columns in the **same
  left-to-right order as the four child nodes above them** (Kd6, Kf6, Kf5, Kd5). The reader must
  be able to drop a vertical line from a node to its bar.
- **Colour is meaning, never decoration.** The grammar is defined once in `mctsviz.sty` and
  printed as a legend on the first tree page (`\vglegend`). Nothing may use a colour outside it.

---

## 3. The figure inventory

Numbering is `FIG-<part>.<n>`; frames within a family are lettered `a, b, c…`.
"Tier" is the honesty tier from `KNOWLEDGE_BASE.md` §5 and drives the frame colour.

### PART 0 — How to read these pictures

| ID | Frames | Content | Tier |
|---|---|---|---|
| FIG-0.1 | 1 | **The legend.** `\vglegend` verbatim, full width, with a paragraph promising the reader that these meanings never change. | — |

### PART 1 — The two partners

| ID | Frames | Content | Tier |
|---|---|---|---|
| FIG-1.1 | **4** | **The handshake.** Same three boxes throughout: `MANAGER (lc0.exe)`, a board, `ARTIST (BT3 network)`. (a) Manager holds the board, Artist idle. (b) board slides to Artist — one gold arrow appears. (c) Artist returns **two index cards**: a *policy card* and a *WDL card*. (d) Manager writes the cards into a tree node. Nothing moves between frames; each frame adds exactly one arrow or one card. | established |
| FIG-1.2 | 1 | **Anatomy of a node** — one large node, exploded, with a callout on each field: the move, `P` (the Artist's prior), `n` (visits), `Q` (running average of what came back), `V` (this node's own one-look value), `U` (curiosity bonus), `S = Q + U`. This is the reference figure; every later figure's node is a shrunk copy of it. | established |
| FIG-1.3 | **2** | **The two cards for our actual position.** Board on the left (15pt, `4k3/8/4K3/4P3/8/8/8/8 w - - 0 1`). (a) both cards face-down. (b) face-up with the **real** numbers: policy 45.13 / 44.23 / 5.38 / 5.26 and `V = +0.97602, d = 0.024`. Caption must land the thesis: *89.36% of the instinct went to the two winning moves — and 10.64% went to two moves that throw the game away.* | **real data** |

### PART 2 — The growing tree *(the heart of the document — budget your effort here)*

**The canvas.** Defined once and reused by every frame FIG-2.0 → FIG-2.8:

```
                          ┌───────────────┐
                          │     ROOT      │            y = 0
                          │  n=…  Q=…     │
                          └───────────────┘
        ┌────────┬────────────┼────────────┬────────┐
   ┌────┴───┐┌───┴────┐  ┌────┴───┐  ┌─────┴──┐
   │  Kd6   ││  Kf6   │  │  Kf5   │  │  Kd5   │      y = −2.2
   └────────┘└────────┘  └────────┘  └────────┘
   x = −4.2   x = −1.4    x = +1.4    x = +4.2
        │         │
   ┌────┴───┐┌────┴───┐                                y = −4.4   (depth 2)
   │  Kd8   ││  Kf8   │        …                       (Kf7 etc. appear as needed)
   └────────┘└────────┘
        │         │
   ┌────┴───┐┌────┴───┐                                y = −6.6   (depth 3)
   │   e6   ││   e6   │
   └────────┘└────────┘

   [ S-BAR STRIP: four columns, same x order as the four children ]
```

Reserve the **right-hand margin as the backpropagation lane** — value arrows swing out there so
they never cross a node. (Rule: if the walked path is on the left half, bend the return arrow
right; if on the right half, bend it left.)

| ID | Frames | What is on the canvas | What changed vs. previous |
|---|---|---|---|
| FIG-2.0 | 1 | Root solid; **all four children dashed-grey** (never visited); edge widths ∝ prior; S-bars all equal `Q` (=0.97602 FPU) with wildly different `U`. | — the starting state |
| FIG-2.1 | 1 | Iteration 1. Gold path root→Kd6. Kd6 turns solid, gets a green "new" burst. Backprop arrow `+0.96766`. | *Every `Q` is identical, so the ranking is purely the priors. The tallest bar is Kd6 and it wins by a nose over Kf6 — 1.76358 vs 1.74788.* |
| FIG-2.2 | 1 | Iteration 2. Gold path root→Kf6. Kf6 turns solid. | **The most important frame in the book.** *Kd6 has the best measured score in the position and is NOT chosen.* Its `U` halved the moment it was visited (denominator `1+0` → `1+1`); the dashed nodes' `Q` fell from 0.97602 to the FPU value 0.75015. Draw a small red down-arrow on the three dashed bars and a red "÷2" tag on Kd6's `U` segment. |
| FIG-2.3 | 1 | Iteration 3. Gold path goes **two levels**: root→Kf6→**Kf8** (new node at depth 2). | *Selection did not stop at the root. It recursed.* First appearance of the second row. |
| FIG-2.4 | 1 | Iteration 4: root→Kd6→Kd8. | Second row now has a node on both sides. |
| FIG-2.5 | 1 | Iteration 5: root→Kd6→Kf7. | Kd6's subtree is wider than Kf6's. |
| FIG-2.6 | 1 | Iteration 6: root→Kf6→Kf8→**e6** (depth 3). | *Third row appears. Nobody told it to go deeper.* |
| FIG-2.7 | 1 | Iteration 7: root→Kd6→Kd8→e6. | |
| FIG-2.8 | 1 | Iteration 8 — state only, no expansion drawn. Add the verification panel: hand `n`/`Q` beside `lc0.exe go nodes 8`, identical to five decimals. | *You have just run Leela's search by hand.* |
| FIG-2.9 | 1 | **The whole search on one line.** Eight thumbnails of the canvas at ~25% scale in a row, no numbers, edge widths only. The reader should see the tree *grow* like a time-lapse. | — |
| FIG-2.10 | **3** | **The sign flip** (iteration 3). Two boards + the three edges of the path. (a) new leaf after `1.Kf6 Kf8`, White to move, `V = +0.95129` — White's view. (b) the edge into it, where **Black** is to move, receives `−0.95129`. (c) the root edge, where **White** is to move, receives `+0.95129`; Kf6's average becomes `(0.98598+0.95129)/2 = 0.968635`. Colour the "whose point of view" label differently in each frame. | **real data** |
| FIG-2.11 | 1 | **Depth was never requested.** Reuse the FIG-2.9 thumbnails, annotated: iterations 1–2 reach depth 1, 3–5 depth 2, 6–7 depth 3. One sentence: *Leela has no depth parameter at all.* | established |

### PART 3 — Why the search abandons a move

| ID | Frames | Content | Tier |
|---|---|---|---|
| FIG-3.1 | **3** | **The refutation.** The same canvas at three budgets. (a) **64 nodes**: Kd6 n=31, Kf6 n=24; Kf5 and Kd5 still dashed at n=0, their FPU `Q` drifted down to 0.664 while their `U` crept up. (b) **128 nodes**: Kd6 62, Kf6 58 — and both dashed nodes **turn red**: `n=1, Q=0.000, d=1.000`. (c) **800 nodes**: Kd6 377, Kf6 240 — and the red nodes are **still at n=1**. *Two visits out of eight hundred permanently eliminated half the legal moves.* | **real data** |
| FIG-3.2 | 1 | **The race that caused it.** Line chart, x = total root visits `N` (log scale, 1→800), y = `S`. Two curves: the leaders' `S` decaying toward ~1.0, and `S(Kf5)` climbing as `√N` grows with `n_a` stuck at 0. Mark the crossing between 64 and 128. Then a red step down to `S≈0` the moment it is measured. | computed from measured priors — label it as such |
| FIG-3.3 | 1 | **The contrast: when nothing matters.** `opposition_draw` (`8/8/4k3/4P3/4K3/8/8/8 w - - 0 1`), all five moves draw, visits split 172/171/155/152/148. Same canvas grammar, five near-identical bars. Put it on the page facing FIG-3.1c. *A flat tree is the engine telling you the position is dead.* | **real data** |
| FIG-3.4 | 1 | **The honest caveat**, drawn not just written: two side-by-side cartoon subtrees — "refutation visible in one look" (value head catches it, 1 visit) vs. "refutation five moves deep" (first visit returns an encouraging number, search must build a subtree). Caption: *the engine's blind spots are the positions where both heads are wrong at once.* | established / cartoon — mark it |

### PART 4 — Reading what the engine decided

| ID | Frames | Content | Tier |
|---|---|---|---|
| FIG-4.1 | **5** | **The moment the engine changed its mind.** Morphy position (board at 15pt with `pgfstyle=border` on the mating squares). Paired bars per move — visits (solid) and `Q` (outline) — at budgets 64 / 128 / 400 / **1600** / 6400. Qb8+ is *absent* through frame (c) at 400 nodes, then appears in frame (d) with **n=3, Q=1.000**, and the `bestmove` label flips from `Qb7` to `Qb8+`. Frame (e) at 6400 is **identical** to (d): four times the thinking, zero change. | **real data** |
| FIG-4.2 | 1 | **Proof beats sampling.** Two nodes side by side: `Qb7  n=172  Q=0.659` and `Qb8+  n=3  Q=1.000  [PROOF]`. Below, the board with the mate drawn: `16.Qb8+ Nxb8 17.Rd8#`. Caption: visit count is the search's considered opinion — *unless* a value is a proof rather than an average. | **real data** |
| FIG-4.3 | 1 | **Policy proposes, value disposes.** One horizontal 100% bar of the root policy for the K+P position: 89.36% blue (the two winning moves), **10.64% red** (the two that throw the game away). Underneath, the value head's verdict on that red slice: `0.000`. | **real data** |
| FIG-4.4 | 1 | **Which number chooses the move.** Decision diagram: rank by **visits**; report `Q` alongside; a move with excellent `Q` and small `n` is **a question, not an answer** — except when `Q` is a proof. This is the figure the product's own reporting must obey. | established |

### PART 5 — Inside the network *(softer ground — the drawing must say so)*

Every figure in this part carries a **visible tier frame** (purple = our hypothesis, teal = real
data) and a caption that states what has and has not been measured. This is not hedging; it is
the difference between the guide being trustworthy and being another confident-sounding artefact.

| ID | Frames | Content | Tier |
|---|---|---|---|
| FIG-5.1 | 1 | **The conveyor belt.** 64 squares → 64 tokens of 768 dimensions → 15 encoder layers (24 attention heads each) → two heads: policy (~1858 move candidates) and WDL. The *architecture* is established fact. The **layer-role labels** ("pieces / geometry / look-ahead / strategy") are **not measured** — draw them as a faded cartoon overlay with the caption saying explicitly that we have not measured this division. v1 asserted it as fact; that is corrected here. | established (architecture) + **cartoon** (roles) |
| FIG-5.2 | **2** | **The probe, as a hypothesis.** (a) a forward pass with a tap at a middle layer. (b) the shape of the "suppressed win" idea: middle layers register a winning sacrifice, the final policy suppresses it. **Draw the shape, print no numbers.** v1's "Layer 8 internally calculates a 95% winning attack" is invented — delete it. Purple hypothesis frame, title: *this project's hypothesis — not yet verified.* | **hypothesis** |
| FIG-5.3 | 1 | **What we can actually show today.** Immediately after 5.2, in a teal real-data frame: Morphy's `P(Qb8+) = 1.60%` on a **forced mate in two**. The instinct nearly missed it — measured, no probe required. Caption should draw the line explicitly: *this is the measured cousin of the hypothesis above.* | **real data** |
| FIG-5.4 | 1 | **Why our attention maps are diffuse today.** Two panels: attention averaged over all 15 layers × 24 heads (a smear) vs. what a single layer/head would look like (a claim we cannot yet make — draw it hollow). Honest about the current limitation of our own tooling. | established (ours) + hypothesis |

### PART 6 — Traps for anyone building on this

| ID | Frames | Content | Tier |
|---|---|---|---|
| FIG-6.1 | **2** | **The same board is not the same question.** (a) two identical diagrams side by side. (b) their evaluations appear: bare FEN `+0.98838, d=0.012` vs. FEN-with-moves `+0.95129, d=0.049`. A history filmstrip under each explains why: given a bare FEN the engine invents a history by repeating the position, and a repeated position looks like shuffling. Note which number the search actually used. | **real data** |
| FIG-6.2 | 1 | **Closing summary card.** What each on-screen element of the product means, mapped to the figures: policy arrows → FIG-1.3; visit-weighted variations → FIG-2.9; refuted moves → FIG-3.1; "excellent Q, few visits" → FIG-4.4. | — |

---

## 4. Frame-diff discipline (the acceptance test for the whole document)

Before any frame is accepted, the author answers these five questions **in a comment above the
figure source**:

1. Which figure is this a mutation of? *(family + previous frame ID)*
2. What are the ≤2 things that changed?
3. Did anything **move** that should not have? *(coordinates must be identical — diff the source)*
4. Where does the reader's eye go first, and is that where the change is?
5. Which measured number in `KNOWLEDGE_BASE.md` does each printed digit come from?

A frame that cannot answer #5 for every digit on it does not go in the document.

---

## 5. What v1 contributed, and what happens to it

*(v1 has since been deleted from the repo. This table is now the only record of it, and is
sufficient — nothing in v1 needs to be read again.)*

| v1 chapter | Fate in v2 |
|---|---|
| Ch. 1 "The Two Partners" | **Keep the metaphor** (Artist / Manager) — it is good and the reader already has it. Convert to FIG-1.1 + FIG-1.2. |
| Ch. 2 "Walking Down the Tree" | **Rebuild on the real position.** Invented board, invented priors, invented +0.80. Replaced by PART 2. |
| Ch. 3 "Refutations & Pivots" (the `e6+` story) | **Delete.** `e6+` is not legal at the root. Replaced by PART 3, which tells a *truer* version of the same story. |
| Ch. 4 "Linear Probes" / "The Tal Moment" | **Keep as hypothesis, strip the fake numbers.** Becomes PART 5, with FIG-5.3 as the measured counterpart. |
| Closing summary | Becomes FIG-6.2. |

The prose voice of v1 is good — plain, concrete, no formula-worship. Keep the voice. Replace the
content it was describing.

---

## 6. Effort allocation

If time runs short, ship in this order. PART 2 alone, done properly, is worth more than all the
other parts done thinly.

1. **PART 2** (the growing tree) — the reason this document is being rewritten.
2. **PART 3** (refutation) — the payoff of PART 2.
3. **PART 0 / PART 1** — cheap, and PART 2 is unreadable without the legend.
4. **PART 4** — the Morphy data is spectacular and nearly free (the numbers are already measured).
5. **PART 6** — small, high value to the engineering side.
6. **PART 5** — last, because it is the softest ground and the easiest place to accidentally lie.
