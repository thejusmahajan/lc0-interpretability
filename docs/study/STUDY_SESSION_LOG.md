# Study Companion Session Log & Feedback Tracker

**Session Date:** 2026-08-09
**Answers re-verified:** 2026-08-11 against `guide/KNOWLEDGE_BASE.md`, `guide/kb/ENGINE_REFERENCE.md`,
`guide/kb/ADDENDUM.md`, `book/data/engine_data.json`, `book/tools/simulate_search.py`, `ch01`–`ch16`.
**Workspace File Path:** `docs/study/STUDY_SESSION_LOG.md`
**Goal:** Persistently track all Q&A, student doubts, conceptual breakthroughs, UI constraints, and feedback during the *Inside LC0's Mind* study session to inform future revisions of the visual guide and book chapters.

> **Read this first.** The questions below are preserved exactly as asked. The **answers have been
> re-verified and eight of them corrected** — the original session answered several points from
> general AlphaZero knowledge rather than from this engine's measured output. Corrections are
> marked **[CORRECTED]** and carry a source. Why the drift happened, and what in the corpus invited
> it, is in `ANSWER_AUDIT.md`. New verified material is in `guide/kb/ADDENDUM.md`.
>
> Formulas are plain text throughout — no TeX, per the UI constraint in §2.

---

## 1. Initial Session Verification & Cold-Start Check

- **Corpus Verification:** Confirmed 9 core files (`neural_mcts_visual_guide_v2.pdf`, `CONCEPT_INDEX.md`, `GLOSSARY.md`, `ENGINE_REFERENCE.md`, `KNOWLEDGE_BASE.md`, `ch01`–`ch16`, `engine_data.json`, `children_data.json`, `simulate_search.py`). All excluded legacy directories ignored.
- **Cold-Start Check:** Passed all 5 diagnostic questions strictly using measured engine data.
- **Note added 2026-08-11:** passing the cold-start check certifies that the *files were read*. It
  does not certify that later answers stayed inside them. All five cold-start questions have their
  answers printed in `START_HERE_PROMPT.md`; the questions in §3–§6 below do not. That asymmetry is
  where the drift started — see `ANSWER_AUDIT.md` §1.

---

## 2. Student Pedagogy Shift & Formatting Directives

- **Student Insight:** The student (~2100–2200 Lichess, physics background) noted that pure decimal/numerical recall questions are unhelpful ("I don't know the exact number because I am not an engine").
- **Direction:** Shifted to **Conceptual MCQs** focused on building deep intuitive and mathematical understanding of MCTS structures, data fields, and algorithms.
- **Formatting Constraint:** **No TeX rendering** in student UI window. All math formulas, tree pathways, and equations must be rendered as clean, plain, human-readable text (e.g. `Q = W / N`, `Root (s0) -> edge a -> Node s1`).
- **Pacing Directive:** Do **NOT** automatically advance to the next question. Wait for explicit student confirmation before asking a new question.
- **Clarification added 2026-08-11:** "conceptual, not numerical" is a directive about **what is
  asked**, not about **where answers come from**. Conceptual answers still have to be read out of
  the corpus and cited. The original session read the directive as licence to answer from general
  knowledge, and that is the proximate cause of most errors below.

---

## 3. Conceptual MCQs & Doubts Log

### Question 1: Search Tree Fundamentals (Nodes vs. Edges)
- **Question:** What fundamentally is a node in the search tree, and what role do edges play?
- **Student Answer:** B (Correct).
- **Student Comment/Doubt:** *"For me, node is a board position characterized by a move. This node is evaluated means that this position is given to the manager engine and asked of its valuation and WDL."*
- **Clarification (verified):**
  - A **Node** is a static board position — here, White Ke6/Pe5 vs Black Ke8, FEN `4k3/8/4K3/4P3/8/8/8/8 w - - 0 1` (`KNOWLEDGE_BASE.md` §1).
  - An **Edge** is a move choice leading out of a position (e.g. `Kd6`). The edge is where `P, N, W, Q` live (`FIG-1.2`, Guide §1.2).
  - Evaluating a node means one forward pass of the **neural network**, returning WDL `(w, d, l)` and policy priors `P(a)` (Guide §1.3, `FIG-1.3b`).
  - **[REFINEMENT to your intuition]** Your instinct "a position characterised by a move" is
    almost right and is worth sharpening: the position is **not** fully characterised by the move
    that reached it. Leela's input is a *position with history* — same board reached two different
    ways gets two different evaluations. Measured: FEN `5k2/8/5K2/4P3/8/8/8/8 w - - 2 2` given bare
    evaluates `+0.98838` (d = 0.012); the same board reached by `moves e6f6 e8f8` evaluates
    `+0.95129` (d = 0.049) — **four times the draw probability** (`KNOWLEDGE_BASE.md` §6). So a node
    is a position *plus the path that reached it*. Your phrasing was closer to the truth than the
    textbook one.
  - **[CORRECTED]** The input format is `INPUT_CLASSICAL_112_PLANE`, measured (`describenet`). What
    those 112 planes decompose into is **not documented anywhere in this corpus** — see
    `ADDENDUM.md` §H. Do not accept a plane-by-plane breakdown from a study session; it will be
    from memory.

