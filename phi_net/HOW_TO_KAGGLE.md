# How to train Φ on Kaggle

Start to finish. Assumes the dataset has been built locally — `data/training/config_steering/`
containing `train.npz`, `val.npz`, `test.npz`, `manifest.json`, `STATS.md`.

**This costs nothing.** Kaggle's free GPU tier is enough for all of it. **Do not spend Colab units
here** — Φ is a small CNN on ~50 MB and it is not where compute goes in this project. The only
thing that could ever justify paid compute is the LC0 profile regeneration, and even then the right
answer is to cut the game count first.

---

## Step 1 — upload the dataset (once)

`data/` is gitignored in its entirety, so the built dataset exists **only on your machine and is
not backed up**. Uploading it to Kaggle fixes both problems at once.

1. Upload `dist/config_steering_dataset.zip` (**6.2 MB**, built for you — the five files flat,
   with no folder inside the archive).
2. Kaggle → **Datasets** → **New Dataset** → upload the zip. Name it something stable, e.g.
   `config-steering`. Private is fine.
3. Note the mount path it gets: `/kaggle/input/config-steering/`.

**Whatever Kaggle does with the archive, the run copes.** It may expand the zip into loose files,
or leave it intact — this project has notes recording both behaviours
(`docs/guides/KAGGLE_BEST_PRACTICES.md` §5). `data.resolve_data_dir()` handles all three shapes:
files at the mount root, files one directory down, or a single unexpanded `.zip` (which it extracts
once to `/kaggle/working/_dataset` and says so). Two dataset versions or two archives on one mount
make it **raise rather than guess** — picking one silently is how a stale artefact gets reported as
a result.

Re-upload as a **new version** whenever the dataset is rebuilt, and write down which version a run
used. Two runs on two dataset versions are not comparable.

---

## Step 2 — get the code there

Upload `dist/phi_net_code.zip` (**32 KB** — seven `.py` files and the docs, flat) as a second
dataset called `phi-net-code`, then in the notebook:

```python
!mkdir -p /kaggle/working/phi_net
!cp /kaggle/input/phi-net-code/*.py /kaggle/working/phi_net/ 2>/dev/null || cp /kaggle/input/phi-net-code/*/*.py /kaggle/working/phi_net/
```

Or paste the files into notebook cells and write them out with `%%writefile`. Either is fine; the
dataset route means you edit locally, re-upload, and the notebook stays one cell.

---

## Step 3 — the notebook

**There is a ready-made notebook: `dist/kaggle_phi_net.ipynb`** (source of record:
`phi_net/kaggle_phi_net.ipynb`). In Kaggle: **New Notebook → File → Import Notebook**, upload it,
add both datasets as inputs in the sidebar, set the accelerator, and run all.

It finds the two mounts **by what they contain**, not by dataset slug, so the names you give the
datasets do not matter. It copes with the archives being expanded by Kaggle or left intact, and it
**refuses to run if two mounts match** rather than guessing between dataset versions. The discovery
cell was executed locally against simulated mounts with both archives still zipped.

The rest of this section describes doing it by hand, which is still fine.

### Doing it by hand

Create a new **Notebook**, and in the sidebar:

- **Accelerator → a SINGLE GPU.** `GPU P100` for preference. Φ trains on `cuda:0` and has no
  `DataParallel` or DDP, so on a `T4 ×2` the second card sits at 0% for the entire run — there is
  no throughput to gain from the pair. Kaggle *may* also bill the session against both cards;
  **I have not verified how the quota is counted, so check your own usage page** rather than
  trusting that. Either way there is no upside, so take one card. The preflight prints every
  visible GPU with its name and SM level, so you will see what you were given.
- **Internet → off** is fine. Nothing here downloads anything.
- Add both datasets as inputs.

Then one cell:

```python
import os
os.chdir('/kaggle/working')

!cd /kaggle/working && python -u -m phi_net.run_kaggle \
    --data-dir /kaggle/input/config-steering \
    --out-dir /kaggle/working/phi_runs
```

**Use `-u`.** It is not cosmetic. A notebook `!command` pipes stdout, so Python block-buffers
it at ~8 KB — and an ~85-byte epoch line therefore does not appear for roughly ninety epochs.
The run looks hung when it is perfectly fine. (The epoch print flushes explicitly now too, so
`-u` is belt and braces.)

**Use the `-m` form.** Running `python /kaggle/working/phi_net/run_kaggle.py` instead puts the *script's*
directory on `sys.path` rather than the package's parent, and the run dies immediately with
`ModuleNotFoundError: No module named 'phi_net'`. That was **verified, not guessed** -- it would
have stopped the very first cell. (`run_kaggle.py` now repairs `sys.path` itself so both forms
work, but `-m` from `/kaggle/working` is the one to type.)

`run_kaggle.py` will:

1. **Preflight** — print torch version, every visible GPU with its name, memory and SM level, and
   **abort if there is no CUDA device**. That abort is deliberate: a Kaggle session bills wall-clock
   for a GPU notebook whether or not the card is used, so a silent CPU fallback costs quota and
   returns nothing.
