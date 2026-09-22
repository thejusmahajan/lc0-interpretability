# HEADSTART — ten minutes to reload everything

Built from the questions you actually asked, in the order you asked them. Plain text formulas.
Numbers only where the number *is* the point. Sources: `guide/KNOWLEDGE_BASE.md`,
`guide/kb/ADDENDUM.md`, `guide/kb/ENGINE_REFERENCE.md`.

---

## The one sentence

**Leela is a biased averaging machine.** The neural net supplies hunches; the search averages
them; and the averaging is *deliberately unfair* — that unfairness is the entire algorithm.

Your own line was "a big averaging machine of hunch values." Add one word — **biased** — and you
have it.

---

## The board everything is measured on

```
4k3/8/4K3/4P3/8/8/8/8 w - - 0 1        White Ke6, Pe5   Black Ke8
```

Four legal moves, all king moves — the pawn cannot advance, its own king is standing on e6.
Two of the four win, two throw the win away. That is why this position: the whole tree fits on a
page, and the search still has real work to do.

```
V(root) = +0.97602   (d = 0.024, so w ~ 97.6%, l ~ 0%)
P:  Kd6 45.13%   Kf6 44.23%   Kf5 5.38%   Kd5 5.26%
Stockfish d30:  Kd6 = #12   Kf6 = #18   Kd5, Kf5 = 0.00
```

**The thesis of the whole document is in those two lines:** the policy put 10.64% of its attention
on two moves that throw away a won game. *The policy is a good guess, not an oracle.*

---

## Q: What is a node? What is an edge?

**Node = a position. Edge = a move out of it.** All four numbers `P, N, W, Q` live on the *edge*,
not the node.

Your instinct was "a position characterised by a move." **Sharpen it, don't drop it — you were
closer than the textbook.** A node is a position *plus the path that reached it*. Measured: the
same 32 squares given as a bare FEN evaluates `+0.98838` (d = 0.012); reached by actual moves it
evaluates `+0.95129` (d = **0.049**). Four times the draw probability, same board. Leela's input
carries history, and a repeated position looks like shuffling.

---

## Q: What does "evaluate" mean?

**One forward pass. That's the whole of it.** No rollouts, no playing to the end. The net returns
`(w, d, l)` and a prior for every legal child at once. `V = w - l`.

*Physics framing:* it is a learned closed-form estimate of the integral, replacing Monte Carlo
sampling of it. Old Go engines sampled the integral by random playout; Leela regresses it.

---

## Q: What is negamax, and what is Q?

`Q = W / N` — running mean of every leaf value found under this edge, in `[-1, +1]`, **in the frame
of whoever is to move at that node.**

**The correction worth carrying:** negamax here is a *bookkeeping convention*, **not the backup
rule.** Leela's backup **averages**. It never takes a max. `V_white = -V_black` only re-expresses
each value in the local frame, flipping every ply. Stockfish maximises; Leela averages and lets the
max *emerge* from where the visits went.

Draw the flip once and it sticks:

```
leaf after 1.Kf6 Kf8, White to move,  net says  +0.95129   (White's frame)
   edge above it, Black to move,      receives  -0.95129
   root edge,     White to move,      receives  +0.95129
```

---

## Q: P versus Q — and why doesn't it just use P?

|  | `P` | `Q` |
|---|---|---|
| when | before search | during search |
| changes? | **never** | every visit |
| is | one forward pass | a mean over many |

**The thing that reframes it:** `P` is *not* a move-quality score. The policy head is trained to
predict **which move a full MCTS search by this same engine would end up playing.** It is the
engine's compressed memory of its own search behaviour. That is why it can hand 10.64% to two
losing moves without being "wrong" in its own terms — and why search is a *policy improvement
operator*, not a tiebreak.

Intuition guides calculation; calculation corrects intuition.

*(Small trap: the `P` you read is already softmaxed at temperature 1.36 — `--policy-softmax-temp`,
the default. The raw net is sharper than the numbers you have been studying.)*

---

## Q: How does it choose? (You derived most of this yourself)

```
S(a) = Q(a)  +  c * P(a) * sqrt(max(N,1)) / (1 + n_a)
       ^^^^     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
       what I    what I might be missing
       measured
```

