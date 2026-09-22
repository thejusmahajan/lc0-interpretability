# Pre-flight self-review of `phi_net`

**Date:** 2026-09-02. **Reviewer:** the leader, on his own code, before it goes to Kaggle.

I looked for bugs that would make the pipeline **useless rather than broken** — the ones that do not
crash, that produce a plausible number, or that waste a GPU session. I found **twelve**. Four of
them were serious. Two further suspicions I raised against myself turned out to be unfounded, and I
checked rather than assumed — see §5. All are fixed and the fixes are verified below.

The honest headline first: **my CPU smoke test proved the pipeline runs and deliberately does not
exercise the riskiest code in it.** `use_amp` is False on CPU, so the entire mixed-precision path —
`autocast`, `GradScaler`, fp16 overflow behaviour — has never executed. See §3.

---

## 1. What was wrong, in order of how much it would have cost

### S1 — `roc_auc` had a Python loop on the per-epoch path

The tie-handling walked the sorted score array one element at a time. Measured: **1.22 s per call**
on CPU for 26,222 rows — and it is called three times per epoch (overall, vs N1, vs N2).

On CUDA it is much worse than slow: `sorted_s[i] != sorted_s[start]` on a device tensor is a
**host-device synchronisation, once per element**. Twenty-six thousand syncs per AUC, ~79,000 per
epoch. The whole design rests on epochs taking seconds; this one function would have made the metric
cost more than the training and produced the exact symptom the README tells the reader to treat as
a bug ("epochs take minutes, not seconds").

**Fixed** with a vectorised average-rank computation via `unique_consecutive`. Verified two ways:

```
ties case   : vectorised 0.492075   brute force 0.492075   diff 0.00e+00
no-ties case: vectorised 0.515847   brute force 0.515847   diff 0.00e+00
speed: 0.0134 s per call   (was 1.22 s)  -- 91x
```

The brute-force reference is the pairwise Mann-Whitney definition with the half-credit rule for
ties. **Ties are not hypothetical here**: the material baseline is fit on ten integer piece counts,
so thousands of rows share a score exactly.

### S2 — the documented Kaggle command does not work

`HOW_TO_KAGGLE.md` said to run `!python /kaggle/working/phi_net/run_kaggle.py`. Verified:

```
ModuleNotFoundError: No module named 'phi_net'
```

Launching a script by path puts the *script's* directory on `sys.path`, not the package's parent.
This would have killed the very first cell of the first session. **Fixed** in two places: the
how-to now uses `python -m phi_net.run_kaggle`, and `run_kaggle.py` repairs `sys.path` itself so
both forms work. Both verified.

### S3 — a frame error, written into the README of the module built to avoid frame errors

The README described the steering criterion as `Φ(after) − Φ(before)`. **Φ is defined on the side to
move**, so `Φ(before)` scores *my own* error-proneness and `Φ(after)` scores *the opponent's*. They
are different questions and subtracting them is meaningless.

For ranking candidate moves it happens to be harmless — `Φ(before)` is constant across candidates,
so the ordering is identical — which is exactly what makes it dangerous: it would never show up as a
wrong answer, only as a wrong idea that someone later extends across plies. **Fixed** in both the
README and `PLAN_CONFIGURATION_STEERING.md` §6, which carried the same error in the spec of record.
The rule is now written down: *any Φ difference must be between positions with the same side to
move.* Gate F3's four-ply comparison preserves parity and is fine; three or five plies would not be.

This is the **POV/frame family** from `LEADER_BIBLE.md` §5, and I wrote a fresh instance of it.

### S4 — the checkpoint recorded no dataset identity

The 20 motif outputs are **positional**, indexed against `manifest.json`'s frozen
`theme_vocabulary_20`. A rebuild that reorders that list silently changes what every output means —
same shape, no error, different semantics. The two builds we already have *do* differ in ordering
(`endgame, crushing, short, …` versus `crushing, short, endgame, …`).

**Fixed**: the manifest is now saved into every checkpoint, the loader prints the dataset's build
timestamp, and `evaluate.py` **refuses** to score a checkpoint against a different build rather than
printing a plausible number.

---

## 2. The rest

