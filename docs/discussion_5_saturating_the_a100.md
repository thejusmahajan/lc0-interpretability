# 📜 Project Discussion 5: Saturating the A100 — GPU Utilization vs. Quality

**Date:** 2026-07-22
**Status:** Performance architecture review — is the diagnosis using the A100's real power?
**Participants:**
- **DeepMind Principal AI Scientist** (AlphaZero architecture, transformer batching, MCTS)
- **LC0 Lead Core Developer** (lc0 engine internals, backends, `lczerolens`)
- **D. Gukesh** (World Champion; hard worker building a tactical style — the target user)
- **Claude** (the engineer who built the current pipeline — on the stand)

**Hardware on the table:** NVIDIA A100-SXM4-**80GB**, compute 8.0, 1410 MHz, 40 MB
L2, CUDA 12.8. **Measured:** BT3 (`768x15x24h`) at **19,397 nps**; one BT3 saliency
**0.58s**; a 3-game diagnosis **378s** of which **TS2 = 74%**; GPU util peaks ~94%.

---

## Act I — The symptom

**DeepMind Scientist:** An A100-80GB is a batch-throughput machine. Its peak is
reached feeding it *hundreds of positions per forward pass*. At 19k nps on a
768×15 transformer, and 0.58s for a *single* saliency forward, we are running it
like a low-latency serial device. The GPU shows 94% "utilization," but that number
is a lie of omission — it means the SM is busy, not that it's near peak FLOPs. A
stream of tiny forward passes keeps it 94% "busy" at a fraction of its throughput.

**LC0 Developer:** Correct. MCTS is **latency-bound on a single search**. Each
`engine.analyze()` runs one search; the tree is explored select→expand→evaluate→
backup. Even with `MinibatchSize=1024` and virtual loss, a single node-limited
search rarely collects a full 1024-leaf batch before it must back up results. So
the A100 does many *small* forwards. On an 80 GB card that's like towing a feather
with a freight train.

---

## Act II — Claude on the stand

**Gukesh:** *(leaning in, blunt)* I train six hours a day to remove *my* wasted
effort. So I will ask plainly: why is my tool wasting this machine? Claude, you
made choices. Defend them or own them.

**Claude:** I'll own them. Three mistakes, and they compound:

1. **I optimized the wrong axis.** I converted time-limits to node-limits and then
   *calibrated the node budgets to reproduce the CPU-era search depth* — 40k/20k
   nodes for BT3. I treated a cutting-edge transformer as if it needed the same
   amount of search as the tiny 18 MB net. It does not. A strong net's evaluation
   is reliable in **far fewer** nodes; I paid for search the net didn't need.
2. **I left the GPU's best trick unused.** BT3 saliency runs **serially**, 0.58s ×
   hundreds of positions. I even *reverted* a batched implementation and deferred
   re-adopting it. That serial loop is the single most A100-hostile thing in the
   pipeline.
3. **I ignored a tool already in my hand.** We load BT3 **twice** — once in lc0
   (`.pb.gz`, for search) and once in torch (`bt3.onnx`, for saliency). I used the
   torch copy only to draw heatmaps, when it can **batch-evaluate policy + value +
   saliency for hundreds of positions in one forward pass.**

**DeepMind Scientist:** So you were doing deep serial search where a wide batched
forward pass would do. That is the whole error, stated once.

---

## Act III — The diagnosis (and the physics that saves us)

**DeepMind Scientist:** Here is the reframe. Two kinds of work exist in this
pipeline, and they have opposite hardware profiles:

```
  WIDE work  (policy screen, candidate scoring, saliency)  = pure forward passes
             -> perfectly batchable -> LOVES the A100
  DEEP work  (confirming the crux line, resolving a tactic) = MCTS search
             -> latency-bound, sequential -> starves the A100
```

We are currently doing **DEEP work everywhere** — a full search on all 4 TS2
candidates at every node — when 90% of it is really WIDE screening.

**LC0 Developer:** And there's a beautiful accelerant we just logged in
`docs/research_learned_lookahead.md`. BT3's **forward pass already contains 3–7
plies of look-ahead in its hidden layers** — a linear probe reads the move two
turns ahead at ~92%. That means for a strong transformer, a *single forward pass*
is not a static eval — **it is implicit calculation.** So the quality we thought we
were buying with 20k–40k MCTS nodes is *largely already present in one batched
forward.* We can shrink the explicit search dramatically **without losing tactical
quality**, because the net does the looking-ahead internally.