You got both proportionalities right unprompted: `U` grows with the parent's total `N`, shrinks
with this edge's own `n_a`. The two details:

- `sqrt(N)` not `N` — because uncertainty falls as `1/sqrt(n)`. Same square root as standard error,
  same one as a random walk's displacement. Exploration should widen only as fast as your ignorance
  is *actually* shrinking.
- `1 + n_a` — no division by zero at `n_a = 0`, and **measuring something halves the urgency of
  measuring it again.**

For unvisited moves there is no `Q` yet, so they borrow the parent's:

```
Q_FPU = Q(parent, running) - 0.33 * sqrt( sum of P over the visited children )
```

**The single frame to remember (iteration 2).** Kd6 has just returned the *best* measured value in
the position — `0.96766`, against a mere guess of `0.75015` for everything else — **and the search
does not pick it again.** Its `U` halved the instant it was visited (`1+0` → `1+1`), so
`S(Kf6) = 1.52205` beat `S(Kd6) = 1.36146`.

**Depth is not a parameter.** Leela has no depth setting at all. Depth is what happens when `U`
collapses wherever the visits piled up. Iterations 1–2 stay at ply 1, 3–5 reach ply 2, 6–7 reach
ply 3 — nobody told it to.

---

## Q: doesn't averaging drag the good move down?

You asked: 1 winning child among 9 losing ones — doesn't the mean get ruined?

**No, because the samples are not drawn uniformly.** `S = Q + U` *chooses where to sample*, so
`Q = W/N` is a visit-weighted mean whose weights the search picked. Measured at 800 nodes:

```
Kd6 377    Kf6 240    Kf5 1    Kd5 1
```

617 of 619 child visits — 99.7% — on the two winning moves. The two losers contribute **2 samples**.

*Physics framing:* **this is importance sampling.** A deliberately biased estimator, biased toward
the max. Not a defect being tolerated — the design.

---

## Q: how does it find the move nobody looked at?

There are **two different stories** here and the session originally merged them. Keep them apart.

**Story 1 — the value head refutes in one pass.**
Kf5 and Kd5 sit unvisited through 64 nodes. Somewhere before 128 each gets **exactly one visit**,
returns `Q = 0.000` with `d = 1.000`, and is **never visited again through 800 nodes.** Two visits
out of eight hundred permanently eliminated half the legal moves — correctly.
**The honest caveat:** this worked because the value head recognised a drawn structure in a *single
forward pass*. When the refutation is five moves deep, that first visit comes back encouraging and
the search has to build a subtree to find out. **The blind spots are where both heads are wrong at
once — which is the definition of a hard position, not a corner case.**

**Story 2 — a proof outranks all sampling.** Morphy, before 16.Qb8+:

| nodes | Qb7 | **Qb8+** | plays |
|---:|---:|---:|---|
| 400 | 169 | **0** | Qb7 |
| 1600 | 172 | **3** | **Qb8+** |
| 6400 | 172 | **3** | **Qb8+** |

`P(Qb8+) = 1.60%` — the instinct nearly missed a mate in two. Then read the last two rows again:
**four times the compute, and not one number in the table moves.** Qb8+ is played on **3 visits**,
beating a move examined **172** times, and it never accumulates more.

**Why:** `Q = 1.0` there is a **proof**, not an average. Proven results are tracked separately and
outrank any amount of sampling — and search *stops* rather than re-sample a solved subtree.

> The tempting explanation — "its `Q` dominates `S`, so all later visits flood into it" — is a
> correct derivation from `S = Q + U` and it is **false here**. The engine has behaviours that do
> not follow from that formula: proofs, terminal nodes, smart pruning, tree reuse. When the
> question is *what did the engine do*, the table wins, not the formula.

**Policy blindness, measured:** zero visits on a mate in two for 400 nodes, because `P = 1.6%`.

---

## Q: what about parallelism?

The tension in one sentence: **the algorithm wants to evaluate one position at a time, the hardware
wants hundreds.**