### Question 2: Evaluation Phase Mechanics
- **Question:** How does LC0 evaluate a newly expanded leaf node in Phase 3?
- **Student Answer:** C (Correct - single neural network forward pass).
- **Context:** Contrasted LC0's single neural pass with historical mid-2000s Go rollouts (random play to termination), which fail in chess due to tactical forcing lines.
- **Note:** the single-forward-pass claim is corpus-backed (Guide §1.3, `ch03` §"Forward pass").
  The Go-rollout history is **outside the corpus** — true, but not sourced here. Flagged, not deleted.

### Question 3: Negamax & Sign Duality
- **Question:** If Black is to move at a node and `Q = -0.95`, what does this mean?
- **Student Answer:** B (Correct - Black is losing / White is winning).
- **Student Doubts:**
  1. *What is Negamax, where does the name come from, and why is it used?*
  2. *What does Q actually mean?*
- **Clarifications:**
  - **Negamax Origin:** In zero-sum games `V_White = -V_Black`. Classical minimax needed separate
    `max` and `min` loops; negamax ("negative maximum") uses `min(x) = -max(-x)` so one loop serves
    both sides, with a sign flip each ply.
  - **[CORRECTED — this is the important one] Negamax in Leela is a *frame convention*, not the
    backup rule.** The original answer said "every player maximizes their score, flipping the sign
    at each ply." That describes **Stockfish**. Leela's backup **averages**; it never takes a max.
    Proof: `KNOWLEDGE_BASE.md` §2.3's "root Q before" column is a plain running mean
    (`(0.97602 + 0.96766)/2 = 0.97184`), and `simulate_search.py` computes `Q = W/N` with no max
    anywhere. The negation only re-expresses each value in the local side-to-move frame
    (`KNOWLEDGE_BASE.md` §2.6). **The max is never computed — it emerges** because selection pours
    visits onto the best move until the mean is dominated by it. Keep these two apart; conflating
    them makes every later question about averaging harder than it needs to be.
  - **Worked sign flip (measured, `KNOWLEDGE_BASE.md` §2.6):** leaf after `1.Kf6 Kf8` is White to
    move, network says `+0.95129` in **White's** frame. The edge above it (Black to move) receives
    `-0.95129`. The root edge (White to move) receives `+0.95129`. Kf6's running average becomes
    `(0.98598 + 0.95129)/2 = 0.968635`.
  - **Q Meaning:** `Q(s,a)` is the empirical mean evaluation of move `a` over all search visits
    through it: `Q = W / N`, bounded `[-1, +1]`, in the frame of the side to move at that node.

### Question 4: Policy Priors P(a) vs. Exploitation Value Q(a)
- **Question:** What is the fundamental difference between Policy Prior `P(a)` and Value `Q(a)`?
- **Student Answer:** B (Correct - `P(a)` is neural prior before search; `Q(a)` is empirical running average built during search).
- **Student Doubts:**
  1. *How is Q(a) a running average? Where does it come from?*
  2. *Why is iteration 4 returning to move 'a' for the second time? Does MCTS have to visit all candidate moves before deepening?*
- **Clarifications:**
  - **Running Average Mechanism:** every walk down `a` evaluates some downstream leaf `V_leaf`,
    adds it to `W(a)` and increments `N(a)`. So `Q(a) = W(a)/N(a)` is the arithmetic mean of all
    leaves discovered under `a`.
  - **Selective Deepening:** MCTS recomputes `S(a) = Q(a) + U(a)` every iteration. It does **not**
    sweep all legal moves before deepening. Measured (`KNOWLEDGE_BASE.md` §2.3): Kf5 and Kd5 sit at
    `n = 0` through all 8 iterations while Kd6 and Kf6 are already 3 plies deep. And from the
    budget ladder (§2.4): they are still unvisited at **64 nodes**.
  - **[CORRECTED — the P values are not raw]** `P(Kd6) = 45.13%` is the policy head's output
    **after** a softmax at temperature 1.36 (`PolicyTemperature` default, flag
    `--policy-softmax-temp`, `ENGINE_REFERENCE.md` §3), because `collect_engine_data.py` does not
    override it. The raw network distribution is **sharper** than the one you have been reading.
    Not previously stated anywhere in the corpus — now in `ADDENDUM.md` §E.

