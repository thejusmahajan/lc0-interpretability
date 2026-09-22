"""Training loop for Phi.

Run the ladder from `PLAN_CONFIGURATION_STEERING.md` section 8b:

    python -m phi_net.train --limit 100000 --epochs 20 --tag b1     # does it learn at all?
    python -m phi_net.train --epochs 40 --tag b2                    # the real held-out number

Design notes that matter, and why:

* **No DataLoader.** The data is resident on the GPU (see ``data.py``).
* **float16 via autocast, with fp32 parameters and a GradScaler.** Never
  ``model.half()`` -- pure fp16 masters silently underflow both the weight update
  and Adam's ``eps=1e-8`` (below fp16's smallest normal, ~6e-5) and you get a
  plausible loss curve with a worse model.
* **bfloat16 is not an option here.** Kaggle's T4 is Turing (SM 7.5) and the P100
  is Pascal (SM 6.0); hardware bf16 starts at Ampere.
* **The ragged last batch is dropped** -- see ``data.batches``.
* **The motif head trains on positives only.** The N1 negatives inherit their
  puzzle's themes (measured: 3.96 motif bits per row, against 3.90 for
  positives), but an N1 row is the position *after* the solution was played --
  the tactic is over. Training the head there teaches it to name a storm that has
  already passed. N2 rows are all-zero by construction. So the motif loss is
  masked to ``source == SOURCE_POSITIVE``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn.functional as F

from phi_net import data as data_mod
from phi_net.metrics import gate_report, logistic_auc, roc_auc
from phi_net.model import build_model


def _make_scaler(device: torch.device, enabled: bool = True):
    """GradScaler across torch versions; a no-op stub on CPU.

    ``enabled`` follows ``use_amp``. Leaving a live scaler on with autocast off is
    not a correctness bug -- scale-then-unscale by a power of two is exact in
    fp32, measured at 0.0 gradient difference -- but it does pointless work and
    makes ``--no-amp`` a half-measure.
    """
    if device.type != "cuda":
        class _NullScaler:
            def scale(self, loss): return loss
            def step(self, opt): opt.step()
            def update(self): pass
            def unscale_(self, opt): pass
        return _NullScaler()
    try:
        return torch.amp.GradScaler("cuda", enabled=enabled)
    except (AttributeError, TypeError):
        return torch.cuda.amp.GradScaler(enabled=enabled)


@torch.no_grad()
def predict(model, split, batch_size: int = 16384, use_amp: bool = True) -> torch.Tensor:
    model.eval()
    out = torch.empty(len(split), device=split.device)
    for start in range(0, len(split), batch_size):
        stop = min(start + batch_size, len(split))
        xb = split.x[start:stop]
        with torch.autocast("cuda", dtype=torch.float16,
                            enabled=use_amp and split.device.type == "cuda"):
            logits, _ = model(xb.float())
        out[start:stop] = logits.float()
    return out


def evaluate_split(model, split, material_ref=None, use_amp: bool = True) -> dict:
    """Phi AUC overall and per negative source. The per-source split matters:
    N1 and N2 are different negatives and Phi may well separate one and not the
    other, which is information about the data, not about the model."""
    scores = predict(model, split, use_amp=use_amp)
    result = {"auc": roc_auc(split.y, scores), "n": len(split)}
    pos = split.source == data_mod.SOURCE_POSITIVE
    for src, name in ((data_mod.SOURCE_N1_SPENT, "auc_vs_n1"),
                      (data_mod.SOURCE_N2_QUIET, "auc_vs_n2")):
        mask = pos | (split.source == src)
        if int((split.source == src).sum()) > 0:
            result[name] = roc_auc(split.y[mask], scores[mask])
    if material_ref is not None:
        result["material_auc"] = material_ref
    return result


def train(args: argparse.Namespace) -> dict:
    device = torch.device(args.device if args.device else
                          ("cuda" if torch.cuda.is_available() else "cpu"))
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.benchmark = True

    print(f"device: {device}"
          + (f"  ({torch.cuda.get_device_name(0)}, "
             f"{torch.cuda.device_count()} visible)" if device.type == "cuda" else ""))

    t0 = time.perf_counter()
    train_split = data_mod.load_split("train", device, args.data_dir,
                                      limit=args.limit, seed=args.seed)
    val_split = data_mod.load_split("val", device, args.data_dir)
    manifest = data_mod.read_manifest(args.data_dir)
    print(f"loaded in {time.perf_counter() - t0:.1f}s")
    if manifest:
        print(f"  dataset built {manifest.get('build_timestamp', '?')} "
              f"seed {manifest.get('seed', '?')} stride {manifest.get('sampling_stride', '?')}")
    else:
        print("  !! no manifest.json beside the .npz -- dataset identity unrecorded")
    print("  " + train_split.describe())
    print("  " + val_split.describe())

    # Material-only baseline: this is F2's reference, and re-deriving it here is a
    # free check that the data just loaded is the data that was audited (A3).
    material_auc = logistic_auc(train_split.material_counts(), train_split.y,
                                val_split.material_counts(), val_split.y)
    print(f"material-only baseline AUC: {material_auc:.4f}  (audited value ~0.488)")

    n_motifs = int(train_split.motif.shape[1])
    model = build_model(channels=args.channels, blocks=args.blocks,
                        n_motifs=n_motifs).to(device)
    print(f"model: {model.n_params():,} parameters")
    forward = model
    if args.compile:
        # Off by default. It is a hypothesis with a measurement attached: a fresh
        # Kaggle session pays the compile pass every time, and for a model this
        # small that can exceed what it saves. Compare wall-clock before keeping.
        forward = torch.compile(model, mode="reduce-overhead")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    steps_per_epoch = len(train_split) // args.batch_size
    if steps_per_epoch == 0:
        raise SystemExit(
            f"batch_size {args.batch_size} exceeds the {len(train_split)} training rows, so "
            f"every epoch would be empty (the ragged last batch is dropped by design). "
            f"Lower --batch-size or raise --limit.")
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=args.lr, total_steps=max(args.epochs * steps_per_epoch, 1),
        pct_start=0.25)
    use_amp = device.type == "cuda" and not args.no_amp
    scaler = _make_scaler(device, enabled=use_amp)
    generator = torch.Generator().manual_seed(args.seed)   # CPU generator; see data.batches

    history, best = [], {"auc": -1.0}
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{steps_per_epoch} steps/epoch at batch {args.batch_size}"
          f"  |  amp={'fp16' if use_amp else 'off'}  |  compile={args.compile}\n",
          flush=True)

    wall0 = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train()
        ep0 = time.perf_counter()
        tot_phi = tot_motif = 0.0
        for idx in data_mod.batches(len(train_split), args.batch_size, generator, device):
            xb = train_split.x[idx].float()
            yb = train_split.y[idx]
            mb = train_split.motif[idx]
            pos_mask = train_split.source[idx] == data_mod.SOURCE_POSITIVE

            opt.zero_grad(set_to_none=True)
            with torch.autocast("cuda", dtype=torch.float16, enabled=use_amp):
                phi_logit, motif_logit = forward(xb)
                loss_phi = F.binary_cross_entropy_with_logits(phi_logit.float(), yb)
                if pos_mask.any():
                    loss_motif = F.binary_cross_entropy_with_logits(
                        motif_logit[pos_mask].float(), mb[pos_mask])
                else:
                    loss_motif = torch.zeros((), device=device)
                loss = loss_phi + args.motif_weight * loss_motif

            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot_phi += float(loss_phi.detach())
            tot_motif += float(loss_motif.detach())

        stats = evaluate_split(model, val_split, material_auc, use_amp=use_amp)
        stats.update(epoch=epoch, loss_phi=tot_phi / steps_per_epoch,
                     loss_motif=tot_motif / steps_per_epoch,
                     seconds=time.perf_counter() - ep0)
        history.append(stats)
        print(f"  epoch {epoch:3d}/{args.epochs}  phi {stats['loss_phi']:.4f}  "
              f"motif {stats['loss_motif']:.4f}  val AUC {stats['auc']:.4f}  "
              f"(n1 {stats.get('auc_vs_n1', float('nan')):.4f} / "
              f"n2 {stats.get('auc_vs_n2', float('nan')):.4f})  "
              f"{stats['seconds']:.1f}s", flush=True)

        if not (stats["auc"] == stats["auc"]):   # NaN guard: a split with one class
            raise SystemExit("validation AUC is NaN -- the split has only one class. "
                             "Check --data-dir and the .npz files.")
        if stats["auc"] > best["auc"]:
            best = dict(stats)
            torch.save({"model": model.state_dict(), "args": vars(args),
                        "val": stats, "n_motifs": n_motifs,
                        "dataset_manifest": manifest},
                       out_dir / f"phi_{args.tag}.pt")

    total = time.perf_counter() - wall0
    table, passed = gate_report(best["auc"], material_auc)
    print(f"\ntotal training wall-clock: {total:.1f}s "
          f"({total / max(args.epochs, 1):.2f}s/epoch)")
    print(f"best val AUC {best['auc']:.4f} at epoch {best['epoch']}")
    print("  (this table is PROVISIONAL: the AUC is the best epoch selected on the "
          "validation\n   split, so it is optimistic. The reportable F1 is evaluate.py "
          "on the test split.)")
    print(table)
    print("  ALL GATES PASS" if passed else
          "  !! A GATE FAILED -- read PLAN section 8 before changing anything.")

    summary = {"tag": args.tag, "best": best, "material_auc": material_auc,
               "gates_passed": passed, "total_seconds": total,
               "history": history, "args": vars(args)}
    (out_dir / f"phi_{args.tag}_metrics.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {out_dir / f'phi_{args.tag}.pt'} and "
          f"{out_dir / f'phi_{args.tag}_metrics.json'}")
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train Phi, the configuration potential.")
    p.add_argument("--data-dir", default=None,
                   help="defaults to data/training/config_steering in the repo")
    p.add_argument("--out-dir", default="phi_net/runs")
    p.add_argument("--tag", default="b2", help="run name, used in output filenames")
    p.add_argument("--limit", type=int, default=None,
                   help="class-balanced subset of TRAIN (the B1 rung); val stays full")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=8192)
    p.add_argument("--lr", type=float, default=2e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--channels", type=int, default=64)
    p.add_argument("--blocks", type=int, default=6)
    p.add_argument("--motif-weight", type=float, default=0.3)
    p.add_argument("--seed", type=int, default=20260901)
    p.add_argument("--device", default=None)
    p.add_argument("--no-amp", action="store_true", help="disable fp16 autocast")
    p.add_argument("--compile", action="store_true",
                   help="try torch.compile; measure before keeping it")
    return p


if __name__ == "__main__":
    train(build_parser().parse_args())