| # | defect | why it matters | fix |
|---|---|---|---|
| 5 | `steps_per_epoch == 0` when `--limit < --batch-size` | silent empty epochs, then `ZeroDivisionError` | explicit `SystemExit` naming both numbers |
| 6 | `best['epoch']` read after the loop; a NaN AUC never compares greater | `KeyError` instead of a diagnosis | NaN guard that says *"the split has only one class"* |
| 7 | `torch.randperm` with a **CUDA** generator | version-sensitive across torch builds; a 200k permutation costs microseconds on CPU anyway | generate on CPU, move once |
| 8 | `load_split` ignored `args.seed` for the `--limit` subset | changing `--seed` did not change which rows B1 saw — silently unreproducible | seed threaded through |
| 9 | `float(loss)` on a tensor still requiring grad | `UserWarning`, and it keeps the graph alive | `.detach()` |
| 10 | `n_motifs` hardcoded to 20 | a rebuild with a different vocabulary size breaks in the head, not at the boundary | derived from `motif.shape[1]`, stored in the checkpoint |
| 11 | reliability binning used a conditional expression *inside* the mask | parses correctly, but one edit from silently wrong | rewritten as an explicit branch |
| 12 | a `⚠` in the gate print | `UnicodeEncodeError` on the cp1252 Windows console — crashed the first run | all `.py` files are pure ASCII, checked programmatically |

Re-verified after every fix: the full ladder runs, `run_kaggle.py` correctly **stopped before B2**
when B1 failed its gate, and `evaluate.py` produces its table and calibration.

---

## 3. What I could NOT verify, and it is the risky half

There is no GPU on this machine. Everything below is **untested code on the path to Kaggle**:

1. **The entire mixed-precision path.** `use_amp` is False on CPU, so `autocast`, `GradScaler`,
   loss scaling and fp16 overflow have never run. This is simultaneously the least-tested and
   most-likely-wrong part of the file. **If anything fails on Kaggle, look here first.** Mitigation
   in place: `--no-amp` reproduces the tested path exactly.
2. **`_unpack` on CUDA.** The bit-shift on negative int64 is correct on CPU (verified against piece
   counts); CUDA integer shift semantics are the same, but I have not run it.
3. **Memory.** 241 MB resident train + 30 MB val + activations at batch 8192 *should* fit a 16 GB
   T4 comfortably. Unmeasured.
4. **`torch.compile`.** Completely untested; off by default for that reason as much as any other.
5. **Epoch wall-clock.** Every timing claim about GPU speed in the README and the round table is a
   prediction. The first real run replaces it.
6. **Multi-GPU is not used.** `phi_net` is deliberately single-device. The second T4 will idle here
   — that is correct for this workload and is *not* the `EnginePool` bug from the LC0 side.

---

## 4. The principles I broke, stated plainly

Worth writing down because each was a *known* rule, not a discovery.

- **Never put an interpreted loop, or a data-dependent branch on a device tensor, on a per-epoch
  path.** Every such comparison is a synchronisation point. I was thinking about tie correctness and
  forgot where the code would run. (§S1)
- **Every command in a document must have been executed exactly as written.** I typed a plausible
  invocation instead of running it. This is the most common way a README lies. (§S2)
- **Trace the frame for any quantity that depends on whose turn it is.** The Bible has a whole
  failure family for this, and I introduced a new instance while writing the module that exists to
  avoid it. (§S3)
- **A number's meaning must travel with the number.** A checkpoint that does not name its dataset
  is a result that cannot be reproduced or invalidated. (§S4)
- **Do not hardcode a constant that exists in the data.** (§10)
- **A test that only exercises the path your machine can run is not a test of the path that will
  run.** The CPU smoke test is genuinely useful — it caught the unicode crash and proved the wiring
  — but reporting it as "verified end to end" without §3 attached would have been the overclaim.

---

## 5. For the independent review

If you want Gemini's read to be genuinely independent, **have it review the code without this
document**, then compare its list against §1–§2. An echo of my findings tells you nothing; an
overlap tells you both of us are looking in the right place; something I missed is the whole point.

The places I would attack if I were reviewing someone else's version of this:

1. The AMP path (§3.1) — untested, and the failure is silent degradation rather than a crash.
2. ~~The bit-order convention in `_unpack` versus `encode.py`.~~ **Settled while writing this.**
   `phi_net._unpack` produces byte-identical planes to the encoder's own reference `unpack()` for
   three positions including a black-to-move one and the start position. The layout matches; we are
   not training on a transposed board.
3. ~~`Split.material_counts()` relying on `uint8` sum promotion.~~ **Settled:** torch promotes
   integer `sum` to `int64` (checked: 255 x 64 = 16,320, not a wrap). No overflow is possible.
4. Whether `--limit`'s stratification changes the N1/N2 mix inside the negatives (it is random
   across sources), and whether that makes B1 and B2 incomparable.
5. `OneCycleLR` total steps versus the number of batches actually yielded — they agree now because
   `drop_last` is on; they would silently desynchronise if anyone turned it off.
