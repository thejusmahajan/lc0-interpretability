"""Build and refresh the kaggle_files bundle from the current repository HEAD.

Ensures repeatable, deterministic bundle assembly for Kaggle GPU execution:
  - backend/ (complete app logic)
  - scripts/
  - engine/ (LC0 binary, weights: 791556.pb.gz, BT3-768x15x24h-swa-2790000.pb.gz, bt3.onnx, lc0.exe)
  - games_of_derdiedasdie/ (lichess_derdiedasdie_2026-07-21.pgn, test_subset.pgn)
  - requirements.txt, pyproject.toml, README_KAGGLE.md
  - diagnose_on_kaggle.py and diagnose_on_kaggle.ipynb

Verifies SHA-256 hashes between repo source files and bundle destination files.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.py2ipynb import convert_py_to_ipynb

BUNDLE_DIR = REPO_ROOT / "kaggle_files"

CRITICAL_ENGINE_FILES = [
    "lc0.exe",
    "791556.pb.gz",
    "BT3-768x15x24h-swa-2790000.pb.gz",
    "bt3.onnx",
]


def sha256_file(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def copy_tree_filtered(src_dir: Path, dst_dir: Path, ignore_patterns: set[str] | None = None) -> None:
    """Copy directory tree filtering out caches and temporary files."""
    if ignore_patterns is None:
        ignore_patterns = {"__pycache__", ".pytest_cache", ".git", ".idea", ".vscode"}

    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.name in ignore_patterns or item.name.endswith(".pyc"):
            continue
        dst_item = dst_dir / item.name
        if item.is_dir():
            copy_tree_filtered(item, dst_item, ignore_patterns)
        else:
            shutil.copy2(item, dst_item)


def build_bundle() -> dict[str, str]:
    """Rebuild the kaggle_files bundle and return verified SHA-256 hashes."""
    print(f"=== Rebuilding Kaggle Bundle at: {BUNDLE_DIR} ===")
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    # Clean any stale __pycache__ in bundle
    for root, dirs, _ in os.walk(BUNDLE_DIR):
        for d in dirs:
            if d in ("__pycache__", ".pytest_cache"):
                shutil.rmtree(Path(root) / d, ignore_errors=True)

    # 1. Sync backend/
    print("Syncing backend/ ...")
    copy_tree_filtered(REPO_ROOT / "backend", BUNDLE_DIR / "backend")

    # 2. Sync scripts/
    print("Syncing scripts/ ...")
    copy_tree_filtered(REPO_ROOT / "scripts", BUNDLE_DIR / "scripts")

    # 3. Sync games_of_derdiedasdie/
    print("Syncing games_of_derdiedasdie/ ...")
    games_dst = BUNDLE_DIR / "games_of_derdiedasdie"
    games_dst.mkdir(parents=True, exist_ok=True)
    for pgn_name in ["lichess_derdiedasdie_2026-07-21.pgn", "test_subset.pgn"]:
        src_pgn = REPO_ROOT / "games_of_derdiedasdie" / pgn_name
        if src_pgn.exists():
            shutil.copy2(src_pgn, games_dst / pgn_name)

    # 4. Sync engine/
    print("Syncing engine/ critical binaries & weights ...")
    engine_dst = BUNDLE_DIR / "engine"
    engine_dst.mkdir(parents=True, exist_ok=True)
    for fname in CRITICAL_ENGINE_FILES:
        src_f = REPO_ROOT / "engine" / fname
        if src_f.exists():
            dst_f = engine_dst / fname
            # Only copy if missing or size differs to save disk I/O on 400MB onnx
            if not dst_f.exists() or dst_f.stat().st_size != src_f.stat().st_size:
                print(f"  Copying engine/{fname} ({src_f.stat().st_size / 1e6:.1f} MB)...")
                shutil.copy2(src_f, dst_f)
            else:
                print(f"  engine/{fname} up to date.")
        else:
            print(f"  WARNING: repo engine/{fname} not found!")

    # 5. Sync root config files
    print("Syncing configuration files ...")
    shutil.copy2(REPO_ROOT / "pyproject.toml", BUNDLE_DIR / "pyproject.toml")

    # Write requirements.txt with full dependencies
    reqs_content = """python-chess
onnx
onnx2torch
lczerolens
python-dotenv
numpy
fastapi
uvicorn
google-generativeai
tqdm
anyio
nest_asyncio
"""
    (BUNDLE_DIR / "requirements.txt").write_text(reqs_content, encoding="utf-8")

    # Convert diagnose_on_kaggle.py to .ipynb if .py exists
    py_script = BUNDLE_DIR / "diagnose_on_kaggle.py"
    ipynb_script = BUNDLE_DIR / "diagnose_on_kaggle.ipynb"
    if py_script.exists():
        print("Generating diagnose_on_kaggle.ipynb ...")
        convert_py_to_ipynb(py_script, ipynb_script)

    # 6. Verify SHA-256 for Checkpoint 1
    print("\n=== Verifying Checkpoint 1: SHA-256 Checksums ===")
    hashes: dict[str, str] = {}
    for fname in CRITICAL_ENGINE_FILES:
        repo_f = REPO_ROOT / "engine" / fname
        bundle_f = engine_dst / fname
        if repo_f.exists() and bundle_f.exists():
            repo_hash = sha256_file(repo_f)
            bundle_hash = sha256_file(bundle_f)
            assert repo_hash == bundle_hash, f"Hash mismatch for {fname}: repo {repo_hash} != bundle {bundle_hash}"
            hashes[fname] = repo_hash
            print(f"OK: {fname}")
            print(f"    SHA-256: {repo_hash}")
        else:
            print(f"SKIP (missing): {fname}")

    print("\n=== Rebuilt Bundle Directory Summary ===")
    total_files = 0
    total_bytes = 0
    for root, _, files in os.walk(BUNDLE_DIR):
        for f in files:
            p = Path(root) / f
            total_files += 1
            total_bytes += p.stat().st_size

    print(f"Total files in bundle: {total_files}")
    print(f"Total bundle size: {total_bytes / (1024 * 1024):.2f} MB ({total_bytes} bytes)")
    return hashes


if __name__ == "__main__":
    build_bundle()
