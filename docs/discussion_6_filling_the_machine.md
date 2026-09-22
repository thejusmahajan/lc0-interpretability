# 📜 Project Discussion 6: Filling the Machine — 80 GB GPU / 167 GB RAM at Full Tilt

**Date:** 2026-07-23
**Status:** Resource-utilization architecture review — the A100 is ~90% idle.
**Hardware (Colab Pro, measured):** A100-SXM4-**80 GB** GPU (using **8.5 GB**),
System RAM **167 GB** (using **5.8 GB**), Disk 235 GB + 368 GB local scratch.
**Budget:** 39.25 compute units (finite — filling the machine must *save* units by
finishing faster, not burn them).
**Participants:** D. Gukesh (World Champion, the target user), Mikhail Tal (his
reborn guardian angel), DeepMind Principal Scientist, LC0 Lead Developer, Claude.

---

## Act I — The accusation

**Gukesh:** *(pulling up the resource monitor)* I pay for a machine with **eighty
gigabytes** of graphics memory and one hundred sixty-seven of system memory. It is
using **eight** and **six**. When I train, I use *all* of myself — every hour, every
faculty. This machine trains at ten percent and calls it a day. I am three months
from defending the title. I do not want a tool that dozes. **Wake it up.**

**DeepMind Scientist:** He's right, and the number tells the story. 8.5 GB on an
A100 means we've loaded the BT3 net (~0.4 GB), an lc0 CUDA context, and almost
nothing else. The other 71 GB is dark. The reason is the *shape* of our workload,
not the hardware.

**LC0 Developer:** One lc0 process, running one MCTS search at a time, at ~18k nps
on the BT3 transformer. A single node-limited search collects a small batch of
leaves before it must back-propagate. So the GPU does a trickle of small forward
passes and idles between them. It is **latency-bound**. An A100 is a **throughput**
machine — it wants to be handed thousands of positions at once. We hand it four.

---

## Act II — Why 71 GB sits dark

**DeepMind Scientist:** Three structural choices keep the machine asleep:

```
  1. SEQUENTIAL pipeline:  game -> move -> candidate -> one search -> next.
     The GPU sees one small problem at a time.
  2. ONE engine process:  no parallelism; the SMs are mostly waiting on the
     CPU-side tree logic (select / expand / backup).
  3. TINY caches:  NNCacheSize=500k, RamLimitMb=8192. On a 167 GB box that's a
     thimble — every game re-evaluates opening positions it has seen 100 times.
```

**LC0 Developer:** And the memory math is almost comic. A BT3 position evaluation is
~0.4 GB of *weights* (shared) plus a few MB of activations. We could hold the
activations for **tens of thousands** of positions in flight and never touch 20 GB.
We're rationing a feast.

---

## Act III — Gukesh sets the terms (this is not about speed)

**Gukesh:** Hear me clearly, because engineers always reach for "faster." I do not
primarily want faster. I want **three** things the idle memory can buy me:
1. **Depth where it decides the game** — in the sharp position, I want the machine
   to look as deep as a second in the World Championship match would, not a blitz
   glance.
2. **Breadth** — every one of my decisions across *thousands* of games, screened, so
   my blind-spots are a statistic, not an anecdote.
3. **Sight** — I want to *see what the net sees three moves ahead*. If its intuition
   already contains the combination, show me the gap between its sight and mine.

If filling the machine also makes it finish before my coffee is cold, good. But the
memory is there to make me **stronger**, not just quicker.

**Tal:** *(delighted)* Finally! The boy understands. A machine with eighty gigabytes
should not evaluate one sacrifice politely — it should **dream a thousand attacks at
once**, burn every one to the end, and bring back only the ones that scorch. Give me
memory and I will give you *chaos with proof*.

---

## Act IV — The five levers (the engineering)

**DeepMind Scientist:** Here is how the idle 71 GB and 161 GB become depth, breadth,
and sight. Five levers, roughly in order of leverage.

### Lever 1 — Harvest-then-batch: the corpus-wide wide screen
Invert the pipeline. **First** walk every game and collect *all* decision positions
(and their candidate moves) into system RAM — 167 GB holds millions of FENs
trivially. **Then** push them through BT3 (`evaluate_batch`: policy + value + WDL +
saliency) in **huge batches** — not 64 positions, but 4,000–16,000 per forward. At
~3 ms/pos amortized, the *entire policy + candidate screen for the whole corpus*
becomes a handful of GPU forwards — seconds, not hours — and it finally fills the
80 GB. This is Discussion-5's Opt #2 taken to its limit. **Breadth, delivered.**

### Lever 2 — Parallel lc0 workers: fill the GPU with deep searches
The deep MCTS confirmations that remain (only the *crux* positions the screen flags)
are still latency-bound one at a time. So run **8–16 lc0 processes concurrently**,
each on a slice of the crux list, all sharing the 80 GB GPU (the net is loaded once
per process; 16 × ~0.5 GB ≈ 8 GB — still a fraction). Their searches overlap; while
one backs up on the CPU, another feeds the SMs. Wall-clock for the deep pass drops
near-linearly — which directly **saves compute units**. **Depth, in parallel.**

### Lever 3 — A colossal NN/transposition cache in the 167 GB RAM
Raise lc0's `NNCacheSize` from 500k to **tens of millions**, and `RamLimitMb` to
tens of GB. Chess games share enormous prefixes — every London System reaches the
same tabiya. A giant cache means each unique position is evaluated **once** for the
whole corpus; the 9,000-game run stops re-computing the same openings 9,000 times.
Nearly free with the RAM we have. **Breadth again, and unit savings.**