**Virtual loss** is the fix. A path selected but not yet evaluated gets `N += 1, W -= 1` on every
edge — a fictitious loss booked so the next thread goes elsewhere; removed when the real value
lands. On an edge with `N = 9, W = 7.2` that drops `Q` from `0.800` to `0.620`. On an edge with
`N = 500` it moves `Q` by `0.004`. **It bites where the tree is thin — exactly where you want
diversification.**

**But:** every number you have studied was measured with all of it switched off —
`--threads=1 --minibatch-size=1 --task-workers=0 --backend=blas`, strictly sequential CPU. So this
corpus *describes* virtual loss and cannot *exhibit* it.

**What is *not* switched off is smart pruning** (`SmartPruningFactor` = 1.33, never overridden).
That, not the disabled parallelism, is why `go nodes 800` built a tree of only **620** root visits
— re-run with `--smart-pruning-factor=0` and you get exactly 800. Requested nodes ≠ tree built,
and the reason has a name. Measured 2026-08-13; `guide/kb/ADDENDUM.md` §J.

---

## Q: does N split cleanly between children?

**Almost — and the leftover `1` is the interesting part.**

```
N(node) = 1 + n(child_1) + n(child_2) + ...
```

**The `1` is the node's own evaluation**, which is a sample like any other. Check it yourself in
ten seconds — this is the root's running Q at iterations 2 and 3:

```
(0.97602 + 0.96766) / 2            = 0.97184   matches the table
(0.97602 + 0.96766 + 0.98598) / 3  = 0.97655   matches the table
```

And at `go nodes 8`: children hold 4 + 3 + 0 + 0 = **7** visits; the tree is **8** nodes.

*Consequence:* a node's `Q` is anchored to its own first impression with weight `1/N`. Heavy at
iteration 2, negligible at 800. And `Q_FPU` reads the parent's *running* `Q`, not its original `V`.

---

## The traps — read this column before you trust a session answer

| Trap | Truth |
|---|---|
| "15 blocks, 768 channels" | **Two different nets.** `791556` = 15 SE-ResNet blocks × **192** filters — **it produced every measured number here.** `BT3` = 15 transformer encoders × **768**, 24 heads — that is what Guide Part 5 *draws*. Both have "15". `ENGINE_REFERENCE.md` calls BT3 "primary" — true for the product, **backwards for this corpus.** |
| `c = 1.745 + 3.894*ln((N+base)/base)` | Numerator is `N + base + **1**` → `(N + 38740)/38739`. Over the whole 8-iteration spine `c` moves 1.7451 → 1.7458. It is a millions-of-nodes knob. |
| `N(parent) = sum of children` | `= 1 + sum`. |
| `--policy-temperature` | Doesn't exist. `--policy-softmax-temp` (1.36). |
| `--virtual-loss` | Doesn't exist. The mechanism is real (ch08); no flag exposes it. |
| MinibatchSize 64 / 256 | Default **0** = backend's choice. |
| `--cpuct-at-root` tunes the root | Inert. `RootHasOwnCpuctParams` = **false** by default. Same for FPU: `FpuStrategyAtRoot` = `same`. |
| "negamax → each player maximises" | Leela **averages**. Negamax is only the frame convention. |
| A ladder's top-`S` move is what the search would pick next | **Not safe.** At 800 nodes Kf5 tops `S` (1.207 vs Kd6's 1.013) on **one** visit and is never picked — smart pruning had excluded it for ~170 iterations. Turn pruning off and it is picked at ~450 child visits, exactly as `S = Q + U` says. `ADDENDUM.md` §J. |
| `puct_utility.h`, `b = 31`, 112-plane breakdown, "AlphaZero rewrote opening theory" | **Not in the corpus.** No LC0 source tree here, no branching factor measured, no plane decomposition anywhere, and chess judgement is out of scope by rule. |

---

## If an answer has no filename attached, do not trust it

That is the finding of `ANSWER_AUDIT.md`, in one line. The earlier study session cited a source on
**11 of 11** answers and had **zero** errors. The later one cited **0 of ~30** and had **eight** —
and every wrong number was a plausible round figure from the AlphaZero literature rather than from
`lc0.exe` on this machine.

**Asking conceptual questions was right. Letting the answers stop naming files is what cost you.**
