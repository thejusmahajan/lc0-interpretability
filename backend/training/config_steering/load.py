"""Data loader for configuration steering splits."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "training" / "config_steering"


def load_split(name: str, data_dir: Path | str | None = None) -> dict:
    """Load a dataset split (train, val, or test) from disk.

    Returns a dict containing:
      - 'bb': np.ndarray of shape (N, 18), dtype uint64
      - 'y': np.ndarray of shape (N,), dtype uint8
      - 'motif': np.ndarray of shape (N, 20), dtype uint8
      - 'meta': dict with manifest metadata (counts, themes, seed, etc.)
    """
    base_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    npz_path = base_dir / f"{name}.npz"
    manifest_path = base_dir / "manifest.json"

    if not npz_path.exists():
        raise FileNotFoundError(f"Split file not found: {npz_path}")

    with np.load(npz_path) as data:
        bb = data["bb"]
        y = data["y"]
        motif = data["motif"]
        source = data["source"] if "source" in data else None

    meta = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

    result = {
        "bb": bb,
        "y": y,
        "motif": motif,
        "meta": meta,
    }
    if source is not None:
        result["source"] = source
    return result
