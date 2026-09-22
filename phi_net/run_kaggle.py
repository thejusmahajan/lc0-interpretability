"""One-cell entry point for a Kaggle notebook.

Paste into a single cell (GPU accelerator on):

    !python /kaggle/working/phi_net/run_kaggle.py --data-dir /kaggle/input/<your-dataset>

It runs the ladder in order and stops at the first rung that fails a gate, which
is the point of a ladder. Everything it prints is measured in that session --
there are no numbers baked into this file.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

# Work whether launched as ``python -m phi_net.run_kaggle`` or as
# ``python /path/to/phi_net/run_kaggle.py``. In the second form Python puts the
# *script's* directory on sys.path, not the package's parent, so the import
# below fails -- which is exactly how a Kaggle session dies in its first cell.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch

from phi_net.train import build_parser, train


def clear_stale_outputs(out_dir: str, tags: tuple[str, ...]) -> list[str]:
    """Delete this run's target artefacts before training starts.

    Directly mirrors commit 33ff814 (2026-07-26), where a crashed 100-game
    Kaggle run left an earlier 2-game ``profile.json`` on disk and the
    completion check happily reported ``[DONE] REAL run: games=2``. Ninety-eight
    games had never been analysed.

    The same trap is set here: if B1 stops the ladder or B2 crashes, a
    ``phi_b2.pt`` from a previous session survives, and the evaluation cell will
    score **the old model** and print a plausible table. Removing the targets up
    front means a crash leaves no artefact, so the next step fails loudly
    instead of lying quietly.
    """
    removed = []
    for tag in tags:
        for suffix in (".pt", "_metrics.json", "_test.json"):
            path = os.path.join(out_dir, f"phi_{tag}{suffix}")
            if os.path.exists(path):
                os.remove(path)
                removed.append(path)
    return removed


def preflight(require_gpu: bool = True) -> None:
    """Fail loudly rather than quietly training on a CPU for eleven hours.

    A Kaggle session bills wall-clock for a GPU-enabled notebook whether or not
    the card is used, so a silent CPU fallback costs quota and returns nothing.
    """
    print("=" * 66)
    print(f"torch {torch.__version__}   cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            print(f"  GPU {i}: {props.name}  {props.total_memory / 1e9:.1f} GB  "
                  f"SM {props.major}.{props.minor}")
        if torch.cuda.get_device_properties(0).major < 8:
            print("  note: SM < 8.0 -> no hardware bfloat16. This code uses float16, "
                  "which is correct for T4 (SM 7.5) and P100 (SM 6.0).")
    elif require_gpu:
        sys.exit("ABORT: no CUDA device. Enable the GPU accelerator, or pass "
                 "--allow-cpu if you really mean to run on CPU.")
    print("=" * 66)


def b1_verdict(b1_auc: float, material_auc: float) -> tuple[bool, str]:
    """Decide whether the B1 rung justifies spending a session on B2.

    **B1 is diagnostic, not the falsification gate.** It runs a fraction of the
    data for a fraction of the epochs to answer one question: does Phi learn
    anything at all? Gate F1 (AUC > 0.70) belongs to B2, judged on the held-out
    test split by ``evaluate.py``.

    This function exists because the first version applied the whole gate set
    here, so a B1 of 0.66 -- a good result at that scale, and exactly the case
    that should proceed -- would have aborted the Kaggle session before B2 ever
    started. Caught by an independent audit, 2026-09-02.

    Only two things stop the ladder:
      * F0 fails: the data is separable on piece counts, so nothing trained on
        it would mean anything.
      * Phi does not beat the material baseline: it learned nothing beyond piece
        counting, and more epochs cannot fix a representation carrying no signal.
    """
    if material_auc >= 0.65:
        return False, (
            f"\nSTOP: F0 failed at B1 -- the material-only baseline scores "
            f"{material_auc:.4f} (must be < 0.65). The dataset is separable on piece "
            f"counts alone, so nothing trained on it would mean anything. Check which "
            f"dataset version is mounted before doing anything else.")
    if b1_auc <= material_auc:
        return False, (
            f"\nSTOP: Phi scored {b1_auc:.4f} against a material-only baseline of "
            f"{material_auc:.4f} -- it learned nothing beyond piece counting.\n"
            f"This is a REPRESENTATION result, not a tuning problem. Read "
            f"PLAN_CONFIGURATION_STEERING.md section 8 before changing hyper-parameters; "
            f"the answer is a different input representation (relational features, or "
            f"BT3 activations), not more epochs.")
    return True, (
        f"\nB1 diagnostic: AUC {b1_auc:.4f} vs material {material_auc:.4f} "
        f"(+{b1_auc - material_auc:.4f}). Signal is present -- proceeding to B2.\n"
        f"B1's gate table above is INFORMATIONAL: F1 is judged at B2, on the test "
        f"split, by evaluate.py.")


def main() -> None:
    p = argparse.ArgumentParser(description="Run the Phi training ladder on Kaggle.")
    p.add_argument("--data-dir", default=None,
                   help="e.g. /kaggle/input/config-steering")
    p.add_argument("--out-dir", default="/kaggle/working/phi_runs")
    p.add_argument("--b1-limit", type=int, default=100_000)
    p.add_argument("--b1-epochs", type=int, default=15)
    p.add_argument("--b2-epochs", type=int, default=40)
    p.add_argument("--batch-size", type=int, default=8192)
    p.add_argument("--allow-cpu", action="store_true")
    p.add_argument("--compile", action="store_true")
    # Without this the mitigation HOW_TO_KAGGLE.md recommends for fp16 trouble
    # is unreachable from the Kaggle entry point.
    p.add_argument("--no-amp", action="store_true",
                   help="disable fp16 autocast in training AND evaluation")
    args = p.parse_args()

    preflight(require_gpu=not args.allow_cpu)

    os.makedirs(args.out_dir, exist_ok=True)
    stale = clear_stale_outputs(args.out_dir, ("b1", "b2"))
    if stale:
        print(f"removed {len(stale)} artefact(s) from a previous run so a crash "
              f"cannot be mistaken for a result:", flush=True)
        for path in stale:
            print(f"  - {path}", flush=True)

    wall0 = time.perf_counter()

    def rung(tag: str, limit, epochs) -> dict:
        print(f"\n{'=' * 66}\n  RUNG {tag.upper()}  "
              f"({'full train split' if limit is None else f'{limit:,} rows'}, "
              f"{epochs} epochs)\n{'=' * 66}")
        rung_args = build_parser().parse_args([])
        rung_args.data_dir = args.data_dir
        rung_args.out_dir = args.out_dir
        rung_args.tag = tag
        rung_args.limit = limit
        rung_args.epochs = epochs
        rung_args.batch_size = args.batch_size
        rung_args.compile = args.compile
        rung_args.no_amp = args.no_amp
        return train(rung_args)

    b1 = rung("b1", args.b1_limit, args.b1_epochs)
    proceed, message = b1_verdict(b1["best"]["auc"], b1["material_auc"])
    print(message, flush=True)
    if not proceed:
        return

    b2 = rung("b2", None, args.b2_epochs)
    print(f"\n{'=' * 66}")
    print(f"  B1 best val AUC {b1['best']['auc']:.4f} in {b1['total_seconds']:.0f}s")
    print(f"  B2 best val AUC {b2['best']['auc']:.4f} in {b2['total_seconds']:.0f}s")
    print(f"  session wall-clock {time.perf_counter() - wall0:.0f}s")
    print(f"{'=' * 66}")
    print("\nNext: python -m phi_net.evaluate --checkpoint "
          f"{args.out_dir}/phi_b2.pt   (run ONCE, on the test split)")


if __name__ == "__main__":
    main()