---

## 4. Edge Fields Deep-Dive (P, N, W, Q)

Verified against Guide §1.2 / `FIG-1.2` and `simulate_search.py`.

- **P (Policy Prior):** the network's hunch for a move **before any search** — `Kd6 45.13%`,
  `Kf6 44.23%`, `Kf5 5.38%`, `Kd5 5.26%` (`KNOWLEDGE_BASE.md` §2.1). Static: it never changes
  during a search. Temperature-softened, per Q4 above.
- **N (Visit Count):** how many iterations passed down this edge. Invested effort.
- **W (Accumulated Value):** running sum of leaf values under this edge, `W = V1 + V2 + ... + VN`.
- **Q (Average Value):** `Q = W / N`, in `[-1, +1]`.
- **[ADDED] What `P` is a model of** — this is the part that reframes everything: the policy is
  trained to predict **which move a full MCTS search by this same engine would end up playing**
  (`ch12_two_heads.tex` §"What the policy is a model of"). It is *not* a goodness score and *not* a
  move-quality ranking. It is the engine's compressed memory of its own search behaviour. That is
  why 10.64% of it lands on two moves that throw away a won game.

---

## 5. MCTS Conceptual & Advanced Insights

- **Student Synthesis:** *"So this is basically a big averaging machine of hunch values."*
  — Accurate, and worth keeping. The one addition: it is a **biased** averaging machine, and the
  bias is the whole design (next bullet).

- **Non-Uniform Averaging Paradox Resolved:** The student questioned if 1 winning child node with
  9 bad child nodes would get dragged down by averaging.
  **Resolution (verified):** the samples are not drawn uniformly. `S = Q + U` is a biased sampler,
  so `Q = W/N` is a *visit-weighted* mean whose weights the search chose. Measured instance
  (`KNOWLEDGE_BASE.md` §2.4, 800 nodes): Kd6 = 377 visits, Kf6 = 240, Kf5 = **1**, Kd5 = **1**. The
  two losing moves contribute 2 samples out of 620. **[CORRECTED]** the original wrote "99% of
  visit count" — that figure was invented; the measured concentration is 617/619 ≈ 99.7% on the two
  winning moves, which happens to make the point harder. Use the measured numbers.
  *Physics framing:* this is importance sampling. The estimator is deliberately biased toward the
  max; that is the feature, not the bug.

- **Refutation / Hidden Gem Discovery (`Qb8!!`):** **[CORRECTED — the original answer taught the
  wrong mechanism.]** The original said: a low-prior move is finally visited, returns `V = +0.98`,
  its `Q` dominates `S`, "causing MCTS to channel all subsequent visits into `Qb8`".
  **The measured data says the opposite** (`engine_data.json → positions.opera_before_qb8.ladder`,
  `KNOWLEDGE_BASE.md` §3):

  | Budget | Qb7 (`b3b7`) | **Qb8+ (`b3b8`)** | Rxd7 | engine plays |
  |---:|---:|---:|---:|---|
  | 400 | 169 | **0** | 4 | Qb7 |
  | 1600 | 172 | **3** | 4 | **Qb8+** |
  | 6400 | 172 | **3** | 4 | **Qb8+** |

  `P(Qb8+) = 1.60%`. `Q(Qb8+) = 1.0` at **n = 3**. `Q(Qb7) = 0.65874` at **n = 172**.
  From 1600 to 6400 nodes — four times the thinking — **not one number in that table moves.**
  Qb8+ is played on **3 visits**, beating a move examined 172 times, and it never gathers more.
  **Why:** `Q = 1.0` here is a **proof** (forced mate in 2, Stockfish d30 confirms
  `16.Qb8+ Nxb8 17.Rd8#`), not an average. Proven results are tracked separately and outrank any
  amount of sampling; search stops rather than re-sampling a solved subtree.
  The "high Q floods the subtree with visits" story is real, but it is the story for an ordinary
  high *average* — not for this table. Full treatment: `ADDENDUM.md` §G.

