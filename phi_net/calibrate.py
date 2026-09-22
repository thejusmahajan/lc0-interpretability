"""Calibrate Phi's output so the percentage shown in the UI means what it says.

Phi's held-out AUC is 0.6908 -- it ranks positions usefully -- but its raw sigmoid
is **over-spread**, and it is worst exactly where steering uses it:

    test bin 0.7-0.8   predicted 0.749   actual 0.654
    test bin 0.8-0.9   predicted 0.843   actual 0.762

The UI renders that as ``Risk: 75%`` when the empirical rate is 65%. That is a
coach overstating its confidence, which this project treats as worse than no
coach at all.

**Isotonic regression fixes it and cannot change the AUC**, because it is a
monotone (rank-preserving) transform. So calibration is free: it makes the number
honest without touching the ranking that the steering actually uses.

    python -m phi_net.calibrate --checkpoint phi_net/runs/phi_b2.pt

**Fitted on the VALIDATION split, reported on TEST.** Fitting on test would make
the reported calibration a description of the fit rather than a measurement of it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch

from phi_net import data as data_mod
from phi_net.metrics import roc_auc
from phi_net.model import build_model
from phi_net.train import predict


def fit_isotonic(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pool-adjacent-violators. Returns (knots_x, knots_y), both non-decreasing.

    Fits the non-decreasing step function minimising squared error against the
    0/1 outcomes. No scikit-learn in this environment, and it is twenty lines.
    """
    order = np.argsort(x, kind="mergesort")
    xs, ys = np.asarray(x, dtype=np.float64)[order], np.asarray(y, dtype=np.float64)[order]

    # each block: [sum of y, count]; merge left while the mean order is violated
    values: list[float] = []
    weights: list[float] = []
    for target in ys:
        values.append(target)
        weights.append(1.0)
        while len(values) > 1 and values[-2] > values[-1]:
            v2, w2 = values.pop(), weights.pop()
            v1, w1 = values.pop(), weights.pop()
            merged_w = w1 + w2
            values.append((v1 * w1 + v2 * w2) / merged_w)
            weights.append(merged_w)

    fitted = np.repeat(np.array(values), np.array(weights).astype(int))
    return xs, fitted


def apply_calibration(p: np.ndarray, knots_x: np.ndarray, knots_y: np.ndarray) -> np.ndarray:
    """Linear interpolation between the isotonic knots, clipped at the ends."""
    return np.interp(np.asarray(p, dtype=np.float64), knots_x, knots_y,
                     left=float(knots_y[0]), right=float(knots_y[-1]))


def decile_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict]:
    rows = []
    edges = np.linspace(0.0, 1.0, bins + 1)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p <= hi if i == bins - 1 else p < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": n,
                     "predicted": float(p[mask].mean()),
                     "actual": float(y[mask].mean())})
    return rows


def expected_calibration_error(rows: list[dict]) -> float:
    """Sample-weighted mean |predicted - actual| across the deciles."""
    total = sum(r["n"] for r in rows)
    return sum(r["n"] * abs(r["predicted"] - r["actual"]) for r in rows) / total


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit Phi's probability calibration.")
    ap.add_argument("--checkpoint", default="phi_net/runs/phi_b2.pt")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    device = torch.device(args.device if args.device else
                          ("cuda" if torch.cuda.is_available() else "cpu"))
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=False)
    saved = ckpt.get("args", {})
    model = build_model(channels=saved.get("channels", 64), blocks=saved.get("blocks", 6),
                        n_motifs=ckpt.get("n_motifs", 20)).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()

    val = data_mod.load_split("val", device, args.data_dir)
    test = data_mod.load_split("test", device, args.data_dir)

    p_val = torch.sigmoid(predict(model, val)).cpu().numpy()
    y_val = val.y.cpu().numpy()
    p_test = torch.sigmoid(predict(model, test)).cpu().numpy()
    y_test = test.y.cpu().numpy()

    knots_x, knots_y = fit_isotonic(p_val, y_val)
    p_test_cal = apply_calibration(p_test, knots_x, knots_y)

    before = decile_table(y_test, p_test)
    after = decile_table(y_test, p_test_cal)

    print(f"fitted on VAL ({len(y_val):,} rows), reported on TEST ({len(y_test):,} rows)\n")
    print("  TEST deciles BEFORE calibration")
    print(f"  {'bin':<10}{'n':>7}{'predicted':>11}{'actual':>9}{'error':>9}")
    for r in before:
        print(f"  {r['bin']:<10}{r['n']:>7}{r['predicted']:>11.3f}{r['actual']:>9.3f}"
              f"{r['predicted'] - r['actual']:>+9.3f}")
    print(f"\n  TEST deciles AFTER calibration")
    print(f"  {'bin':<10}{'n':>7}{'predicted':>11}{'actual':>9}{'error':>9}")
    for r in after:
        print(f"  {r['bin']:<10}{r['n']:>7}{r['predicted']:>11.3f}{r['actual']:>9.3f}"
              f"{r['predicted'] - r['actual']:>+9.3f}")

    ece_before, ece_after = expected_calibration_error(before), expected_calibration_error(after)
    auc_before = roc_auc(torch.tensor(y_test), torch.tensor(p_test))
    auc_after = roc_auc(torch.tensor(y_test), torch.tensor(p_test_cal))
    print(f"\n  expected calibration error  {ece_before:.4f} -> {ece_after:.4f}")
    print(f"  test AUC                    {auc_before:.4f} -> {auc_after:.4f}"
          f"   (must be unchanged: isotonic is rank-preserving)")

    # store a compact monotone curve rather than every training point
    grid = np.linspace(0.0, 1.0, 101)
    out = {
        "fitted_on": "val",
        "reported_on": "test",
        "checkpoint": os.path.basename(args.checkpoint),
        "dataset_build": (ckpt.get("dataset_manifest") or {}).get("build_timestamp"),
        "grid_x": [round(float(v), 4) for v in grid],
        "grid_y": [round(float(v), 6) for v in apply_calibration(grid, knots_x, knots_y)],
        "test_ece_before": round(ece_before, 4),
        "test_ece_after": round(ece_after, 4),
        "test_auc": round(auc_after, 4),
        "note": ("Isotonic, fitted on val. Rank-preserving, so the AUC is unchanged and the "
                 "steering order is untouched; only the displayed probability changes."),
    }
    path = Path(args.checkpoint).with_name(Path(args.checkpoint).stem + "_calibration.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