**Gukesh:** *(sitting up)* Say that again in my language.

**LC0 Developer:** Tal didn't calculate every branch — he *saw* the sacrifice and
verified the critical line. BT3 is the same: its intuition *is* look-ahead. So we
let the net **see** all the candidates in one batched glance, and we only sit down
to **calculate deeply** on the one or two moves that look sharp.

**Gukesh:** *(grinning)* That is exactly how a tactician thinks. You don't deep-
calculate forty moves. You feel where the fire is, then you burn the line to the
end. If the machine can *feel* in a batch and *calculate* only the fire — that is
not a compromise on quality. That is **better** chess, and faster.

---

## Act IV — The plan (quality preserved, A100 fed)

**DeepMind Scientist:** Formalize it as a two-tier evaluator.

### Optimization 1 — Batch every forward pass (immediate, ~40% off TS2)
Adopt the batched `saliency_absolute_batch` the pipeline already calls. Hundreds of
0.58s serial saliency calls collapse into a handful of GPU forwards. This is pure
win, zero quality change. **Do first, with tests.**

### Optimization 2 — Wide batched screen with BT3-in-torch (the big one)
Use the already-loaded `bt3.onnx` (via `lczerolens`) to compute **policy + value +
saliency together, batched across all candidate positions in one forward.** This
saturates the A100 exactly as it wants. Justified by learned look-ahead: the single
forward already carries the tactical foresight. TS2 stops running 4 separate MCTS
searches per node and instead scores all candidates in one batched glance.

### Optimization 3 — Deep search only on the crux (preserves quality)
Keep lc0 + BT3 MCTS, but spend it **only** where it matters: the handful of
candidates the wide screen flags as sharp/steer-worthy, and Stage B confirmation of
a genuine suspect. This is the *only* place we pay for latency-bound search — and
it's small, so the A100 isn't starved by it.

### Optimization 4 — Find the node "knee" for BT3 (empirical, quality-guarded)
Measure eval stability vs. node count on a sample: strong nets plateau early. Set
the *confirmation* node budget at the knee (likely well under 20k), not at a number
inherited from the small net. Guard it: a position whose eval is still swinging gets
more nodes; a settled one stops.

**LC0 Developer:** Optional 5 — with 80 GB free, we can also run **2–4 lc0 instances**
sharing the GPU so the deep searches themselves overlap. Secondary to the above.

---

## Act V — Verdict

**Gukesh:** So the honest answer to "are we wasting the GPU?" is **yes** — and the
fix makes the analysis *more* like real tactical thinking, not less. I approve. Feed
the net wide, calculate the fire deep.

**DeepMind Scientist:** The quality argument is sound: we are not lowering the
ceiling, we are removing search we were doing *out of habit inherited from a weak
net*. The transformer's internal look-ahead is the quality; the batch is the speed.

**Claude:** Accepted, and the criticism is fair. My node budgets were a small-net
reflex applied to a strong net, and my serial saliency wasted the one thing the A100
is best at. The path is: **(1) batch saliency now, (2) batched BT3-torch wide screen,
(3) deep MCTS only on the crux, (4) node-knee calibration** — each guarded by a
quality check so we never trade the profile's correctness for speed.

---

## 🎯 Deliverables (ordered; each gated by a quality check)

| # | Change | Expected effect | Quality guard |
|---|---|---|---|
| 1 | Adopt batched `saliency_absolute_batch` (tested) | ~40% off TS2; kills the "Stage B 0%" pause | identical saliency values, verified vs serial |
| 2 | BT3-in-torch **batched policy+value screen** for TS2 candidates | Saturates A100; replaces 4 serial searches with 1 batched forward | steer candidates matched vs full-search on a sample |
| 3 | Deep lc0+BT3 search **only** on screened crux moves | Removes most latency-bound search | crux set ⊇ what full-search would have flagged |
| 4 | Node-knee calibration for BT3 confirmation | Cuts confirmation nodes to the plateau | eval stability check per position |
| 5 (opt) | Multi-instance lc0 sharing the 80 GB GPU | Overlaps residual deep searches | — |

**Bottom line for the user:** *Yes — there is a real, quality-preserving path to use
the A100 properly.* The insight is that BT3's forward pass already does the look-
ahead, so we feed the net **wide and batched** (where the A100 is unbeatable) and
reserve **deep search for the crux only**. Estimated end state on the 30-game
subset: from ~1 hour down to **~15–25 minutes** with equal-or-better findings — and
a diagnosis engine that thinks the way a tactician actually thinks.
