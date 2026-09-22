"""VRAM-resident data loading for Phi.

There is no ``DataLoader`` in this file and that is deliberate. The whole dataset
is 34.7 MB on disk as packed bitboards and ~300 MB unpacked; it fits on any GPU
Kaggle offers with room to spare. A ``DataLoader`` with worker processes would
spend the entire epoch in Python while the GPU idles -- the vectorised unpack of
one split measured **27.45 s on the project laptop's two CPU cores**, and doing
that per epoch is the single easiest way to waste a GPU session.

So: load once, unpack once, keep everything on the device, and index batches with
a permutation tensor.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch

# data/training/config_steering/ relative to the repo root
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "training" / "config_steering"

SOURCE_POSITIVE = 0   # s_err  -- the opponent is to move and about to go wrong
SOURCE_N1_SPENT = 1   # the position after a puzzle's full solution line
SOURCE_N2_QUIET = 2   # real quiet play from the user's own games

# Plane indices holding our/their P N B R Q (kings excluded: always exactly one).
_MATERIAL_PLANES = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]


def _unpack(bb_u64: np.ndarray, device: torch.device, chunk: int = 32_768) -> torch.Tensor:
    """(N, 18) uint64 bitboards -> (N, 18, 8, 8) uint8 planes, on ``device``.

    Done in chunks because the intermediate is int64: unpacking all 209k training
    rows in one shot would allocate 209036 * 18 * 64 * 8 bytes ~= 1.9 GB of
    scratch. Chunking at 32k rows caps that spike at ~300 MB.

    The ``view(np.int64)`` is a bit-level reinterpret, not a conversion. Values
    with bit 63 set become negative, and torch's ``>>`` is then an arithmetic
    shift -- but ``(x >> k) & 1`` still yields bit k correctly for every k in
    0..63, because sign extension only ever fills bits *above* the one we mask.
    """
    n = bb_u64.shape[0]
    bits = torch.arange(64, dtype=torch.int64, device=device)
    out = torch.empty((n, 18, 8, 8), dtype=torch.uint8, device=device)
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        block = torch.from_numpy(np.ascontiguousarray(bb_u64[start:stop]).view(np.int64)).to(device)
        planes = ((block.unsqueeze(-1) >> bits) & 1).to(torch.uint8)
        out[start:stop] = planes.view(stop - start, 18, 8, 8)
    return out


class Split:
    """One split of the dataset, fully resident on the target device."""

    def __init__(self, x: torch.Tensor, y: torch.Tensor, motif: torch.Tensor,
                 source: torch.Tensor, name: str):
        self.x = x            # (N, 18, 8, 8) uint8
        self.y = y            # (N,)          float32
        self.motif = motif    # (N, 20)       float32
        self.source = source  # (N,)          uint8
        self.name = name

    def __len__(self) -> int:
        return self.x.shape[0]

    @property
    def device(self) -> torch.device:
        return self.x.device

    def material_counts(self) -> torch.Tensor:
        """(N, 10) piece counts -- the features behind alarm A3 and gate F2."""
        return self.x[:, _MATERIAL_PLANES].sum(dim=(2, 3)).float()

    def describe(self) -> str:
        n = len(self)
        pos = int((self.y == 1).sum())
        by_src = {int(s): int((self.source == s).sum()) for s in torch.unique(self.source)}
        mb = self.x.numel() / 1e6
        return (f"{self.name:5s} {n:>7,} rows | {pos:>7,} pos / {n - pos:>7,} neg "
                f"| sources {by_src} | {mb:.0f} MB resident")


def resolve_data_dir(data_dir: Path | None, expect: str = "train") -> Path:
    """Return the directory that actually contains ``<expect>.npz``.

    Three mount shapes are handled, because all three happen on Kaggle and each
    one otherwise dies with a FileNotFoundError in the first seconds of a session
    for a reason the message would not explain:

    1. **Flat** -- ``<mount>/train.npz``. The intended layout.
    2. **Nested** -- zipping the *folder* rather than its contents gives
       ``<mount>/config_steering/train.npz``. Resolved one level down.
    3. **Still archived** -- ``<mount>/something.zip``. This project's own notes
       (``docs/guides/KAGGLE_BEST_PRACTICES.md`` section 5) record that a
       multi-file ``.zip`` can survive Kaggle ingestion intact rather than being
       expanded. Extracted once into ``CSZERO_UNZIP_DIR`` (default
       ``/kaggle/working/_dataset`` when it exists, else a temp dir).

    Deliberately **one level down and deterministic**. A recursive ``**`` glob
    taking the first hit from an unordered list would silently pick one of two
    mounted dataset versions -- the stale-artefact family (commit 33ff814) in a
    different hat. Ambiguity raises instead of guessing.
    """
    root = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    if (root / f"{expect}.npz").exists():
        return root

    if root.is_dir():
        nested = sorted({q.parent for q in root.glob(f"*/{expect}.npz")})
        if len(nested) == 1:
            return nested[0]
        if len(nested) > 1:
            raise FileNotFoundError(
                f"{expect}.npz appears in {len(nested)} subdirectories of {root}: "
                f"{[str(d) for d in nested]}. Refusing to guess -- point --data-dir "
                f"at exactly one of them.")

        archives = sorted(root.glob("*.zip"))
        if len(archives) == 1:
            import zipfile
            target = Path(os.environ.get("CSZERO_UNZIP_DIR") or _default_unzip_dir())
            target.mkdir(parents=True, exist_ok=True)
            if not (target / f"{expect}.npz").exists():
                print(f"[data] mount holds an unexpanded archive; extracting "
                      f"{archives[0].name} -> {target}", flush=True)
                with zipfile.ZipFile(archives[0]) as z:
                    z.extractall(target)
            return resolve_data_dir(target, expect)
        if len(archives) > 1:
            raise FileNotFoundError(
                f"{root} holds {len(archives)} .zip archives and no {expect}.npz. "
                f"Refusing to guess which one is the dataset.")

    raise FileNotFoundError(
        f"{root / (expect + '.npz')} not found, and no single subdirectory or archive "
        f"of {root} contains it. Build the dataset with the config_steering builder, or "
        f"point --data-dir at the directory holding the .npz files. If you zipped a "
        f"folder rather than its contents, the mount is one level deeper than you think.")


def _default_unzip_dir() -> str:
    """Somewhere writable. /kaggle/working persists into the notebook output;
    a temp dir is the fallback everywhere else."""
    import tempfile
    if os.path.isdir("/kaggle/working"):
        return "/kaggle/working/_dataset"
    return os.path.join(tempfile.gettempdir(), "cszero_dataset")


def read_manifest(data_dir: Path | None = None) -> dict:
    """The dataset's manifest, or {} if absent.

    Recorded into every checkpoint. The 20 motif outputs are positional, so a
    rebuild that reorders ``theme_vocabulary_20`` silently changes what each
    output means -- with no shape change and no error. The manifest is how a
    later reader can tell.
    """
    import json
    try:
        data_dir = resolve_data_dir(data_dir)
    except FileNotFoundError:
        return {}
    path = data_dir / "manifest.json"
    if not path.exists():
        nested = list(data_dir.glob("**/manifest.json"))
        if nested:
            path = nested[0]
        else:
            return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_split(name: str, device: torch.device, data_dir: Path | None = None,
               limit: int | None = None, seed: int = 20260901) -> Split:
    """Load one split and move it, unpacked, onto ``device``.

    ``limit`` takes a class-balanced random subset -- this is how the B1 rung of
    the ladder is run without building a second dataset. Subsetting is stratified
    so a small run does not silently change the class balance.
    """
    data_dir = resolve_data_dir(data_dir, name)
    path = data_dir / f"{name}.npz"
    with np.load(path) as d:
        bb, y, motif = d["bb"], d["y"], d["motif"]
        source = d["source"] if "source" in d.files else np.zeros(len(y), dtype=np.uint8)

    if limit is not None and limit < len(y):
        rng = np.random.default_rng(seed)
        take = []
        for cls in (0, 1):
            idx = np.where(y == cls)[0]
            take.append(rng.choice(idx, min(limit // 2, len(idx)), replace=False))
        keep = np.sort(np.concatenate(take))
        bb, y, motif, source = bb[keep], y[keep], motif[keep], source[keep]

    return Split(
        x=_unpack(bb, device),
        y=torch.from_numpy(y.astype(np.float32)).to(device),
        motif=torch.from_numpy(motif.astype(np.float32)).to(device),
        source=torch.from_numpy(source.astype(np.uint8)).to(device),
        name=name,
    )


def batches(n: int, batch_size: int, generator: torch.Generator,
            device: torch.device, drop_last: bool = True):
    """Yield index tensors for one shuffled epoch.

    ``drop_last`` defaults to True. A ragged final batch changes the input shape,
    which forces ``torch.compile(mode="reduce-overhead")`` to re-capture its CUDA
    graph every epoch -- costing exactly what the mode was meant to save. With
    ~25 batches an epoch, dropping a few thousand rows from a freshly reshuffled
    permutation costs nothing.
    """
    # Generated on CPU and moved: torch.randperm with a *CUDA* generator has been
    # version-sensitive, and a 200k permutation costs microseconds either way.
    perm = torch.randperm(n, generator=generator).to(device)
    stop = (n // batch_size) * batch_size if drop_last else n
    for start in range(0, stop, batch_size):
        yield perm[start:start + batch_size]