- **Policy Blindness Failure Mode:** The student correctly deduced that if a winning line requires
  2 or 3 consecutive quiet moves each with tiny `P`, the required node count multiplies and MCTS
  fails to find the line on a small budget.
  **Verified, and now with a measured instance:** Qb8+ received **zero** visits at 64, 128 and
  400 nodes, and first appeared somewhere between 400 and 1600 (table above). A mate in two, missed
  for 400 nodes, because `P = 1.6%`.
  **[CORRECTED]** the specific range "800–2,000 nodes" was invented. The measured bracket is
  **400 → 1600**. Also note the compounding claim (`P1 × P2 × P3`) is a sound argument but is
  **not measured** in this corpus — label it as reasoning, not data.

- **High Compute & Logarithmic CPUCT Expansion:** `c_puct` does grow logarithmically with visits,
  widening exploration as the tree fills.
  **[CORRECTED] the formula was missing a `+1`.** Measured
  (`KNOWLEDGE_BASE.md` §2.2, `simulate_search.py`):

  ```
  c_puct(N) = cpuct_init + cpuct_factor * ln( (N + cpuct_base + 1) / cpuct_base )
            = 1.745     + 3.894        * ln( (N + 38740) / 38739 )
  ```

  Note **38740 over 38739**. Defaults measured from the binary: `CPuct 1.75`, `CPuctFactor 3.89`,
  `CPuctBase 38739.00` (`ENGINE_REFERENCE.md` §3). Measured `c_puct` at iteration 1 = **1.7451**.
  With base ≈ 38,739 the growth is glacial: over the entire 8-iteration spine `c_puct` moves from
  1.7451 to 1.7458 (`KNOWLEDGE_BASE.md` §2.3). It is a **millions-of-nodes** knob, not a
  hundreds-of-nodes one.
  **[CORRECTED] the AlphaZero `h4-h5` / "rewrote opening theory" claim is removed.** That is chess
  judgement, forbidden by `START_HERE_PROMPT.md` §2 regardless of how well known it is, and it is
  not in the corpus.

- **GPU Parallelization & Virtual Loss:** LC0 does batch and multi-thread, and cannot evaluate
  everything in parallel. **Virtual loss** is the mechanism that stops parallel threads from all
  picking the same leaf: when a path is selected but not yet evaluated, every edge on it gets
  `N += 1` and `W -= 1` — a fictitious loss — which is removed and replaced by the true value when
  the evaluation returns (`ch08_engineering_reality.tex` §"Virtual loss", L35–64). Worked example
  there: `N=9, W=7.2, Q=0.800` → `N=10, W=6.2, Q=0.620`, a drop of 0.18; on an edge with `N=500`
  the same fiction moves `Q` by 0.004. **Virtual loss bites where the tree is thin** — exactly
  where diversification is wanted.
  **[CORRECTED] three things:**
  1. **`MinibatchSize` default is `0`** ("use a backend suggested value"), not "64/256"
     (`ENGINE_REFERENCE.md` §3). `TaskWorkers` default `-1`; `Threads` default `0`.
  2. **`b = 31` → "1 billion nodes at depth 6" is outside the corpus.** No branching factor is
     measured or cited anywhere in `docs/study/`. (For the record `31^6 ≈ 0.89` billion, so the
     arithmetic was fine — the *input* was unsourced.)
  3. **Every number you have been studying was measured with all of this switched OFF.**
     `collect_engine_data.py:144` runs `--threads=1 --minibatch-size=1 --max-collision-events=1
     --max-collision-visits=1 --out-of-order-eval=false --task-workers=0 --backend=blas`. Strictly
     sequential, unbatched, CPU. So this corpus can describe virtual loss but cannot exhibit it.
     Its visible cost: `go nodes 800` built a tree of **620** root visits; 1600 → 1493; Morphy
     400 → 182 (`ch08`).

