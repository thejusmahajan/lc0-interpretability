"""Final evaluation of a trained Phi against the held-out TEST split.

    python -m phi_net.evaluate --checkpoint phi_net/runs/phi_b2.pt

Run this **once**, at the end. The validation split is what you tune against; the
test split is what you report, and every time you look at it to make a decision
it becomes a little less held-out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Same repair as run_kaggle.py: launching this by path rather than with -m puts
# the script's own directory on sys.path, not the package's parent.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch

from phi_net import data as data_mod
from phi_net.metrics import gate_report, logistic_auc, roc_auc
from phi_net.model import build_model
from phi_net.train import predict


def reliability(y: torch.Tensor, prob: torch.Tensor, bins: int = 10) -> list[dict]:
    """Calibration table. A well-ranked model can still be badly calibrated, and
    the steering stage compares Phi *differences* between positions, so the shape
    of the probability curve matters as much as the AUC."""
    rows = []
    edges = torch.linspace(0, 1, bins + 1, device=prob.device)
    for i in range(bins):
        upper_inclusive = (i == bins - 1)
        if upper_inclusive:
            mask = (prob >= edges[i]) & (prob <= edges[i + 1])
        else:
            mask = (prob >= edges[i]) & (prob < edges[i + 1])
        n = int(mask.sum())
        if n == 0:
            continue
        rows.append({"bin": f"{float(edges[i]):.1f}-{float(edges[i + 1]):.1f}",
                     "n": n, "mean_pred": float(prob[mask].mean()),
                     "actual": float(y[mask].mean())})
    return rows


def main(args) -> dict:
    device = torch.device(args.device if args.device else
                          ("cuda" if torch.cuda.is_available() else "cpu"))
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=False)
    saved = ckpt.get("args", {})
    model = build_model(channels=saved.get("channels", 64),
                        blocks=saved.get("blocks", 6),
                        n_motifs=ckpt.get("n_motifs", 20)).to(device)

    # A checkpoint trained on one dataset build and evaluated against another is
    # a silent category error: the motif outputs are positional and the splits
    # differ. Compare identities and refuse rather than print a plausible number.
    trained_on = (ckpt.get("dataset_manifest") or {}).get("build_timestamp")
    here = data_mod.read_manifest(args.data_dir).get("build_timestamp")
    if trained_on and here and trained_on != here:
        raise SystemExit(f"checkpoint was trained on dataset built {trained_on} but "
                         f"{here} is mounted. Refusing to report a number across builds.")
    model.load_state_dict(ckpt["model"])
    model.eval()

    train_split = data_mod.load_split("train", device, args.data_dir, limit=args.baseline_limit)
    test_split = data_mod.load_split("test", device, args.data_dir)
    print("  " + test_split.describe())

    material_auc = logistic_auc(train_split.material_counts(), train_split.y,
                                test_split.material_counts(), test_split.y)
    scores = predict(model, test_split, use_amp=not args.no_amp)
    prob = torch.sigmoid(scores)
    phi_auc = roc_auc(test_split.y, scores)

    pos = test_split.source == data_mod.SOURCE_POSITIVE
    per_source = {}
    for src, name in ((data_mod.SOURCE_N1_SPENT, "vs N1 spent-tactic"),
                      (data_mod.SOURCE_N2_QUIET, "vs N2 quiet-play")):
        mask = pos | (test_split.source == src)
        if int((test_split.source == src).sum()):
            per_source[name] = roc_auc(test_split.y[mask], scores[mask])

    print(f"\nTEST  Phi AUC {phi_auc:.4f}   material baseline {material_auc:.4f}", flush=True)
    for name, value in per_source.items():
        print(f"      {name:<22} {value:.4f}", flush=True)
    table, passed = gate_report(phi_auc, material_auc)
    print(table, flush=True)
    print("  ALL GATES PASS" if passed else "  !! A GATE FAILED", flush=True)

    print("\n  calibration", flush=True)
    print(f"  {'bin':<10}{'n':>8}{'predicted':>12}{'actual':>10}", flush=True)
    cal = reliability(test_split.y, prob)
    for row in cal:
        print(f"  {row['bin']:<10}{row['n']:>8}{row['mean_pred']:>12.3f}{row['actual']:>10.3f}", flush=True)

    result = {"test_auc": phi_auc, "material_auc": material_auc,
              "per_source": per_source, "gates_passed": passed, "calibration": cal,
              "checkpoint": str(args.checkpoint)}
    out = Path(args.checkpoint).with_name(Path(args.checkpoint).stem + "_test.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {out}", flush=True)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Evaluate Phi on the held-out test split.")
    p.add_argument("--checkpoint", default="phi_net/runs/phi_b2.pt")
    p.add_argument("--data-dir", default=None)
    p.add_argument("--device", default=None)
    p.add_argument("--no-amp", action="store_true",
                   help="disable fp16 autocast during inference")
    p.add_argument("--baseline-limit", type=int, default=60000,
                   help="rows of TRAIN used to fit the material baseline")
    main(p.parse_args())