### Lever 4 — Activation harvesting at scale: give Gukesh *sight*
This is what the memory unlocks that nothing else can. BT3's forward pass already
contains 3–7 plies of look-ahead in its hidden layers (`docs/research_learned_
lookahead.md`). Normally you'd never store those activations — they're huge. But with
70 GB of GPU headroom and 160 GB of RAM, we **can** harvest, for thousands of
positions at once: the attention-head "future-board" representations and the
value/policy *before* the output-layer priors override them. That yields the
**"suppressed-win" detector** — moves the net's deeper layers found but its instinct
rejected — exactly Tal's dream and Gukesh's third demand. Feasible *only* because we
have the memory to hold the rich internal state in bulk.

### Lever 5 — Quality headroom: fp32 BT3, or an ensemble, for the crux
The crux positions deserve the best eval we can give. 80 GB lets us run BT3 in
**fp32** (higher precision than cuda-fp16) for the final confirmation, or even a
small **ensemble** (BT3 + a second strong net) whose agreement/disagreement is
itself a signal of danger. Memory we already own, spent on the ~5% of positions that
decide the diagnosis. **Depth, sharpened.**

---

## Act V — Tal's rollout furnace

**Tal:** Add one more, for the fire. When your wide screen flags a position as
*sharp* — high decisiveness, narrow, low draw share — do not merely evaluate it.
**Rollout a thousand games from it in parallel** on the idle GPU: let BT3 play both
sides at speed, ten thousand times, and measure how often the *human* defender
collapses versus the engine's cold defense. That gap — "practical chaos" — is the
true Tal score. A move that is +0.3 but wins 70% against a human under pressure is
worth more than a +0.8 that any patzer holds. **The memory lets you measure fear.**

**DeepMind Scientist:** Massively-parallel self-play rollouts from flagged nodes —
that's a legitimate and beautiful use of 80 GB. It's how AlphaZero measured
positions in the first place. We can bound it (N rollouts, depth cap) so it stays
within the compute-unit budget.

---

## Act VI — The re-architected pipeline

**Claude:** Synthesizing, the pipeline changes shape from a thin sequential thread
into a wide machine that fills the hardware:

```
  HARVEST      walk all games -> all decision positions + candidates -> 167 GB RAM
     |
  WIDE SCREEN  giant batched BT3 (policy+value+wdl+saliency) -> fills 80 GB GPU
     |         + huge lc0 NN cache (RAM) so nothing is evaluated twice
     |
  CRUX SELECT  keep only sound + sharp candidates (cheap, from the screen)
     |
  DEEP PASS    8-16 parallel lc0 workers, fp32/ensemble, on the crux only
     |         + Tal rollout furnace on the sharpest nodes
     |
  SIGHT        harvest BT3 look-ahead activations on findings -> suppressed-win /
               vision features (Discussion-4 B1/B2, research note)
     |
  PROFILE      findings + steer + repertoire, richer than before
```

Every idle resource now has a job: **GPU RAM** = giant batches + parallel workers +
fp32/ensemble + rollouts; **system RAM** = the harvested corpus + the colossal NN
cache + the activation store; **disk/scratch** = persist the caches and activations
across sessions so a restart resumes for free.

**Gukesh:** *That* is a training partner. Deep where it matters, broad across all my
games, and it shows me what it sees. Build it.

---

## Act VII — What comes out of it (deliverables, staged & quality-gated)

| # | Lever | Resource it fills | Effect | Risk / gate |
|---|---|---|---|---|
| 1 | Harvest-then-batch wide screen | GPU (big batches) + RAM (corpus) | Whole-corpus screen in seconds; breadth | Quality-neutral (net eval unchanged); validate `steer_findings` diff |
| 2 | Parallel lc0 workers | GPU (concurrent searches) | Deep pass near-linear faster → **fewer compute units** | Process orchestration; identical evals per worker |
| 3 | Colossal NN cache | System RAM | Transpositions free across the corpus | Just config (`NNCacheSize`, `RamLimitMb`); verify no eval drift |
| 4 | Activation harvesting (sight) | GPU headroom + RAM | Suppressed-win / vision features at scale | Research-y; prototype after UI validation |
| 5 | fp32 / ensemble on the crux | GPU RAM | Max-quality confirmation where it decides | Small; measure eval stability |
| 6 | Tal rollout furnace | GPU (parallel rollouts) | "Practical chaos" score for sharp nodes | Bound N/depth to the unit budget |

**Bottom line for the user:** the machine is idle because our pipeline hands it one
small problem at a time. Re-shape it to **harvest → wide-batch screen → parallel-deep
crux → harvest sight**, and the *same* 80 GB / 167 GB turn into **more depth, full-
corpus breadth, and the net's own look-ahead made visible** — while finishing faster
and spending *fewer* compute units, because a filled GPU is a fast GPU.

**Recommended first move (highest leverage, lowest risk):** Lever 1 + Lever 3 —
the harvest-then-batch wide screen plus the giant NN cache. Both are near-quality-
neutral, both directly fill the idle memory, both cut the wall-clock (and unit burn)
of the current deep-search-bound run. Levers 2, 5, 6 follow for the deep pass; Lever
4 (sight) after the UI is validated. Each stays gated by the same rule we've held all
along: **prove the findings don't degrade before it ships.**