- **Custom Selection Equations & Policy Weights in LC0:**
  - *Out-of-the-box controls (all verified in the 91-option dump):* **`--policy-softmax-temp`**
    (default 1.36) — **[CORRECTED]** the original said `--policy-temperature`, which **does not
    exist**; `--noise-epsilon` / `--noise-alpha` (Dirichlet noise on root priors);
    `--cpuct-at-root`, `--cpuct-base-at-root`, `--cpuct-factor-at-root`.
  - **[CORRECTED] the root-specific cpuct flags are inert by default.**
    `RootHasOwnCpuctParams` defaults to **false**, so the root uses the same cpuct as everywhere
    else until you enable it (`ENGINE_REFERENCE.md` §3, §5). Same shape for FPU:
    `FpuStrategyAtRoot` defaults to `same`, so `FpuValueAtRoot = 1.00` has no effect.
  - *Custom code:* lc0 is open-source C++, so the selection rule can be replaced.
    **[CORRECTED] the file names were invented.** `puct_utility.h` does not exist. **No LC0 source
    tree is present in this repository** — only `lc0.exe` — so no source path can be verified from
    here (`ADDENDUM.md` §H). The *flags* are measured; the *source layout* is not.

- **Web-Based Gemini vs. Open-Source LC0 Access Control:** In LC0 the binary, weights and C++
  source run locally and you control 91 UCI flags and, in principle, the selection rule itself. A
  hosted model's decoding loop runs on someone else's servers and is not reachable from a chat
  window. (Not a chess claim; retained as stated.)

- **Dual-Head Forward Pass Architecture (`V` and `P` computation):**
  **[CORRECTED — the architecture given was a merge of two different networks.]** The original said
  "15 Residual / Attention blocks (768 channels)". That describes neither net. Both nets in this
  repo have **15** of something, which is what makes the merge invisible:

  | | **791556** — produced every measured number here | **BT3-768x15x24h** — drawn in Guide Part 5 |
  |---|---|---|
  | Body | 15 **SE residual blocks**, **192 filters** | 15 **transformer encoders**, **24 heads** |
  | Dmodel | 192 | 768 (DFF 1024) |
  | Format | `NETWORK_SE_WITH_HEADFORMAT` | `NETWORK_ATTENTIONBODY_WITH_MULTIHEADFORMAT` |
  | Policy accuracy | 66.72% | 39.59% |

  Source: `describenet` dumps in `kb/raw/`; `collect_engine_data.py:27` (`NET_SMALL = 791556`);
  `ch11_attention.tex:310` ("every real number in this book came from the smaller 791556 net").
  Beware: `ENGINE_REFERENCE.md` calls BT3 "Primary" — true for the *product*, backwards for *this
  study corpus*. Full note: `ADDENDUM.md` §A.

  The pipeline shape itself was right:
  1. *Input:* board → `INPUT_CLASSICAL_112_PLANE` tensor (measured format name; the plane-by-plane
     breakdown is a **declared gap**, `ADDENDUM.md` §H). It includes history — see Q1 above.
  2. *Body:* 15 blocks (ResNet in 791556, transformer encoders in BT3).
  3. *Two heads:*
     - *Policy:* `POLICY_ATTENTION` in **both** nets — attention over square pairs, softmaxed over
       legal moves, then temperature 1.36. Sums to 100%.
     - *Value:* `VALUE_WDL` — a 3-way `(w, d, l)`, with `V = w - l`. Measured root:
       `V = +0.97602`, `d = 0.024` → w ≈ 97.6%, d = 2.4%, l ≈ 0.0%.
     - Both nets also carry a third head, `MOVES_LEFT_V1` (MLH) — omitted from the original answer.

---

## 6. Node & Edge Local N Mechanics

- **Local Scope:** `N` is stored locally on every node and edge across the entire tree. ✔
- **Subtree Count:** the local `n` on an edge `a` equals the number of nodes in the subtree
  hanging under `a`, counting the child itself, across all levels. ✔
- **[CORRECTED] Parent-Child Visit Splitting — the original was off by exactly one, and the one
  matters:**

  ```
  WRONG:    N(parent) = n(b1) + n(b2) + n(b3) + ...
  RIGHT:    N(parent) = 1 + n(b1) + n(b2) + n(b3) + ...
  RIGHT:    n(b1)     = N(parent) - 1 - (sum of the siblings' n)
  ```

  **The `1` is the node's own network evaluation**, which is a sample like any other.
  Three independent confirmations:
  - `simulate_search.py`: `root_W, root_N = ROOT_V, 1` — the root is initialised holding its own
    value as sample #1.
  - the arithmetic in `KNOWLEDGE_BASE.md` §2.3: `(0.97602 + 0.96766)/2 = 0.97184` ✔ and
    `(0.97602 + 0.96766 + 0.98598)/3 = 0.97655` ✔ — both match the printed table. Drop the root's
    own eval and every FPU number in that table breaks.
  - at `go nodes 8`: Kd6 = 4, Kf6 = 3, Kf5 = 0, Kd5 = 0 → child visits sum to **7**, tree size **8**.

  *Consequence:* a node's `Q` is anchored by its own first impression with weight `1/N`. Heavy
  early, negligible at 800 nodes. This is also why `Q_FPU` is computed from the parent's *running*
  `Q`, not from its original `V`.