2. Run **rung B1** — 100,000 rows, 15 epochs.
3. **Stop there if B1 fails a gate.** Scaling a model that has not learned anything only makes it
   confident.
4. Run **rung B2** — the full training split, 40 epochs.
5. Print both wall-clocks and the gate table.

Then, in a second cell, once:

```python
!cd /kaggle/working && python -u -m phi_net.evaluate \
    --checkpoint /kaggle/working/phi_runs/phi_b2.pt \
    --data-dir /kaggle/input/config-steering
```

---

### Why the run deletes its own outputs first

`run_kaggle.py` removes `phi_b1.*` and `phi_b2.*` from the output directory before training.
That is not tidiness. On 2026-07-26 (commit `33ff814`) a crashed 100-game Kaggle run left an
earlier **2-game** `profile.json` on disk; the completion check read it and printed
`[DONE] REAL run: games=2`. Ninety-eight games had never been analysed, and the run looked
successful. The same trap is set here — if B1 stops the ladder or B2 crashes, a `phi_b2.pt`
from an earlier session would survive and the evaluation cell would score **the old model**.
Deleting the targets up front means a crash leaves no artefact, so the next step fails loudly
instead of lying quietly.

---

## Step 4 — get the results out

Anything under `/kaggle/working/` is saved as the notebook's output version. So the checkpoints and
the metrics JSON come home automatically — but only if the session ends **gracefully**.

For anything long, use **Save & Run All (Commit)** rather than leaving an interactive tab open.
Interactive sessions die on idle, and a killed session discards the working directory.

Download `phi_runs/` afterwards and commit the metrics JSON (not the `.pt`) to the repo, so the
numbers are in the record.

---

## What a good result looks like

The gate table at the end of B2:

```
  GATE                     VALUE   THRESHOLD   VERDICT
  F0  material-only AUC    0.4884   < 0.65      PASS
  F1  Phi held-out AUC     0.xxxx   > 0.7       ?
  F2  Phi minus material   0.xxxx   >= 0.03     ?
```

**F0 should print ≈ 0.488.** That number was independently verified at audit time against the built
dataset. If it comes out different, you are not training on the data that was audited — stop and
check which dataset version is mounted.

F1 and F2 are the actual experiment and nobody knows the answer yet. Both outcomes are useful:

- **F1 passes** → configurations are learnable from this representation, and the steering pipeline
  has its potential function. Next is stage B/C in the plan.
- **F1 fails** → configurations are *not* linearly-or-convolutionally recoverable at 18 planes.
  That is a real finding, not a failure of nerve. The response is to change the representation
  (relational features, or BT3 activations) — **not** to tune hyper-parameters until the number
  moves.

Also watch the per-source line: `(n1 x.xxxx / n2 x.xxxx)`. If Φ separates positives from the
"spent tactic" negatives but not from real quiet play, it has learned "a tactic just finished here"
rather than "a tactic is available from here" — the same class of artefact the dataset was rebuilt
to remove, arriving through the model instead of the data.

---

## If something goes wrong

| symptom | cause |
|---|---|
| `ABORT: no CUDA device` | the accelerator is off. Turn it on; don't pass `--allow-cpu` to get past it. |
| `FileNotFoundError ... train.npz` | `--data-dir` doesn't match the mount. Check `/kaggle/input/`. |
| F0 is not ≈ 0.488 | wrong dataset version mounted. |
| OOM on load | you are on a smaller card than expected. Pass `--b1-limit 50000`, or unpack in smaller chunks (`data._unpack(chunk=…)`). |
| epochs take minutes, not seconds | something is copying per batch. There should be no `DataLoader` anywhere; confirm the data landed on the device (the load line prints "MB resident"). |
| loss goes to `nan` | fp16 overflow. Run with `--no-amp` to confirm, then reduce `--lr`. Do **not** switch to `model.half()`. |
| nothing prints for minutes | block-buffered stdout. Use `python -u`. The run is almost certainly fine. |
| B2 never runs | fixed 2026-09-02. B1 used to abort on the full F1 gate; it now stops only if F0 fails or Φ fails to beat the material baseline. |
| `FileNotFoundError` although the dataset is mounted | you zipped the *folder*, so the files are one level deeper. `data.py` resolves one level down automatically; if it refuses, two dataset versions are mounted and it will not guess between them. |
| a result appears after a failed run | it cannot any more: `run_kaggle.py` deletes this run's checkpoints before starting, so a crash leaves nothing to mistake for a result. |

---

## Housekeeping

Kaggle gives roughly 30 GPU-hours a week with a ~12-hour session cap; check the current numbers on
your account page rather than trusting these. Two concurrent sessions are allowed — that halves
calendar time but **spends the weekly allowance twice as fast**, so keep it for runs you already
know are correct.

**Never do CPU work in a GPU session.** Building the dataset inside a GPU notebook burns the
allowance running `python-chess` on a CPU. Build locally; train on Kaggle.
