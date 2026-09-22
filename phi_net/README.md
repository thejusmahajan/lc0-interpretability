# `phi_net` — the configuration potential

Φ answers one question about a chess position:

> **Is this a position of the shape where the side to move goes wrong?**

It is a *potential function* over configurations, not a second opinion about who is winning. **No
engine evaluation appears anywhere in its inputs, its labels, or its loss** — which is Thejus's
binding constraint, satisfied by construction rather than by promise:

> *"Now, LC0 evaluating a position good doesn't mean it is a tactical position."*

Design and rationale: **`docs/plans/PLAN_CONFIGURATION_STEERING.md`** (read §3 and §4 first).
The aim in Thejus's own words: `ideas/2026-09-01_steering_to_tal_configurations.md`.

---

## What it learns, and the honest limit

The positive class is `s_err` — the Lichess puzzle `fen`, which is the position **one ply before
the tactic**, with the losing side to move and about to err. There are 5.5M of these, and each one
is **a real human of a known rating who actually failed to solve it**.

So Φ learns **what a human in the 1500–2200 band gets wrong**, not objective attacking potential.
For a coaching tool aimed at Thejus's opponents that is the right target. It must never be claimed
as more than that, anywhere, including in a job application.

---

## Files

| file | what it does |
|---|---|
| `data.py` | loads the `.npz` splits and unpacks 18 `uint64` bitboards into `18×8×8` planes, **resident on the GPU**. No `DataLoader` — see below. |
| `model.py` | the network: a small residual CNN with a Φ head and a 20-way motif head. |
| `metrics.py` | ROC AUC and the logistic baseline in torch (scikit-learn is *not* in the `cszero` env), plus the F0/F1/F2 gate table. |
| `train.py` | the training loop. One rung of the ladder per invocation. |
| `evaluate.py` | final held-out **test** evaluation, per-source AUC and calibration. Run once. |
| `run_kaggle.py` | one-cell entry point: preflight, B1, then B2, stopping if B1 fails a gate. |

---

## Four decisions worth understanding before you change anything

**1. There is no `DataLoader`, deliberately.** The whole training split is 34.7 MB packed and
~241 MB unpacked — it fits in any Kaggle GPU with room to spare. A `DataLoader` with worker
processes would spend the epoch in Python while the card idles; the vectorised unpack of one split
measured **27.45 s on the project laptop's two CPU cores**, and paying that per epoch is the
easiest way to waste a GPU session. So: unpack once, keep it on the device, index batches with a
permutation tensor.

**2. `float16` via `autocast`, with fp32 parameters and a `GradScaler` — never `model.half()`.**
Pure-fp16 masters do not crash; they silently underflow. A weight update of order `lr × grad`
rounds away against fp16's ten mantissa bits, and Adam's default `eps=1e-8` is below fp16's
smallest normal (~6e-5). You get a plausible loss curve and a worse model.

**3. `bfloat16` is not an option.** Kaggle's T4 is Turing (SM 7.5) and the P100 is Pascal (SM 6.0);
hardware bf16 starts at Ampere. On a T4 it is emulated and slower than fp32.

**4. The motif head trains on positives only.** The N1 "spent tactic" negatives *inherit their
puzzle's themes* — measured at 3.96 motif bits per row, against 3.90 for positives — but an N1 row
is the position **after** the solution was played. Training the head there teaches it to name a
storm that has already passed. N2 rows are all-zero by construction. So the motif loss is masked to
`source == 0`.

The ragged last batch is dropped, because a changing input shape forces
`torch.compile(mode="reduce-overhead")` to re-capture its CUDA graph every epoch.

---

## The gates

From `PLAN_CONFIGURATION_STEERING.md` §8. They are printed at the end of every run.

| gate | test | threshold | if it fails |
|---|---|---|---|
| **F0** | material-only AUC on the loaded data | < 0.65 | the data is not what was audited — stop |
| **F1** | Φ held-out AUC | > 0.70 | configurations are not learnable at this representation |
| **F2** | Φ AUC − material AUC | ≥ 0.03 | Φ learned material, not configuration |

**A failed F2 is a data result, not a tuning problem.** Do not respond to it by changing
hyper-parameters. The dataset has already been rebuilt once for exactly this reason: the first
build passed all its alarms and was still separable at AUC 0.66 on *check status and mobility*,
which have nothing to do with configuration.

---

## Running it

The ladder (`PLAN` §8b). Build the dataset first — it lives in `data/training/config_steering/`
and is **gitignored**, so it exists only on the machine that built it.

```bash
# B1 -- does it learn anything at all? minutes on a T4
python -m phi_net.train --limit 100000 --epochs 15 --tag b1

# B2 -- the real held-out number
python -m phi_net.train --epochs 40 --tag b2

# once, at the end, on the test split
python -m phi_net.evaluate --checkpoint phi_net/runs/phi_b2.pt
```

On Kaggle, one cell does all of it: see **`HOW_TO_KAGGLE.md`**.

Useful flags: `--channels` / `--blocks` (model size), `--batch-size` (8192 default; the data is
resident so large batches are free), `--no-amp`, `--compile`, `--device cpu`.

`--compile` is **off by default and is a hypothesis with a measurement attached**: a fresh Kaggle
session pays the compile pass every time, and for a model this small that can cost more than it
saves. Run thirty seconds each way and keep whichever wins — do not adopt it because it is
standard practice.

### Verified end to end

The pipeline was smoke-tested on CPU before delivery (6,000 rows, 1 epoch, 16 channels, 2 blocks):
it loads, trains, evaluates, writes a checkpoint and a metrics JSON, and the gate table renders.
That run scored **val AUC 0.5285** and correctly reported **F1 FAIL** — which is the right answer
for a deliberately tiny model, and confirms the gates are not decorative. It is not a result.

---

## Outputs

`--out-dir` (default `phi_net/runs/`) receives:

- `phi_<tag>.pt` — best checkpoint by validation AUC, with the args and val stats inside it
- `phi_<tag>_metrics.json` — full per-epoch history, the gate verdicts, wall-clock
- `phi_<tag>_test.json` — from `evaluate.py`

Per-epoch output reports Φ's AUC **against each negative source separately** (`n1` and `n2`). If Φ
separates one and not the other, that is information about the data, not about the model.

---

## What Φ is for, once it works

It is the potential in a potential-based re-ranking of moves LC0 has **already declared safe**.
`metrics.steer_candidates()` keeps only moves costing ≤ 60 cp against best and never landing below
−60 cp; Φ then ranks that surviving set. **LC0 keeps an absolute veto over
blunders. Φ never overrides it — it only re-orders what is already sound.**

Shaping by a potential difference cannot change which policy is optimal, only which one is found
first (Ng, Harada & Russell, ICML 1999).

### ⛑ Φ's meaning flips with the side to move — rank, do not subtract across a ply

Φ is defined on the **side to move**: “the player to move here is about to go wrong”. So:

* `Φ(position in hand)` — *I* am to move. It scores **my own** error-proneness.
* `Φ(position after my move)` — the **opponent** is to move. It scores **theirs**.

These are different questions, and `Φ(after) − Φ(before)` subtracts one from the
other. For *ranking candidate moves* it is harmless, because `Φ(before)` is the same constant
for every candidate and the ordering is identical — so **rank by `Φ(after)` and do not write
the subtraction down at all.**

Where it would genuinely bite is any comparison **across plies**. Gate F3 asks whether the
Φ-max move “raises Φ four plies later”; four plies preserves the parity, so that is
legitimate. A three- or five-ply comparison would not be, and would produce a confident,
meaningless number. **Any Φ difference must be between positions with the same side to move.**
