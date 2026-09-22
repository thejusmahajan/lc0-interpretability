"""Build the local puzzle database from the lichess puzzle export.

Supersedes scratch/build_puzzle_db.py, which carried a development-time
`if count >= 300000: break` that was never removed — the reason the local pool
was 300k rows out of the export's ~6.06M.

Builds to a temporary file and swaps it in only after a row-count check, so a
failed or interrupted run cannot leave a truncated database behind.

Two columns the old schema dropped are kept here:
  rating_deviation — lichess' own uncertainty on the rating. Puzzles with a
                     high RD have barely been played and their rating is
                     noise; filter on it when a band needs to mean something.
  nb_plays         — how many times the puzzle has been solved.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sqlite3
import sys
from collections import defaultdict

import zstandard as zstd

from backend.training.puzzle_db import DB_PATH

DATA_DIR = os.path.dirname(DB_PATH)
ZST_PATH = os.path.join(DATA_DIR, "lichess_db_puzzle.csv.zst")

# Matches the previous build's semantics: below this the puzzle is mostly
# community-flagged junk or ambiguous.
MIN_POPULARITY = 70


def build(zst_path: str = ZST_PATH, out_path: str | None = None,
          min_popularity: int = MIN_POPULARITY, limit: int | None = None) -> int:
    out_path = out_path or DB_PATH
    tmp_path = out_path + ".building"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    conn = sqlite3.connect(tmp_path)
    cur = conn.cursor()
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")
    cur.execute("""
        CREATE TABLE puzzles (
            id TEXT PRIMARY KEY,
            fen TEXT,
            moves TEXT,
            rating INT,
            rating_deviation INT,
            popularity INT,
            nb_plays INT,
            themes TEXT,
            opening_tags TEXT
        )""")
    cur.execute("""
        CREATE TABLE opening_motifs (
            opening_tag TEXT,
            theme TEXT,
            n INT
        )""")
    # Created empty and populated separately by puzzle_regime.build_flag_cache,
    # which needs a board replay per puzzle. It must exist even when empty:
    # puzzle_regime._sample LEFT JOINs it on every query, so omitting it breaks
    # deck building and session drawing outright.
    cur.execute("""
        CREATE TABLE puzzle_flags (
            id TEXT PRIMARY KEY,
            quiet_first INT, retreat_first INT, declined_capture INT
        )""")

    motif_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    kept = seen = 0
    batch: list[tuple] = []

    with open(zst_path, "rb") as f:
        with zstd.ZstdDecompressor().stream_reader(f) as reader:
            rows = csv.DictReader(io.TextIOWrapper(reader, encoding="utf-8"))
            for row in rows:
                seen += 1
                popularity = int(row.get("Popularity") or 0)
                if popularity < min_popularity:
                    continue

                themes = row.get("Themes") or ""
                opening_tags = row.get("OpeningTags") or ""
                batch.append((
                    row["PuzzleId"], row["FEN"], row["Moves"],
                    int(row.get("Rating") or 0),
                    int(row.get("RatingDeviation") or 0),
                    popularity,
                    int(row.get("NbPlays") or 0),
                    themes, opening_tags,
                ))

                if opening_tags and themes:
                    for tag in opening_tags.split():
                        for theme in themes.split():
                            motif_counts[tag][theme] += 1

                kept += 1
                if len(batch) >= 50000:
                    cur.executemany(
                        "INSERT OR REPLACE INTO puzzles VALUES (?,?,?,?,?,?,?,?,?)", batch)
                    batch.clear()
                    conn.commit()
                    print(f"  kept {kept:,} / seen {seen:,}", flush=True)
                if limit and kept >= limit:
                    break

    if batch:
        cur.executemany("INSERT OR REPLACE INTO puzzles VALUES (?,?,?,?,?,?,?,?,?)", batch)
        conn.commit()

    print(f"  aggregating {len(motif_counts):,} opening tags...", flush=True)
    cur.executemany(
        "INSERT INTO opening_motifs VALUES (?,?,?)",
        [(tag, theme, n) for tag, themes in motif_counts.items()
         for theme, n in themes.items()])

    cur.execute("CREATE INDEX idx_rating ON puzzles(rating)")
    cur.execute("CREATE INDEX idx_rating_pop ON puzzles(rating, popularity)")
    cur.execute("CREATE INDEX idx_themes ON puzzles(themes)")
    conn.commit()

    total = cur.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0]
    conn.close()

    if total != kept:
        raise RuntimeError(f"row-count check failed: inserted {kept}, table has {total}")
    if not limit and total < 1_000_000:
        raise RuntimeError(
            f"only {total} rows built from a ~6M export — refusing to swap in a "
            f"truncated database. This is the bug the old script shipped with.")

    swap_in(tmp_path, out_path)
    return total


def swap_in(tmp_path: str, out_path: str, attempts: int = 12) -> None:
    """Move the freshly built database into place, retrying on Windows locks.

    os.replace fails with WinError 32/5 while any reader still holds the old
    file — an antivirus scan, or a sqlite connection that has not been closed.
    The build itself is expensive, so a transient lock must not discard it.
    """
    import time

    backup = out_path + ".previous"
    for i in range(attempts):
        try:
            if os.path.exists(out_path):
                if os.path.exists(backup):
                    os.remove(backup)
                os.replace(out_path, backup)
                print(f"  previous database kept at {os.path.basename(backup)}")
            os.replace(tmp_path, out_path)
            return
        except PermissionError as exc:
            if i == attempts - 1:
                raise RuntimeError(
                    f"could not swap in the new database after {attempts} attempts "
                    f"({exc}). The build is intact at {tmp_path!r} — close any "
                    f"process holding {out_path!r} and re-run with --swap-only."
                ) from exc
            time.sleep(2 * (i + 1))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="build_puzzle_db", description=__doc__.splitlines()[0])
    ap.add_argument("--min-popularity", type=int, default=MIN_POPULARITY)
    ap.add_argument("--limit", type=int, help="stop after N kept rows (testing only)")
    ap.add_argument("--swap-only", action="store_true",
                    help="skip the build; just swap in an existing .building file")
    a = ap.parse_args(argv)

    if not os.path.exists(ZST_PATH):
        sys.exit(f"missing export: {ZST_PATH}")
    if a.swap_only:
        swap_in(DB_PATH + ".building", DB_PATH)
        print(f"swapped in {DB_PATH}")
        return
    print(f"building from {os.path.basename(ZST_PATH)} (popularity >= {a.min_popularity})")
    total = build(min_popularity=a.min_popularity, limit=a.limit)
    print(f"done: {total:,} puzzles at {DB_PATH}")


if __name__ == "__main__":
    main()
