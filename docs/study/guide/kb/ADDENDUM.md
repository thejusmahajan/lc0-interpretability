# Knowledge Base Addendum — gaps and traps found by auditing a study session

**Status:** authoritative, same rules as `KNOWLEDGE_BASE.md`. Every claim below traces to a
file in this repository. Where something is *not* in the corpus, this file says so explicitly
rather than filling the hole.

**Why this file exists.** A study session (`../../STUDY_SESSION_LOG.md`, 2026-08-09/10) produced
answers that were fluent and mostly right, and wrong in eight specific places. Seven of the
eight were not careless — they were the *natural* reading of a corpus that leaves these points
ambiguous or, in one case, states them incorrectly. This file closes those holes so the next
session cannot fall into them. The audit itself is `../../ANSWER_AUDIT.md`.

---

## A. Which network produced which number — the conflation trap

This is the single most misleading thing in the reference shelf.

`ENGINE_REFERENCE.md` §1 labels **BT3** the "Primary Network Weights" and **791556** the
"Diagnostic Network Weights". For the *product* that is true. **For this study corpus it is
backwards.**

| | 791556 | BT3-768x15x24h |
|---|---|---|
| Body | 15 **SE residual blocks**, **192 filters** | 15 **transformer encoder layers**, **24 heads** |
| Embedding / Dmodel | 192 | 768 (encoder DFF 1024) |
| Format | `NETWORK_SE_WITH_HEADFORMAT` | `NETWORK_ATTENTIONBODY_WITH_MULTIHEADFORMAT` |
| Policy head | `POLICY_ATTENTION` | `POLICY_ATTENTION` |
| Value head | `VALUE_WDL` | `VALUE_WDL` |
| Input | `INPUT_CLASSICAL_112_PLANE` | `INPUT_CLASSICAL_112_PLANE` |
| Policy accuracy | 66.72% | 39.59% |

Source: `raw/describenet_791556.txt`, `raw/describenet_bt3.txt`, `ENGINE_REFERENCE.md` §2.

**Every measured number in the book and in the guide's Parts 0–4 came from 791556**, not BT3:

- `book/tools/collect_engine_data.py:27` — `NET_SMALL = ENGINE_DIR / "791556.pb.gz"`, and it is
  the default `weights=` argument of both `lc0_run()` and `lc0_policy_only()`.
- `ch01_what_an_engine_does.tex:359` — "all the real numbers in ... "
- `ch11_attention.tex:310` — "every real number in this book came from the smaller 791556 net"
- `ch07_search_by_hand.tex:21`, `ch06_building_puct.tex:44`, `ch02:86` — same attribution.

**But the guide's Part 5 draws BT3.** `parts/part5_network.tex`, FIG-5.1: "64 square tokens pass
through 15 transformer encoder layers (24 heads each)". FIG-5.4: "averages attention across all
15 layers and 24 heads."

So the guide shows a **transformer** in Part 5 and reports **ResNet** numbers in Parts 0–4, and
says so nowhere on the page. Both nets happen to have **15** of something, which makes the merge
almost impossible to notice.

> **The wrong sentence this produces:** *"15 residual/attention blocks, 768 channels."* That
> describes neither net. 791556 is 15 blocks × **192** filters; BT3 is 15 encoders × **768**
> embedding and has no residual blocks in the ResNet sense.

**Rule:** when a question mixes *search numbers* with *architecture*, name the net for each half.

---

## B. `N` counts the node's own evaluation: `N(node) = 1 + Σ n_a`

`STUDY_SESSION_LOG.md` §6 originally recorded `N(parent) = N(branch1) + N(branch2) + …`. That is
off by exactly one, and the one matters.

**Proof from the simulator** (`book/tools/simulate_search.py`):

```python
root_W, root_N = ROOT_V, 1        # the root starts holding its OWN evaluation as sample #1
```

**Proof from the arithmetic** in `KNOWLEDGE_BASE.md` §2.3. The "root Q before" column is a plain
running mean that includes the root's own network value:

