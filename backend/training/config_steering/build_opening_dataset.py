"""Opening Dataset builder for configuration steering (Brief 2026-09-03).

Builds the opening training dataset for configuration steering:
  - Positive class (s_err): 60,000 opening puzzles (rating 1500..2200, themes LIKE '%opening%')
      * Oversample sharp subset (themes contain 'sacrifice' or 'kingsideAttack')
      * Cap any one opening family at 15% of positives (tag truncated at 2nd underscore, keeping Accepted/Declined)
      * Balanced turn: 50% WTM, 50% BTM
  - Negative pool N1 (n1_spent): spent tactic positions from opening puzzles:
      * puzzle ids disjoint from positives
      * excluding post-solution positions in check (board.is_check())
      * excluding puzzles whose themes contain 'mate'
  - Negative pool N2 (n2_quiet): real quiet opening play from lichess_derdiedasdie_2026-07-21.pgn:
      * sampled within the first 20 plies only (plies 1 to 20)
  - Matching:
      * Extended key: (material_key, phase_bucket, in_check, mobility_bucket)
      * Exact bucket matching without replacement, partitioned by turn (WTM/BTM)
      * Priority: N1 over N2 (prefer N1 as it comes from same population as positives).
      * Unmatched positives dropped, never back-filled.
  - Alarms:
      A1: side-to-move balance (50 +- 2% in both classes)
      A2: material_key overlap (positives vs negatives top-10 >= 8)
      A3: 10-feature material-only Logistic Regression AUC on val (< 0.65)
      A4: 14-feature cheap-tactical + material Logistic Regression AUC on val (< 0.60)
      A5: 5-feature phase-only Logistic Regression AUC on val (< 0.60)
  - Exports:
      train.npz, val.npz, test.npz (with arrays: bb, y, motif, source, opening_family, sharp),
      manifest.json, STATS.md
  - Archive:
      dist/config_steering_opening.zip (flat)
"""

from __future__ import annotations

import collections
import datetime
import json
from pathlib import Path
import random
import sqlite3
import time
from typing import Any
import zipfile

import chess
import chess.pgn
import numpy as np

from backend.training.config_steering.build_dataset import (
    compute_material_and_phase,
    compute_tactical_features,
    get_split_name,
    compute_roc_auc,
    fit_logistic_regression_and_auc,
)
from backend.training.config_steering.encode import encode

DEFAULT_DB_PATH = Path("data/puzzles/puzzles.sqlite")
DEFAULT_PGN_PATH = Path("games_of_derdiedasdie/lichess_derdiedasdie_2026-07-21.pgn")
DEFAULT_OUTPUT_DIR = Path("data/training/config_steering_opening")
DEFAULT_ZIP_PATH = Path("dist/config_steering_opening.zip")

RANDOM_SEED = 20260901


def parse_opening_family(tag_str: str) -> str:
    """Roll opening_tags up to family key: truncated at second underscore,

    preserving any Accepted or Declined token in the key.
    Example: Italian_Game_Evans_Gambit_Declined -> Italian_Game_Declined
    Example: Danish_Gambit_Accepted_Classical_Defense -> Danish_Gambit_Accepted
    Example: Sicilian_Defense_Bowdler_Attack -> Sicilian_Defense
    """
    if not tag_str or not tag_str.strip():
        return "Unknown"
    tokens = tag_str.strip().split()
    chosen_tag = tokens[-1] if len(tokens) > 1 else tokens[0]
    parts = chosen_tag.split("_")
    base = "_".join(parts[:2]) if len(parts) >= 2 else parts[0]
    acc_dec = None
    for p in parts:
        if p.lower() in ("accepted", "declined"):
            acc_dec = p.capitalize()
            break
    if acc_dec and acc_dec.lower() not in base.lower():
        return f"{base}_{acc_dec}"
    return base


def is_sharp_opening(themes_str: str) -> bool:
    """True if puzzle carries sacrifice or kingsideAttack themes."""
    t_lower = (themes_str or "").lower()
    return ("sacrifice" in t_lower) or ("kingsideattack" in t_lower)


def compute_a5_features(board: chess.Board) -> tuple[float, float, float, float, float]:
    """Compute 5 phase-only features for Alarm A5:

    1. total piece count (all non-empty squares: pawns + pieces + kings)
    2. pawn count (white pawns + black pawns)
    3. castling rights count collapsed to a count (0 to 4)
    4. in_check (0.0 or 1.0)
    5. n_legal_moves
    """
    total_pieces = float(len(board.piece_map()))
    pawn_count = float(len(board.pieces(chess.PAWN, chess.WHITE)) + len(board.pieces(chess.PAWN, chess.BLACK)))
    castling_count = float(
        int(board.has_kingside_castling_rights(chess.WHITE))
        + int(board.has_queenside_castling_rights(chess.WHITE))
        + int(board.has_kingside_castling_rights(chess.BLACK))
        + int(board.has_queenside_castling_rights(chess.BLACK))
    )
    in_check = 1.0 if board.is_check() else 0.0
    n_legal_moves = float(len(list(board.legal_moves)))
    return (total_pieces, pawn_count, castling_count, in_check, n_legal_moves)