- **[CORRECTED] "Each search iteration creates effectively 1 new node."** True for the *algorithm*,
  false for the *engine*: collisions and terminal hits mean requested nodes ≠ tree built. Measured
  (`ch08`): `go nodes 800` → **620** root visits; 1600 → **1493**; Morphy 400 → **182**.

---

## 7. Correction ledger (2026-08-11)

| # | Where | Original claim | Verified |
|---|---|---|---|
| 1 | §5 dual-head | "15 Residual/Attention blocks, 768 channels" | 791556 = 15 SE blocks × 192; BT3 = 15 encoders × 768. All measured numbers are 791556. |
| 2 | §6 | `N(parent) = Σ n(children)` | `N(parent) = 1 + Σ n(children)` |
| 3 | §5 cpuct | `ln((N + base)/base)` | `ln((N + base + 1)/base)` |
| 4 | §5 Qb8 | "Q dominates S, all later visits flood into Qb8" | Qb8+ frozen at **3 visits** from 1600 → 6400 nodes; it wins as a **proof**, not by sampling. |
| 5 | §5 flags | `--policy-temperature`, MinibatchSize 64/256 | `--policy-softmax-temp` (1.36); MinibatchSize default **0**. Root cpuct/FPU flags inert by default. |
| 6 | §5 source | `puct_utility.h` / `search.cc` | No LC0 source tree in this repo; file names unverifiable. |
| 7 | §3 Q3 | "every player maximizes, flipping sign" | Leela's backup **averages**; negamax is only a frame convention. |
| 8 | §5 | "99% of visits", "800–2,000 nodes", `b = 31`, AlphaZero h4-h5 | Measured: 617/619; 400→1600; no branching factor in corpus; chess judgement out of scope. |

Also fixed outside this log: `guide/kb/GLOSSARY.md`'s **Virtual Loss** entry cited a
`--virtual-loss` flag and an `ENGINE_REFERENCE.md (VirtualLoss)` option. Neither exists — the word
"virtual" does not appear once in the 91-option dump. Corrected, with the real `ch08` line range.

---

## 8. Session Log: Cross-Entropy Loss, Optimization Dynamics & PyTorch Implementation (2026-08-18)

- **Detailed Companion File:** [`docs/study/STUDY_CROSS_ENTROPY_AND_OPTIMIZATION.md`](file:///c:/Users/Admin/Documents/chess_speak_out_loud/docs/study/STUDY_CROSS_ENTROPY_AND_OPTIMIZATION.md)
- **Key Focus Areas:**
  1. **Cross-Entropy in LC0 (Policy & WDL Value Heads):**
     - **Policy Head:** Categorical cross-entropy over ~1,858 moves against MCTS visit distribution `pi`. Avoids the `p * (1 - p)` vanishing gradient trap of MSE + Softmax, yielding a clean linear update signal `p - pi`.
     - **Value Head (WDL vs Scalar MSE):** LC0 moved from AlphaZero's scalar `[-1, 1]` MSE to 3-way `[P(Win), P(Draw), P(Loss)]` categorical cross-entropy.
     - **Disambiguating 0.00:** Scalar MSE cannot tell a fortress draw (`0% Win, 100% Draw, 0% Loss`) apart from a sharp tactical slugfest (`50% Win, 0% Draw, 50% Loss`). WDL cross-entropy retains the full distribution, enabling search contempt and volatility modeling.
  2. **Optimization Surfaces & Maximum Likelihood Estimation (MLE):**
     - Cross-entropy minimizes KL-divergence / maximizes likelihood of observed data.
     - MSE loss surfaces in classification create flat loss regions and near-zero gradients when wrong, whereas cross-entropy provides continuous, non-zero gradient descent trajectories.
  3. **PyTorch Training Loop Mechanics:**
     - Clarified the canonical 4-step sequence:
       - Step 1: **Forward Pass** (`predictions = model(inputs)`)
       - Step 2: **Calculate Loss** (`loss = criterion(predictions, targets)`) — *where `nn.CrossEntropyLoss()` executes*
       - Step 3: **Backward Pass** (`loss.backward()`) — *computes gradients*
       - Step 4: **Optimizer Step** (`optimizer.step()`) — *updates parameter weights*