```
iter 2:  (0.97602 + 0.96766) / 2               = 0.97184   ✓ matches the table
iter 3:  (0.97602 + 0.96766 + 0.98598) / 3     = 0.97655   ✓ matches the table
```

If the root's own eval were not a sample, iteration 2 would read 0.96766 and the whole FPU column
would be wrong.

**Proof from the visit counts.** At `go nodes 8` (`KNOWLEDGE_BASE.md` §2.3): Kd6 = 4, Kf6 = 3,
Kf5 = 0, Kd5 = 0. Sum of child visits = **7**. Tree size = **8** = 1 root + 7.

Corrected statements:

```
N(node)   = 1 + n(child_1) + n(child_2) + ...
n(edge a) = number of nodes in the subtree hanging under a, counting the child itself
n(a)      = N(node) - 1 - (sum of the siblings' n)
```

Consequence worth holding onto: the root's `Q` is dragged toward its own first impression by one
sample out of `N`. Early in a search that is a large weight; at 800 nodes it is 1/800.

---

## C. The `c_puct` growth formula has a `+1` in the numerator

`KNOWLEDGE_BASE.md` §2.2 prints the instantiated version:

```
c_puct(N) = 1.745 + 3.894 * ln((N + 38740) / 38739)
```

Note **38740** on top and **38739** underneath. The general form, from
`simulate_search.py`:

```python
def cpuct(n):
    return CPUCT + CPUCT_FACTOR * math.log((n + CPUCT_BASE + 1.0) / CPUCT_BASE)
```

i.e. `c_puct(N) = cpuct_init + cpuct_factor * ln((N + cpuct_base + 1) / cpuct_base)`.

Dropping the `+1` is the commonest recall error, because the published AlphaZero-style formula is
usually written without it. It makes `c_puct(0)` come out as exactly `cpuct_init` instead of the
measured `1.7451` (`KNOWLEDGE_BASE.md` §2.3, iteration 1).

**Measured defaults** (`ENGINE_REFERENCE.md` §3): `CPuct 1.75`, `CPuctFactor 3.89`,
`CPuctBase 38739.00`. The help text rounds to two decimals; the simulator uses the engine's
internal `1.745` / `3.894`, which is why the tables agree to five figures.

**Root has no separate cpuct by default:** `RootHasOwnCpuctParams` default **false**, so
`--cpuct-at-root` and friends exist but are inert until you enable that flag
(`ENGINE_REFERENCE.md` §3, and §5 row "Root CPUCT Parameters").

---

## D. What was switched OFF in every measured run

`collect_engine_data.py:144-157` runs lc0 with:

```
--threads=1  --minibatch-size=1  --max-collision-events=1  --max-collision-visits=1
--out-of-order-eval=false  --task-workers=0  --backend=blas
```

So every number in this corpus comes from a **strictly sequential, unbatched, CPU** search. This
matters twice:

1. **You may not cite this corpus for a claim about batching, GPU parallelism, or virtual loss
   in action.** The mechanisms are described in `ch08_engineering_reality.tex`; they were
   *disabled* when the data was taken. `ch08` says so itself in its `realdata` box.