def build_opening_dataset(
    db_path: Path | str = DEFAULT_DB_PATH,
    pgn_path: Path | str = DEFAULT_PGN_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    zip_path: Path | str = DEFAULT_ZIP_PATH,
    target_positives: int = 60000,
    rating_min: int = 1500,
    rating_max: int = 2200,
    max_family_fraction: float = 0.15,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Build the opening configuration steering dataset."""
    start_time_all = time.time()
    random.seed(seed)
    np.random.seed(seed)

    db_path = Path(db_path)
    pgn_path = Path(pgn_path)
    output_dir = Path(output_dir)
    zip_path = Path(zip_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # STEP 2: Positive Class (s_err) from Opening Puzzles
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 2: Scanning & Sampling Opening Positives (s_err)...")
    t0_pos = time.time()
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Linear streaming scan over the rating window
    cur.execute(
        "SELECT id, fen, moves, rating, themes, opening_tags FROM puzzles WHERE rating BETWEEN ? AND ?",
        (rating_min, rating_max),
    )

    pool_sharp_w: list[dict[str, Any]] = []
    pool_sharp_b: list[dict[str, Any]] = []
    pool_nonsharp_w: list[dict[str, Any]] = []
    pool_nonsharp_b: list[dict[str, Any]] = []
    n1_eligible_leftovers: list[tuple[str, str, str, int, str, str]] = []

    total_scanned = 0
    total_opening_found = 0

    while True:
        rows = cur.fetchmany(50000)
        if not rows:
            break
        total_scanned += len(rows)
        for pid, fen, moves, rating, themes, opening_tags in rows:
            t_lower = (themes or "").lower()
            if "opening" in t_lower:
                total_opening_found += 1
                board = chess.Board(fen)
                is_wtm = (board.turn == chess.WHITE)
                is_sharp = is_sharp_opening(themes)
                fam = parse_opening_family(opening_tags)

                mat_key, phase_bucket, counts = compute_material_and_phase(board)
                in_check, n_legal, cap_avail, n_checks, mobility_bucket = compute_tactical_features(board)
                features_14 = counts + (float(in_check), float(n_legal), float(cap_avail), float(n_checks))
                features_a5 = compute_a5_features(board)
                bb = encode(board)

                item = {
                    "puzzle_id": pid,
                    "bb": bb,
                    "label": 1,
                    "source": 0,  # 0 = s_err
                    "fen": fen,
                    "moves": moves,
                    "material_key": mat_key,
                    "phase_bucket": phase_bucket,
                    "in_check": in_check,
                    "n_legal_moves": n_legal,
                    "capture_available": cap_avail,
                    "n_checks_available": n_checks,
                    "mobility_bucket": mobility_bucket,
                    "piece_counts": counts,
                    "features_14": features_14,
                    "features_a5": features_a5,
                    "rating": rating,
                    "themes": themes,
                    "opening_tags": opening_tags,
                    "opening_family": fam,
                    "sharp": is_sharp,
                    "is_white_to_move": is_wtm,
                }

                if is_sharp:
                    if is_wtm:
                        pool_sharp_w.append(item)
                    else:
                        pool_sharp_b.append(item)
                else:
                    if is_wtm:
                        pool_nonsharp_w.append(item)
                    else:
                        pool_nonsharp_b.append(item)

    conn.close()
    print(f"Scanned {total_scanned} rows in rating window [{rating_min}, {rating_max}]")
    print(f"Opening puzzles found: {total_opening_found}")
    print(f"Pool breakdown: sharp_W={len(pool_sharp_w)}, sharp_B={len(pool_sharp_b)}, nonsharp_W={len(pool_nonsharp_w)}, nonsharp_B={len(pool_nonsharp_b)}")

    # Target constraints
    target_per_turn = target_positives // 2  # 30,000 WTM, 30,000 BTM
    max_per_family = int(max_family_fraction * target_positives)  # 15% = 9,000

    # Deterministic shuffling
    random.shuffle(pool_sharp_w)
    random.shuffle(pool_sharp_b)
    random.shuffle(pool_nonsharp_w)
    random.shuffle(pool_nonsharp_b)

    positives_w: list[dict[str, Any]] = []
    positives_b: list[dict[str, Any]] = []
    pos_family_counts: collections.Counter[str] = collections.Counter()
    positive_ids_set: set[str] = set()

    # Pass 1: Prioritize sharp opening puzzles (Constraint 2a) up to available, respecting family cap (Constraint 2b)
    for p in pool_sharp_w:
        fam = p["opening_family"]
        if len(positives_w) < target_per_turn and pos_family_counts[fam] < max_per_family:
            positives_w.append(p)
            pos_family_counts[fam] += 1
            positive_ids_set.add(p["puzzle_id"])
        else:
            n1_eligible_leftovers.append((p["puzzle_id"], p["fen"], p["moves"], p["rating"], p["themes"], p["opening_tags"]))

    for p in pool_sharp_b:
        fam = p["opening_family"]
        if len(positives_b) < target_per_turn and pos_family_counts[fam] < max_per_family:
            positives_b.append(p)
            pos_family_counts[fam] += 1
            positive_ids_set.add(p["puzzle_id"])
        else:
            n1_eligible_leftovers.append((p["puzzle_id"], p["fen"], p["moves"], p["rating"], p["themes"], p["opening_tags"]))

    sharp_positives_kept = len(positives_w) + len(positives_b)

    # Pass 2: Fill remaining positive slots from non-sharp opening puzzles respecting family cap and turn balance
    for p in pool_nonsharp_w:
        if len(positives_w) < target_per_turn:
            fam = p["opening_family"]
            if pos_family_counts[fam] < max_per_family:
                positives_w.append(p)
                pos_family_counts[fam] += 1
                positive_ids_set.add(p["puzzle_id"])
            else:
                n1_eligible_leftovers.append((p["puzzle_id"], p["fen"], p["moves"], p["rating"], p["themes"], p["opening_tags"]))
        else:
            n1_eligible_leftovers.append((p["puzzle_id"], p["fen"], p["moves"], p["rating"], p["themes"], p["opening_tags"]))

    for p in pool_nonsharp_b:
        if len(positives_b) < target_per_turn:
            fam = p["opening_family"]
            if pos_family_counts[fam] < max_per_family:
                positives_b.append(p)
                pos_family_counts[fam] += 1
                positive_ids_set.add(p["puzzle_id"])
            else:
                n1_eligible_leftovers.append((p["puzzle_id"], p["fen"], p["moves"], p["rating"], p["themes"], p["opening_tags"]))
        else:
            n1_eligible_leftovers.append((p["puzzle_id"], p["fen"], p["moves"], p["rating"], p["themes"], p["opening_tags"]))

    positives = positives_w + positives_b
    total_positives_kept = len(positives)
    achieved_sharp_share = sharp_positives_kept / total_positives_kept
    t_pos = time.time() - t0_pos

    top15_families = pos_family_counts.most_common(15)

    print(f"Total positives kept: {total_positives_kept} (WTM: {len(positives_w)}, BTM: {len(positives_b)})")
    print(f"Sharp positives kept: {sharp_positives_kept} (Achieved share: {achieved_sharp_share * 100:.2f}%)")
    print(f"Distinct families in positives: {len(pos_family_counts)}")
    print(f"Top 15 families (max allowed {max_family_fraction * 100:.1f}% = {max_per_family}):")
    for fam, cnt in top15_families:
        print(f"  {fam}: {cnt} ({cnt / total_positives_kept * 100:.2f}%)")
    print(f"Positive scan wall-clock: {t_pos:.2f}s")

    # -------------------------------------------------------------------------
    # STEP 3: Negative Pools (N1 spent opening & N2 quiet opening)
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 3: Extracting Opening Negative Pools (N1 spent & N2 quiet)...")

    # Pool N1: spent tactics from disjoint opening puzzles
    t0_n1 = time.time()
    n1_negatives: list[dict[str, Any]] = []
    n1_dropped_check = 0
    n1_dropped_mate = 0

    for pid, fen, moves_str, rating, themes, opening_tags in n1_eligible_leftovers:
        if pid in positive_ids_set:
            continue
        # Exclude puzzles whose themes contain 'mate'
        if "mate" in (themes or "").lower().split():
            n1_dropped_mate += 1
            continue

        board = chess.Board(fen)
        for m_str in moves_str.split():
            board.push(chess.Move.from_uci(m_str))

        # Exclude if post-solution position is in check
        if board.is_check():
            n1_dropped_check += 1
            continue

        bb = encode(board)
        mat_key, phase_bucket, counts = compute_material_and_phase(board)
        in_check, n_legal, cap_avail, n_checks, mobility_bucket = compute_tactical_features(board)
        features_14 = counts + (float(in_check), float(n_legal), float(cap_avail), float(n_checks))
        features_a5 = compute_a5_features(board)
        is_wtm = (board.turn == chess.WHITE)
        fam = parse_opening_family(opening_tags)
        is_sharp = is_sharp_opening(themes)

        n1_negatives.append({
            "puzzle_id": pid,
            "bb": bb,
            "label": 0,
            "source": 1,  # 1 = n1_spent
            "material_key": mat_key,
            "phase_bucket": phase_bucket,
            "in_check": in_check,
            "n_legal_moves": n_legal,
            "capture_available": cap_avail,
            "n_checks_available": n_checks,
            "mobility_bucket": mobility_bucket,
            "piece_counts": counts,
            "features_14": features_14,
            "features_a5": features_a5,
            "rating": rating,
            "themes": themes,
            "opening_tags": opening_tags,
            "opening_family": fam,
            "sharp": is_sharp,
            "is_white_to_move": is_wtm,
        })
    t_n1 = time.time() - t0_n1
    print(f"Pool N1 (n1_spent) size after exclusions: {len(n1_negatives)} (dropped {n1_dropped_check} in-check, {n1_dropped_mate} mate) ({t_n1:.2f}s)")

    # Pool N2: real quiet opening play from games within first 20 plies
    t0_n2 = time.time()
    n2_negatives: list[dict[str, Any]] = []
    total_n2_positions_scanned = 0

    with open(pgn_path, "r", encoding="utf-8", errors="ignore") as f:
        game_idx = 0
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            moves = list(game.mainline_moves())
            max_ply = min(20, len(moves))
            board = game.board()
            ply = 0
            for m in moves[:max_ply]:
                board.push(m)
                ply += 1
                total_n2_positions_scanned += 1
                bb = encode(board)
                mat_key, phase_bucket, counts = compute_material_and_phase(board)
                in_check, n_legal, cap_avail, n_checks, mobility_bucket = compute_tactical_features(board)
                features_14 = counts + (float(in_check), float(n_legal), float(cap_avail), float(n_checks))
                features_a5 = compute_a5_features(board)
                is_wtm = (board.turn == chess.WHITE)

                n2_negatives.append({
                    "puzzle_id": f"game_{game_idx}_ply_{ply}",
                    "game_idx": game_idx,
                    "bb": bb,
                    "label": 0,
                    "source": 2,  # 2 = n2_quiet
                    "material_key": mat_key,
                    "phase_bucket": phase_bucket,
                    "in_check": in_check,
                    "n_legal_moves": n_legal,
                    "capture_available": cap_avail,
                    "n_checks_available": n_checks,
                    "mobility_bucket": mobility_bucket,
                    "piece_counts": counts,
                    "features_14": features_14,
                    "features_a5": features_a5,
                    "rating": None,
                    "themes": "",
                    "opening_tags": "",
                    "opening_family": "game_play",
                    "sharp": False,
                    "is_white_to_move": is_wtm,
                })
            game_idx += 1
    t_n2 = time.time() - t0_n2
    print(f"Total N2 positions scanned (first 20 plies): {total_n2_positions_scanned} across {game_idx} games")
    print(f"Pool N2 (n2_quiet) size: {len(n2_negatives)} ({t_n2:.2f}s)")

    # -------------------------------------------------------------------------
    # STEP 4: Matching (Extended Key, Prefer N1 over N2)
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 4: Matching Opening Negatives to Positives (Preferring N1)...")
    t0_match = time.time()

    # Bucket negatives by extended 4-tuple key: (material_key, phase_bucket, in_check, mobility_bucket)
    # partitioned by is_white_to_move
    n1_buckets: dict[tuple[str, int, bool, int], dict[bool, list[dict[str, Any]]]] = (
        collections.defaultdict(lambda: {True: [], False: []})
    )
    for neg in n1_negatives:
        k = (neg["material_key"], neg["phase_bucket"], neg["in_check"], neg["mobility_bucket"])
        n1_buckets[k][neg["is_white_to_move"]].append(neg)

    n2_buckets: dict[tuple[str, int, bool, int], dict[bool, list[dict[str, Any]]]] = (
        collections.defaultdict(lambda: {True: [], False: []})
    )
    for neg in n2_negatives:
        k = (neg["material_key"], neg["phase_bucket"], neg["in_check"], neg["mobility_bucket"])
        n2_buckets[k][neg["is_white_to_move"]].append(neg)

    # Deterministic shuffle within buckets
    for subdict in n1_buckets.values():
        for items in subdict.values():
            random.shuffle(items)
    for subdict in n2_buckets.values():
        for items in subdict.values():
            random.shuffle(items)

    matched_positives: list[dict[str, Any]] = []
    matched_negatives: list[dict[str, Any]] = []
    matched_n1_count = 0
    matched_n2_count = 0

    positives_order = list(positives)
    random.shuffle(positives_order)

    for pos in positives_order:
        k = (pos["material_key"], pos["phase_bucket"], pos["in_check"], pos["mobility_bucket"])
        wtm = pos["is_white_to_move"]

        # Priority 1: N1 (spent opening tactic) with same turn - PREFER N1
        if n1_buckets[k][wtm]:
            neg = n1_buckets[k][wtm].pop()
            matched_positives.append(pos)
            matched_negatives.append(neg)
            matched_n1_count += 1
        # Priority 2: N2 (quiet opening play) with same turn
        elif n2_buckets[k][wtm]:
            neg = n2_buckets[k][wtm].pop()
            matched_positives.append(pos)
            matched_negatives.append(neg)
            matched_n2_count += 1
        else:
            # Positive dropped with no match - never back-filled
            pass

    match_rate = len(matched_positives) / len(positives)
    t_match = time.time() - t0_match

    print(f"Match rate: {match_rate * 100:.2f}% ({len(matched_positives)} / {len(positives)})")
    print(f"Matched positives: {len(matched_positives)}")
    print(f"Matched negatives: {len(matched_negatives)}")
    print(f"Matched N1 (spent): {matched_n1_count} ({matched_n1_count / len(matched_negatives) * 100:.2f}%)")
    print(f"Matched N2 (quiet): {matched_n2_count} ({matched_n2_count / len(matched_negatives) * 100:.2f}%)")

    # -------------------------------------------------------------------------
    # STEP 5: Splitting, Writing NPZs, and Archiving
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 5: Splitting and Exporting Datasets...")
    t0_split = time.time()

    # 20-theme vocabulary across kept positives only
    theme_counter: collections.Counter[str] = collections.Counter()
    for pos in matched_positives:
        if pos["themes"]:
            for t in pos["themes"].split():
                theme_counter[t] += 1

    top20_themes = [t for t, _ in theme_counter.most_common(20)]
    theme_to_idx = {t: i for i, t in enumerate(top20_themes)}

    def make_motif(themes_str: str) -> np.ndarray:
        vec = np.zeros(20, dtype=np.uint8)
        if themes_str:
            for t in themes_str.split():
                if t in theme_to_idx:
                    vec[theme_to_idx[t]] = 1
        return vec

    splits_data: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "val": [],
        "test": [],
    }

    for pos in matched_positives:
        s_name = get_split_name(pos["puzzle_id"])
        pos["motif"] = make_motif(pos["themes"])
        splits_data[s_name].append(pos)

    for neg in matched_negatives:
        if neg["source"] == 2:
            s_name = get_split_name(f"game_{neg['game_idx']}")
        else:
            s_name = get_split_name(neg["puzzle_id"])
        neg["motif"] = make_motif(neg["themes"])
        splits_data[s_name].append(neg)

    manifest_counts: dict[str, Any] = {}
    overall_counts: dict[str, Any] = {
        "total": 0,
        "positives": 0,
        "negatives": 0,
        "sharp_positives": 0,
        "sources": {"s_err": 0, "n1_spent": 0, "n2_quiet": 0},
    }

    for s_name in ["train", "val", "test"]:
        recs = splits_data[s_name]
        random.shuffle(recs)
        bb_arr = np.stack([r["bb"] for r in recs]).astype(np.uint64)
        y_arr = np.array([r["label"] for r in recs], dtype=np.uint8)
        motif_arr = np.stack([r["motif"] for r in recs]).astype(np.uint8)
        source_arr = np.array([r["source"] for r in recs], dtype=np.uint8)
        opening_family_arr = np.array([str(r.get("opening_family", "")) for r in recs], dtype=object)
        sharp_arr = np.array([bool(r.get("sharp", False)) for r in recs], dtype=bool)

        npz_file = output_dir / f"{s_name}.npz"
        np.savez(
            npz_file,
            bb=bb_arr,
            y=y_arr,
            motif=motif_arr,
            source=source_arr,
            opening_family=opening_family_arr,
            sharp=sharp_arr,
        )

        n_pos = sum(1 for r in recs if r["label"] == 1)
        n_neg = sum(1 for r in recs if r["label"] == 0)
        n_sharp_pos = sum(1 for r in recs if r["label"] == 1 and r.get("sharp", False))
        n_s_err = sum(1 for r in recs if r["source"] == 0)
        n_n1 = sum(1 for r in recs if r["source"] == 1)
        n_n2 = sum(1 for r in recs if r["source"] == 2)

        manifest_counts[s_name] = {
            "total": len(recs),
            "positives": n_pos,
            "negatives": n_neg,
            "sharp_positives": n_sharp_pos,
            "sources": {
                "s_err": n_s_err,
                "n1_spent": n_n1,
                "n2_quiet": n_n2,
            },
        }

        overall_counts["total"] += len(recs)
        overall_counts["positives"] += n_pos
        overall_counts["negatives"] += n_neg
        overall_counts["sharp_positives"] += n_sharp_pos
        overall_counts["sources"]["s_err"] += n_s_err
        overall_counts["sources"]["n1_spent"] += n_n1
        overall_counts["sources"]["n2_quiet"] += n_n2

    manifest_data = {
        "dataset_name": "config_steering_opening",
        "build_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "seed": seed,
        "rating_window": [rating_min, rating_max],
        "target_positives": target_positives,
        "achieved_sharp_share_before_match": float(achieved_sharp_share),
        "achieved_sharp_share_after_match": float(overall_counts["sharp_positives"] / max(1, overall_counts["positives"])),
        "max_family_fraction": max_family_fraction,
        "theme_vocabulary_20": top20_themes,
        "counts": {
            **manifest_counts,
            "overall": overall_counts,
        },
    }

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Build flat zip archive
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname in ["train.npz", "val.npz", "test.npz", "manifest.json"]:
            fpath = output_dir / fname
            zf.write(fpath, arcname=fname)

    t_split = time.time() - t0_split

    # -------------------------------------------------------------------------
    # STEP 6: Alarms A1, A2, A3, A4, and A5
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 6: Evaluating Alarms (A1, A2, A3, A4, A5)...")
    t0_alarms = time.time()

    # Alarm A1: Side-to-move balance
    pos_w_ratio = sum(1 for r in matched_positives if r["is_white_to_move"]) / len(matched_positives)
    neg_w_ratio = sum(1 for r in matched_negatives if r["is_white_to_move"]) / len(matched_negatives)
    a1_pass = (abs(pos_w_ratio - 0.50) <= 0.02) and (abs(neg_w_ratio - 0.50) <= 0.02)

    # Alarm A2: Top-10 material_key overlap
    pos_top10 = collections.Counter(r["material_key"] for r in matched_positives).most_common(10)
    neg_top10 = collections.Counter(r["material_key"] for r in matched_negatives).most_common(10)
    pos_top10_keys = set(k for k, _ in pos_top10)
    neg_top10_keys = set(k for k, _ in neg_top10)
    overlap_count = len(pos_top10_keys.intersection(neg_top10_keys))
    a2_pass = overlap_count >= 8

    # Alarm A3: Material-only Logistic Regression AUC on val
    train_recs = splits_data["train"]
    val_recs = splits_data["val"]

    X_train_mat = np.array([r["piece_counts"] for r in train_recs], dtype=np.float32)
    y_train = np.array([r["label"] for r in train_recs], dtype=np.uint8)

    X_val_mat = np.array([r["piece_counts"] for r in val_recs], dtype=np.float32)
    y_val = np.array([r["label"] for r in val_recs], dtype=np.uint8)

    a3_auc, _ = fit_logistic_regression_and_auc(X_train_mat, y_train, X_val_mat, y_val, seed=seed)
    a3_pass = a3_auc < 0.65

    # Alarm A4: 14-feature Logistic Regression AUC on val
    X_train_14 = np.array([r["features_14"] for r in train_recs], dtype=np.float32)
    X_val_14 = np.array([r["features_14"] for r in val_recs], dtype=np.float32)

    a4_auc_overall, val_probs_14 = fit_logistic_regression_and_auc(X_train_14, y_train, X_val_14, y_val, seed=seed)
    a4_pass = a4_auc_overall < 0.60

    # A4 broken down by negative source on val set
    val_sources = np.array([r["source"] for r in val_recs], dtype=np.uint8)
    mask_n1 = (val_sources == 0) | (val_sources == 1)
    a4_auc_n1 = compute_roc_auc(y_val[mask_n1], val_probs_14[mask_n1]) if sum(val_sources == 1) > 0 else 0.5

    mask_n2 = (val_sources == 0) | (val_sources == 2)
    a4_auc_n2 = compute_roc_auc(y_val[mask_n2], val_probs_14[mask_n2]) if sum(val_sources == 2) > 0 else 0.5

    # Alarm A5: Phase-only 5-feature Logistic Regression AUC on val
    X_train_a5 = np.array([r["features_a5"] for r in train_recs], dtype=np.float32)
    X_val_a5 = np.array([r["features_a5"] for r in val_recs], dtype=np.float32)

    a5_auc, val_probs_a5 = fit_logistic_regression_and_auc(X_train_a5, y_train, X_val_a5, y_val, seed=seed)
    a5_pass = a5_auc < 0.60

    # Single-feature AUCs on validation split
    auc_in_check = compute_roc_auc(y_val, X_val_14[:, 10])
    auc_n_legal = compute_roc_auc(y_val, X_val_14[:, 11])
    auc_cap_avail = compute_roc_auc(y_val, X_val_14[:, 12])
    auc_n_checks = compute_roc_auc(y_val, X_val_14[:, 13])

    auc_total_pieces = compute_roc_auc(y_val, X_val_a5[:, 0])
    auc_pawn_count = compute_roc_auc(y_val, X_val_a5[:, 1])
    auc_castling_count = compute_roc_auc(y_val, X_val_a5[:, 2])

    # Means comparison on validation split
    pos_mask_val = (y_val == 1)
    neg_mask_val = (y_val == 0)

    val_pos_check_mean = float(np.mean(X_val_14[pos_mask_val, 10])) * 100
    val_neg_check_mean = float(np.mean(X_val_14[neg_mask_val, 10])) * 100
    val_pos_legal_mean = float(np.mean(X_val_14[pos_mask_val, 11]))
    val_neg_legal_mean = float(np.mean(X_val_14[neg_mask_val, 11]))
    val_pos_cap_mean = float(np.mean(X_val_14[pos_mask_val, 12])) * 100
    val_neg_cap_mean = float(np.mean(X_val_14[neg_mask_val, 12])) * 100

    val_pos_total_pcs_mean = float(np.mean(X_val_a5[pos_mask_val, 0]))
    val_neg_total_pcs_mean = float(np.mean(X_val_a5[neg_mask_val, 0]))
    val_pos_pawns_mean = float(np.mean(X_val_a5[pos_mask_val, 1]))
    val_neg_pawns_mean = float(np.mean(X_val_a5[neg_mask_val, 1]))
    val_pos_castling_mean = float(np.mean(X_val_a5[pos_mask_val, 2]))
    val_neg_castling_mean = float(np.mean(X_val_a5[neg_mask_val, 2]))

    t_alarms = time.time() - t0_alarms

    # Write STATS.md
    stats_md_content = f"""# Opening Configuration Steering Dataset — STATS.md

**Build Date:** {manifest_data["build_timestamp"]}
**Seed:** {seed}
**Match Rate:** {match_rate * 100:.2f}% ({len(matched_positives)} / {len(positives)})
**Achieved Sharp Share (before match):** {achieved_sharp_share * 100:.2f}% ({sharp_positives_kept} / {total_positives_kept})
**Achieved Sharp Share (after match):** {overall_counts["sharp_positives"] / overall_counts["positives"] * 100:.2f}% ({overall_counts["sharp_positives"]} / {overall_counts["positives"]})

---

## 1. Summary Counts

| Split | Positives (s_err) | Sharp Positives | Negatives (Total) | N1 (n1_spent) | N2 (n2_quiet) | Total Rows |
|---|---|---|---|---|---|---|
| **train** | {manifest_counts["train"]["positives"]} | {manifest_counts["train"]["sharp_positives"]} | {manifest_counts["train"]["negatives"]} | {manifest_counts["train"]["sources"]["n1_spent"]} | {manifest_counts["train"]["sources"]["n2_quiet"]} | {manifest_counts["train"]["total"]} |
| **val** | {manifest_counts["val"]["positives"]} | {manifest_counts["val"]["sharp_positives"]} | {manifest_counts["val"]["negatives"]} | {manifest_counts["val"]["sources"]["n1_spent"]} | {manifest_counts["val"]["sources"]["n2_quiet"]} | {manifest_counts["val"]["total"]} |
| **test** | {manifest_counts["test"]["positives"]} | {manifest_counts["test"]["sharp_positives"]} | {manifest_counts["test"]["negatives"]} | {manifest_counts["test"]["sources"]["n1_spent"]} | {manifest_counts["test"]["sources"]["n2_quiet"]} | {manifest_counts["test"]["total"]} |
| **TOTAL** | {overall_counts["positives"]} | {overall_counts["sharp_positives"]} | {overall_counts["negatives"]} | {overall_counts["sources"]["n1_spent"]} | {overall_counts["sources"]["n2_quiet"]} | {overall_counts["total"]} |

---

## 2. Tactical & Phase Balance Table

Comparison on the held-out validation split:

| Feature | Positives (s_err) | Negatives (Matched) | Delta | Notes |
|---|---|---|---|---|
| **In check** | {val_pos_check_mean:.2f}% | {val_neg_check_mean:.2f}% | {abs(val_pos_check_mean - val_neg_check_mean):.2f}% | Matched exactly |
| **Mean legal moves** | {val_pos_legal_mean:.2f} | {val_neg_legal_mean:.2f} | {abs(val_pos_legal_mean - val_neg_legal_mean):.2f} | Mobility bucket matched |
| **Capture available** | {val_pos_cap_mean:.2f}% | {val_neg_cap_mean:.2f}% | {abs(val_pos_cap_mean - val_neg_cap_mean):.2f}% | Tactical balance |
| **Total piece count** | {val_pos_total_pcs_mean:.2f} | {val_neg_total_pcs_mean:.2f} | {abs(val_pos_total_pcs_mean - val_neg_total_pcs_mean):.2f} | Opening phase check |
| **Pawn count** | {val_pos_pawns_mean:.2f} | {val_neg_pawns_mean:.2f} | {abs(val_pos_pawns_mean - val_neg_pawns_mean):.2f} | Opening pawn structure |
| **Castling rights count** | {val_pos_castling_mean:.2f} | {val_neg_castling_mean:.2f} | {abs(val_pos_castling_mean - val_neg_castling_mean):.2f} | Development status |

---

## 3. The Five Alarms (A1–A5)

| Alarm | Measurement | Target / Threshold | Status |
|---|---|---|---|
| **A1 Side-to-move balance** | Positives: {pos_w_ratio * 100:.2f}% WTM<br>Negatives: {neg_w_ratio * 100:.2f}% WTM | 50 ± 2% in both classes | **{"PASS" if a1_pass else "FAIL"}** |
| **A2 Material key overlap** | Top 10 overlap: {overlap_count}/10 shared | ≥ 8/10 shared | **{"PASS" if a2_pass else "FAIL"}** |
| **A3 Material-only AUC** | 10 piece counts: **AUC = {a3_auc:.4f}** | **AUC < 0.65** | **{"PASS" if a3_pass else "FAIL"}** |
| **A4 Cheap-tactical + material AUC** | 14 features: **AUC = {a4_auc_overall:.4f}**<br>• N1-only: {a4_auc_n1:.4f}<br>• N2-only: {a4_auc_n2:.4f} | **AUC < 0.60** | **{"PASS" if a4_pass else "FAIL"}** |
| **A5 Phase-only AUC** | 5 development features: **AUC = {a5_auc:.4f}** | **AUC < 0.60** | **{"PASS" if a5_pass else "FAIL"}** |

---

## 4. Single-Feature AUCs (Validation Split)

| Feature | Single-Feature ROC AUC | Notes |
|---|---|---|
| `in_check` | {auc_in_check:.4f} | Exactly matched |
| `n_legal_moves` | {auc_n_legal:.4f} | Mobility bucket matched |
| `capture_available` | {auc_cap_avail:.4f} | Informative / balanced |
| `n_checks_available` | {auc_n_checks:.4f} | Tactical check threat |
| `total_pieces` | {auc_total_pieces:.4f} | Phase feature (A5) |
| `pawn_count` | {auc_pawn_count:.4f} | Phase feature (A5) |
| `castling_count` | {auc_castling_count:.4f} | Phase feature (A5) |

---

## 5. A2 Material Key Comparison (Top 10)

| Rank | Positives (s_err) | Count | Negatives (Matched) | Count |
|---|---|---|---|---|
"""
    for rank in range(10):
        pos_k, pos_c = pos_top10[rank] if rank < len(pos_top10) else ("-", 0)
        neg_k, neg_c = neg_top10[rank] if rank < len(neg_top10) else ("-", 0)
        stats_md_content += f"| {rank + 1} | `{pos_k}` | {pos_c} | `{neg_k}` | {neg_c} |\n"

    stats_md_content += f"""
---

## 6. Top 15 Opening Families in Dataset

| Rank | Opening Family | Count in Positives | Share of Positives |
|---|---|---|---|
"""
    for rank, (fam, cnt) in enumerate(top15_families):
        stats_md_content += f"| {rank + 1} | `{fam}` | {cnt} | {cnt / total_positives_kept * 100:.2f}% |\n"

    stats_md_content += f"""
---

## 7. Top 20 Motif Themes (Vocabulary)

{", ".join(f"`{t}`" for t in top20_themes)}
"""

    with open(output_dir / "STATS.md", "w", encoding="utf-8") as f:
        f.write(stats_md_content)

    # Also write STATS.md to zip archive
    with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(output_dir / "STATS.md", arcname="STATS.md")

    print(f"Alarm A1 (Side balance): Positives={pos_w_ratio:.4f}, Negatives={neg_w_ratio:.4f} -> {'PASS' if a1_pass else 'FAIL'}")
    print(f"Alarm A2 (Material overlap): {overlap_count}/10 in top 10 -> {'PASS' if a2_pass else 'FAIL'}")
    print(f"Alarm A3 (Material-only AUC): {a3_auc:.4f} (threshold < 0.65) -> {'PASS' if a3_pass else 'FAIL'}")
    print(f"Alarm A4 (14-feature AUC): {a4_auc_overall:.4f} (threshold < 0.60) -> {'PASS' if a4_pass else 'FAIL'}")
    print(f"Alarm A5 (Phase-only AUC): {a5_auc:.4f} (threshold < 0.60) -> {'PASS' if a5_pass else 'FAIL'}")

    if not a4_pass:
        raise RuntimeError(
            f"Alarm A4 FIRED: 14-feature AUC {a4_auc_overall:.4f} >= 0.60 threshold! Stop and report."
        )

    if not a5_pass:
        raise RuntimeError(
            f"Alarm A5 FIRED: phase-only AUC {a5_auc:.4f} >= 0.60 threshold! Negatives are separable on development phase. Stop and report."
        )

    wall_clock_total = time.time() - start_time_all
    print("=" * 70)
    print(f"OPENING DATASET BUILD COMPLETED in {wall_clock_total:.2f}s")
    print(f"Archive written to {zip_path}")
    print("=" * 70)

    return {
        "wall_clock": {
            "step2_positives": t_pos,
            "step3_n1": t_n1,
            "step3_n2": t_n2,
            "step4_match": t_match,
            "step5_split": t_split,
            "step6_alarms": t_alarms,
            "total": wall_clock_total,
        },
        "target_positives": target_positives,
        "positives_kept": total_positives_kept,
        "sharp_positives_kept": sharp_positives_kept,
        "achieved_sharp_share": achieved_sharp_share,
        "top15_families": top15_families,
        "distinct_families": len(pos_family_counts),
        "n1_size": len(n1_negatives),
        "n2_size": len(n2_negatives),
        "match_rate": match_rate,
        "matched_positives": len(matched_positives),
        "matched_negatives": len(matched_negatives),
        "matched_n1_count": matched_n1_count,
        "matched_n2_count": matched_n2_count,
        "manifest": manifest_data,
        "alarms": {
            "a1_pos_w": pos_w_ratio,
            "a1_neg_w": neg_w_ratio,
            "a1_pass": a1_pass,
            "a2_overlap": overlap_count,
            "a2_pass": a2_pass,
            "a3_auc": a3_auc,
            "a3_pass": a3_pass,
            "a4_auc_overall": a4_auc_overall,
            "a4_auc_n1": a4_auc_n1,
            "a4_auc_n2": a4_auc_n2,
            "a4_pass": a4_pass,
            "a5_auc": a5_auc,
            "a5_pass": a5_pass,
            "single_features": {
                "in_check": auc_in_check,
                "n_legal_moves": auc_n_legal,
                "capture_available": auc_cap_avail,
                "n_checks_available": auc_n_checks,
                "total_pieces": auc_total_pieces,
                "pawn_count": auc_pawn_count,
                "castling_count": auc_castling_count,
            },
        },
        "stats_md": stats_md_content,
        "zip_path": str(zip_path),
    }


if __name__ == "__main__":
    build_opening_dataset()