2. **`MinibatchSize` default is `0`**, not 64 or 256 (`ENGINE_REFERENCE.md` §3: "Set to 0 to use
   a backend suggested value"). `TaskWorkers` default is `-1` (heuristic); `Threads` default `0`
   (backend default). Any specific batch number is a property of a backend, and the corpus does
   not record backend-suggested values.

Also from `ch08`: requested nodes ≠ tree built. Measured: K+P `go nodes 800` → **620** root
visits; startpos 1600 → **1493**; Morphy 400 → **182**.

**That gap is `SmartPruningFactor`, and it was measured on 2026-08-13** — see **§J**. The flag
sits at its default `1.33` in every collected ladder, because `collect_engine_data.py:146-157`
does not override it. Re-run the K+P position with `--smart-pruning-factor=0` and `go nodes 800`
builds a tree of exactly **800**. So the third thing switched off in this corpus is not switched
off at all: smart pruning is switched **on**, everywhere, silently.

---

## E. The priors you see are already temperature-softened

`PolicyTemperature` default is **1.36** (`--policy-softmax-temp`, `ENGINE_REFERENCE.md` §3;
"higher values make priors of move candidates closer to each other"). `collect_engine_data.py`
does **not** override it.

Therefore `P(Kd6) = 45.13%` is the network's policy logits after a softmax at temperature 1.36 —
not the raw softmax. The raw distribution is sharper than what the corpus shows. This is not
recorded anywhere else in the corpus, so it is stated here.

**The flag is `--policy-softmax-temp`. There is no `--policy-temperature`.** (Verified: 91
options in `ENGINE_REFERENCE.md`, and `raw/lc0_help.txt`.)

---

## F. Virtual loss: the mechanism is real, the flag is not

**Corpus-backed (established), `ch08_engineering_reality.tex` §"Virtual loss", L35–64:** when a
path is selected but not yet evaluated, each edge on it gets `N += 1` and `W -= 1` — a fictitious
loss booked so the next thread picks somewhere else. When the real value arrives the fiction is
removed and the true value applied. Worked example there: `N=9, W=7.2, Q=0.800` → `N=10, W=6.2,
Q=0.620`, a drop of 0.18; on an edge with `N=500` the same fiction moves `Q` by 0.004.
**Virtual loss bites where the tree is thin, which is exactly where you want diversification.**

**Not corpus-backed:** `lc0.exe` v0.32.1 exposes **no `--virtual-loss` flag**. `grep -c virtual
raw/lc0_help.txt` returns **0**. What is exposed is collision handling:
`--max-collision-events` (default 917), `--max-collision-visits` (default 80000), and the
`…-scaling-…` family.

> **`GLOSSARY.md`'s "Virtual Loss" entry cited `ENGINE_REFERENCE.md (VirtualLoss)` and
> `--virtual-loss`. Both are fabrications and have been corrected.** Its `ch08:L125` pointer was
> also wrong (L125 is tree reuse). If you are reading a glossary entry, the citation is a claim
> too.

**Collision** (`ch08` §"Collisions"): selection lands on a leaf already queued for evaluation.
The engine can waste the iteration or record it and move on; Leela counts and caps them.

---

## G. Proof beats sampling — the Morphy result, stated correctly

The tempting story is: a hidden move gets one visit, returns a huge `Q`, and `S = Q + U` then
funnels every later visit into it. **That is not what the engine did.** Measured
(`engine_data.json → positions.opera_before_qb8.ladder`, and `KNOWLEDGE_BASE.md` §3):

| Budget | Qb7 (`b3b7`) | **Qb8+ (`b3b8`)** | Rxd7 | engine plays |
|---:|---:|---:|---:|---|
| 400 | 169 | **0** | 4 | Qb7 |
| 1600 | 172 | **3** | 4 | **Qb8+** |
| 6400 | 172 | **3** | 4 | **Qb8+** |

`P(Qb8+) = 1.60%`. `Q(Qb8+) = 1.0` at **n = 3**. `Q(Qb7) = 0.65874` at **n = 172**.

Read the last two rows again: from 1600 to 6400 nodes — **four times the thinking** — *not one
visit count in the table changes.* Qb8+ is played on **3 visits** against a move examined 172
times, and it never accumulates more.

**Mechanism:** `Q = 1.0` here is not an average, it is a **proof** — a forced mate, tracked
separately from sampled values. A proof outranks any amount of sampling, and search stops rather
than continuing to sample a solved subtree. If it had been an ordinary high average, the
`1/(1+n_a)` term would indeed have poured visits in; that is the *other* story, and it is not
this table.

Stockfish d30 confirms: `Qb8+` = mate in 2 (16.Qb8+ Nxb8 17.Rd8#); `Qb7` = +3.92.

---

## H. Declared gaps — do not answer these from general knowledge

These came up in the session and **the corpus does not contain them.** Say "gap", or run the
engine.

| Question | Status |
|---|---|
| What the 112 input planes decompose into (history × piece planes, castling, rule-50, …) | **Gap.** The corpus records only the format name `INPUT_CLASSICAL_112_PLANE` (`describenet`) and, in `ch07:360`, that "the network sees the last several board states as additional input planes". No plane-by-plane breakdown exists anywhere in `docs/study/`. |
| Average branching factor of chess (`b ≈ 31`, `b ≈ 35`) | **Gap.** Not measured or cited in the corpus. Any depth-vs-node-count estimate built on it is outside-corpus arithmetic and must be labelled as such. |
| LC0 C++ source file and symbol names (`search.cc`, `node.h`, `params.cc`, `puct_utility.h`) | **Gap.** No LC0 source tree is present in this repository — only `lc0.exe`. `puct_utility.h` in particular was invented. The *flags* are measured (91 of them); the *source layout* is not verifiable here. |
| Backend-suggested minibatch sizes for a given GPU | **Gap.** See §D. |
| Whether AlphaZero/Leela "rewrote opening theory" (h4-h5 pushes, etc.) | **Out of scope by rule.** This is chess judgement. `START_HERE_PROMPT.md` §2 forbids it regardless of how well known it is. |
| Network training pipelines, `ch17`–`ch19`, appendices A–F, `KLDGainAverageInterval` & friends | **Gap**, already declared in `START_HERE_PROMPT.md` §4. |

---

## I. Small corrections carried from the session

- **Negamax is a frame convention, not the backup rule.** In MCTS the value backed up is
  **averaged**, not maximised (`KNOWLEDGE_BASE.md` §2.6, and §2.3's running means). The negation
  `V_white = -V_black` only re-expresses each value in the local side-to-move frame at every ply.
  The *max* is never taken during backup; it emerges because selection concentrates visits on the
  best move. Saying "every player maximises, with a sign flip" describes negamax minimax search —
  Stockfish — not Leela.
- **The averaging paradox, stated properly.** "1 good child among 9 bad ones drags the average
  down" fails because the samples are **not drawn uniformly**. `S = Q + U` is a biased sampler, so
  `Q = W/N` is a visit-weighted mean whose weights the search itself chose. Measured instance:
  at 800 nodes the K+P root has 377 visits on Kd6 and 240 on Kf6 but **1 each** on the two drawing
  moves (`KNOWLEDGE_BASE.md` §2.4). The two zeros contribute 2 samples out of 620. The estimator is
  deliberately biased toward the max — that is the point of it, not a defect.
- **The value head's sign frame.** A value is always in the frame of the side to move *at that
  node*, and flips at every ply on the way up (`KNOWLEDGE_BASE.md` §2.6). The worked flip:
  leaf after `1.Kf6 Kf8` is `+0.95129` for White; the Black-to-move edge above it receives
  `−0.95129`; the root edge receives `+0.95129`.
- **`V = w − l`**, so `V(root) = +0.97602` with `d = 0.024` unpacks to w ≈ 97.6%, d = 2.4%,
  l ≈ 0.0% (`KNOWLEDGE_BASE.md` §2.1).

---

## J. The `U`/`S` columns, and the one place the selection rule is overruled

**Added 2026-08-13.** Everything here was measured on this machine. `engine_data.json` carries
lc0's own `U`, `S` and `V` columns straight from `--verbose-move-stats` — they are parsed at
`collect_engine_data.py:132-134`, not recomputed by the collector. That makes them an
independent check on the formulas the rest of this corpus asserts, and nothing in the corpus had
used them that way.

### J1. The PUCT and FPU formulas hold across the whole ladder, not just the 8 hand iterations

`KNOWLEDGE_BASE.md` §2.3 verifies `S = Q + U` at `go nodes 8` only. Applying
`U = c_puct(N) · P · sqrt(N) / (1 + n_a)` to the engine's own `U` column, K+P position:

| budget | 8 | 16 | 32 | 64 | 128 | 800 |
|---|---|---|---|---|---|---|
| mean relative error over the 4 moves | 0.02% | 0.02% | 0.03% | 0.03% | 0.04% | 0.21% |

The residual at 800 is the four-figure priors stored in the JSON (`P: 45.13`), not a change of
mechanism. Likewise `Q_FPU = Q(root) − 0.33 · sqrt(ΣP over visited children)` reproduces the
engine's reported `Q` for *unvisited* children exactly — predicted `0.68102` vs engine `0.68103`
at 32 nodes, predicted `0.66400` vs engine `0.66400` at 64.

### J2. The `N` under the square root is `Σ n_a`, and the `U` column proves it on its own

§B derives `N(node) = 1 + Σ n_a` from the running mean. The exploration term gives it
independently: fit the `U` column with `sqrt(Σ n_a)` versus `sqrt(tree N)` and the two differ by
orders of magnitude at small budgets.

```
budget 8    (tree 8,   Σn 7)     Σn_a → 0.020%      tree N → 6.902%
budget 32   (tree 32,  Σn 31)    Σn_a → 0.025%      tree N → 1.606%
budget 800  (tree 620, Σn 619)   Σn_a → 0.206%      tree N → 0.292%
```

Decisive below ~100 nodes; the two hypotheses converge as `N` grows, so do not run this test at
800 alone.

### J3. Smart pruning overrules `S = Q + U` — measured, with a named cause

At `go nodes 800` the engine reports **Kf5 with the highest `S` of all four moves** (`1.20738`,
against `1.01268` for Kd6) while holding **one visit**, and never selects it again. Reproduce
with `book/tools/smart_pruning_probe.py`:

| run | tree built | Kd6 | Kf6 | Kf5 | Kd5 |
|---|---:|---:|---:|---:|---:|
| pruning at default 1.33, `go nodes 800` | **620** | 377 | 240 | **1** | **1** |
| pruning off, budget trimmed to match | 600 | 365 | 230 | **2** | **2** |
| pruning off, `go nodes 800` | **800** | 463 | 332 | 2 | 2 |

Row 2 is the load-bearing one: at *the same tree size* the visit distribution differs, so smart
pruning is not merely stopping the search early — it is **excluding a move from selection while
the search is still running**. With pruning off, Kf5's `S` overtakes the winners' between **440
and 470** child visits and it is picked immediately (`n=1, S=1.007` at 440; `n=2, S=0.695` at
470). The control run continued to 619 child visits without ever picking it: roughly **170
iterations in which the top-ranked move was passed over**.

This is the corpus's concrete instance of `START_HERE_PROMPT.md` §2 — *when the question is what
did the engine do, the measured table outranks the formula.* Before this, the only demonstration
was the Morphy proven mate (§G), which is a different mechanism.

**It is not a proof and not a terminal node.** `Q(Kf5)` moves `0.00000` at `n=1` to `+0.00009` at
`n=2`, which a proven value cannot do. The exact-looking `D: 1.000` / `V: 0.0` is the value head
saturating on a dead-drawn structure, not a certainty marker. **Do not reach for §G to explain
this table.**

### J4. What this costs the rest of the corpus

1. **Every ladder in `engine_data.json` was collected with smart pruning on.** The `S` column of
   any terminal ladder entry can therefore rank first a move the engine had already excluded.
   Reading it as "what the search would pick next" is unsafe corpus-wide, not just at 800 nodes.
2. `nodes_requested` overstates the search at every budget where pruning fired. Quote the tree
   `N` (`ladder.<b>.root.N`), never the budget key.
3. `SmartPruningFactor` default **1.33**, `SmartPruningMinimumBatches` default **0**
   (`ENGINE_REFERENCE.md`:551-552).

### J5. Declared gap this opened

The root's `Q` **falls** monotonically over the ladder — `0.99297` (32) → `0.97595` (64) →
`0.95582` (128) → `0.94195` (800) — with root `D` rising `0.007 → 0.024 → 0.044 → 0.058`. The
search grows steadily *less* optimistic about a position Stockfish calls mate in 12. Two samples
of `0.000` out of 619 cannot account for it. **No explanation in this corpus. Do not invent one.**
