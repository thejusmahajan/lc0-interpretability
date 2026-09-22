"""Dataset builder for configuration steering (Rebuild 2026-09-02).

Builds the training dataset for configuration steering:
  - Positive class (s_err): 200,000 unmodified puzzle FENs (rating 1500..2200)
  - Negative pool N1 (n1_spent): spent tactic positions, excluding:
      * post-solution positions in check (board.is_check())
      * puzzles whose themes contain 'mate'
  - Negative pool N2 (n2_quiet): real quiet play positions from lichess_derdiedasdie_2026-07-21.pgn
      * sampled at every 3rd ply (plies 9 to T-10, step 3)
  - Matching:
      * Extended key: (material_key, phase_bucket, in_check, mobility_bucket)
      * mobility_bucket = len(list(board.legal_moves)) // 6
      * Exact bucket matching without replacement, partitioned by turn (WTM/BTM)
      * Priority: N2 over N1. Unmatched positives dropped, never back-filled.
  - Alarms:
      A1: side-to-move balance (50 +- 2% in both classes)
      A2: material_key overlap (positives vs negatives top-10)
      A3: 10-feature material-only Logistic Regression AUC on val (< 0.65)
      A4: 14-feature cheap-tactical + material Logistic Regression AUC on val (< 0.60)
  - Exports:
      train.npz, val.npz, test.npz (with arrays: bb, y, motif, source), manifest.json, STATS.md
"""

from __future__ import annotations

import collections
import datetime
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import time
from typing import Any

import chess
import chess.pgn
import numpy as np

from backend.training.config_steering.encode import encode

DEFAULT_DB_PATH = Path("data/puzzles/puzzles.sqlite")
DEFAULT_PGN_PATH = Path("games_of_derdiedasdie/lichess_derdiedasdie_2026-07-21.pgn")
DEFAULT_OUTPUT_DIR = Path("data/training/config_steering")

RANDOM_SEED = 20260901


def compute_material_and_phase(
    board: chess.Board,
) -> tuple[str, int, tuple[int, int, int, int, int, int, int, int, int, int]]:
    """Compute material key (side-to-move first), phase bucket, and raw 10 piece counts.

    material_key = f"{P}-{N}-{B}-{R}-{Q}|{p}-{n}-{b}-{r}-{q}"
    phase_bucket = (number of non-king pieces on the board) // 4
    piece_counts = (P, N, B, R, Q, p, n, b, r, q)
    """
    if board.turn == chess.WHITE:
        our_color = chess.WHITE
        their_color = chess.BLACK
    else:
        our_color = chess.BLACK
        their_color = chess.WHITE

    P = len(board.pieces(chess.PAWN, our_color))
    N = len(board.pieces(chess.KNIGHT, our_color))
    B = len(board.pieces(chess.BISHOP, our_color))
    R = len(board.pieces(chess.ROOK, our_color))
    Q = len(board.pieces(chess.QUEEN, our_color))

    p = len(board.pieces(chess.PAWN, their_color))
    n = len(board.pieces(chess.KNIGHT, their_color))
    b = len(board.pieces(chess.BISHOP, their_color))
    r = len(board.pieces(chess.ROOK, their_color))
    q = len(board.pieces(chess.QUEEN, their_color))

    material_key = f"{P}-{N}-{B}-{R}-{Q}|{p}-{n}-{b}-{r}-{q}"
    total_non_king = P + N + B + R + Q + p + n + b + r + q
    phase_bucket = total_non_king // 4
    piece_counts = (P, N, B, R, Q, p, n, b, r, q)

    return material_key, phase_bucket, piece_counts


def compute_tactical_features(
    board: chess.Board,
) -> tuple[bool, int, float, int, int]:
    """Compute (in_check, n_legal_moves, capture_available, n_checks_available, mobility_bucket)."""
    in_check = board.is_check()
    legal_moves = list(board.legal_moves)
    n_legal_moves = len(legal_moves)
    capture_available = 1.0 if any(board.is_capture(m) for m in legal_moves) else 0.0
    n_checks_available = sum(1 for m in legal_moves if board.gives_check(m))
    mobility_bucket = n_legal_moves // 6
    return in_check, n_legal_moves, capture_available, n_checks_available, mobility_bucket


def get_split_name(identifier: str) -> str:
    """Deterministic hash split: <80 train, 80-89 val, >=90 test."""
    val = int(hashlib.md5(identifier.encode("utf-8")).hexdigest(), 16) % 100
    if val < 80:
        return "train"
    elif val < 90:
        return "val"
    else:
        return "test"


def compute_roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Exact ROC AUC computation via rank sum (Mann-Whitney U statistic)."""
    y_true = np.asarray(y_true, dtype=bool)
    y_score = np.asarray(y_score, dtype=np.float64)
    n_pos = int(np.sum(y_true))
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = np.argsort(y_score)
    rank = np.empty_like(order, dtype=np.float64)
    rank[order] = np.arange(1, len(y_score) + 1)
    unique_scores, inverse_indices, counts = np.unique(
        y_score, return_inverse=True, return_counts=True
    )
    if len(unique_scores) < len(y_score):
        for idx, count in enumerate(counts):
            if count > 1:
                mask = inverse_indices == idx
                rank[mask] = np.mean(rank[mask])
    pos_ranks_sum = float(np.sum(rank[y_true]))
    auc = (pos_ranks_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def fit_logistic_regression_and_auc(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    seed: int = RANDOM_SEED,
) -> tuple[float, np.ndarray]:
    """Fit logistic regression and return held-out AUC on validation set alongside predicted probabilities."""
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score

        clf = LogisticRegression(max_iter=1000, random_state=seed)
        clf.fit(X_train, y_train)
        val_probs = clf.predict_proba(X_val)[:, 1]
        return float(roc_auc_score(y_val, val_probs)), val_probs
    except ImportError:
        import torch
        import torch.nn as nn
        import torch.optim as optim

        torch.manual_seed(seed)
        # Normalize features with train mean/std to ensure fast L-BFGS convergence
        mean = torch.tensor(np.mean(X_train, axis=0, keepdims=True), dtype=torch.float32)
        std = torch.tensor(np.std(X_train, axis=0, keepdims=True) + 1e-6, dtype=torch.float32)

        X_t = (torch.tensor(X_train, dtype=torch.float32) - mean) / std
        y_t = torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)
        X_v = (torch.tensor(X_val, dtype=torch.float32) - mean) / std

        model = nn.Linear(X_train.shape[1], 1)
        optimizer = optim.LBFGS(
            model.parameters(), lr=1.0, max_iter=200, line_search_fn="strong_wolfe"
        )
        criterion = nn.BCEWithLogitsLoss()

        def closure():
            optimizer.zero_grad()
            pred = model(X_t)
            loss = criterion(pred, y_t)
            l2 = 0.5 * 1e-4 * sum(p.pow(2.0).sum() for p in model.parameters())
            total_loss = loss + l2
            total_loss.backward()
            return total_loss

        optimizer.step(closure)
        with torch.no_grad():
            val_logits = model(X_v).squeeze(1)
            val_probs = torch.sigmoid(val_logits).numpy()

        return compute_roc_auc(y_val, val_probs), val_probs


def build_dataset(
    db_path: Path | str = DEFAULT_DB_PATH,
    pgn_path: Path | str = DEFAULT_PGN_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    target_positives: int = 200000,
    rating_min: int = 1500,
    rating_max: int = 2200,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Build the rebuilt configuration steering dataset and write output files."""
    start_time_all = time.time()
    random.seed(seed)
    np.random.seed(seed)

    db_path = Path(db_path)
    pgn_path = Path(pgn_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # STEP 2: Positive Class (s_err)
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 2: Extracting Positive Class (s_err)...")
    t0 = time.time()
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM puzzles WHERE rating BETWEEN ? AND ?",
        (rating_min, rating_max),
    )
    total_in_rating = cur.fetchone()[0]
    stride = total_in_rating // target_positives
    if stride < 1:
        stride = 1

    print(f"Total puzzles in rating {rating_min}-{rating_max}: {total_in_rating}")
    print(f"Sampling stride n: {stride} (target positives: {target_positives})")

    cur.execute(
        "SELECT id, fen, moves, rating, themes FROM puzzles WHERE rating BETWEEN ? AND ? ORDER BY id",
        (rating_min, rating_max),
    )

    target_per_turn = target_positives // 2
    positives_w: list[dict[str, Any]] = []
    positives_b: list[dict[str, Any]] = []
    positive_ids_set: set[str] = set()
    n1_candidates_rows: list[tuple[str, str, str, int, str]] = []

    row_idx = 0
    while True:
        rows = cur.fetchmany(50000)
        if not rows:
            break
        for pid, fen, moves, rating, themes in rows:
            is_sample_point = (row_idx % stride == 0)
            if is_sample_point:
                board = chess.Board(fen)
                bb = encode(board)
                mat_key, phase_bucket, counts = compute_material_and_phase(board)
                in_check, n_legal, cap_avail, n_checks, mobility_bucket = compute_tactical_features(board)
                features_14 = counts + (float(in_check), float(n_legal), float(cap_avail), float(n_checks))
                is_wtm = (board.turn == chess.WHITE)

                if is_wtm and len(positives_w) < target_per_turn:
                    positives_w.append({
                        "puzzle_id": pid,
                        "bb": bb,
                        "label": 1,
                        "source": 0,  # 0 = s_err
                        "material_key": mat_key,
                        "phase_bucket": phase_bucket,
                        "in_check": in_check,
                        "n_legal_moves": n_legal,
                        "capture_available": cap_avail,
                        "n_checks_available": n_checks,
                        "mobility_bucket": mobility_bucket,
                        "piece_counts": counts,
                        "features_14": features_14,
                        "rating": rating,
                        "themes": themes,
                        "is_white_to_move": True,
                    })
                    positive_ids_set.add(pid)
                elif (not is_wtm) and len(positives_b) < target_per_turn:
                    positives_b.append({
                        "puzzle_id": pid,
                        "bb": bb,
                        "label": 1,
                        "source": 0,  # 0 = s_err
                        "material_key": mat_key,
                        "phase_bucket": phase_bucket,
                        "in_check": in_check,
                        "n_legal_moves": n_legal,
                        "capture_available": cap_avail,
                        "n_checks_available": n_checks,
                        "mobility_bucket": mobility_bucket,
                        "piece_counts": counts,
                        "features_14": features_14,
                        "rating": rating,
                        "themes": themes,
                        "is_white_to_move": False,
                    })
                    positive_ids_set.add(pid)
                elif len(n1_candidates_rows) < 800000:
                    # §2.1: filter out 'mate' theme before queuing
                    if "mate" not in (themes or "").lower().split():
                        n1_candidates_rows.append((pid, fen, moves, rating, themes))
            elif len(n1_candidates_rows) < 800000:
                # §2.1: filter out 'mate' theme before queuing
                if "mate" not in (themes or "").lower().split():
                    n1_candidates_rows.append((pid, fen, moves, rating, themes))
            row_idx += 1

    conn.close()
    positives = positives_w + positives_b
    t_pos = time.time() - t0

    pos_mat_counts = collections.Counter(p["material_key"] for p in positives)
    top5_pos_mat = pos_mat_counts.most_common(5)

    print(f"Rows scanned: {row_idx}")
    print(f"Positives kept: {len(positives)} (WTM: {len(positives_w)}, BTM: {len(positives_b)})")
    print(f"Positive scan wall-clock: {t_pos:.2f}s")
    print(f"Top 5 positive material keys: {top5_pos_mat}")

    # -------------------------------------------------------------------------
    # STEP 3: Negative Pools (N1 spent & N2 quiet)
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 3: Extracting Negative Pools (N1 spent & N2 quiet)...")

    # Pool N1: spent tactic (§2.1 exclusions: drop in_check, drop mate)
    t0_n1 = time.time()
    n1_negatives: list[dict[str, Any]] = []
    n1_dropped_check = 0

    for pid, fen, moves_str, rating, themes in n1_candidates_rows:
        if pid in positive_ids_set:
            continue
        board = chess.Board(fen)
        for m_str in moves_str.split():
            board.push(chess.Move.from_uci(m_str))

        # §2.1: Drop if side to move in post-solution position is in check
        if board.is_check():
            n1_dropped_check += 1
            continue

        bb = encode(board)
        mat_key, phase_bucket, counts = compute_material_and_phase(board)
        in_check, n_legal, cap_avail, n_checks, mobility_bucket = compute_tactical_features(board)
        features_14 = counts + (float(in_check), float(n_legal), float(cap_avail), float(n_checks))
        is_white_to_move = (board.turn == chess.WHITE)

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
            "rating": rating,
            "themes": themes,
            "is_white_to_move": is_white_to_move,
        })
    t_n1 = time.time() - t0_n1
    print(f"Pool N1 (n1_spent) size after exclusions: {len(n1_negatives)} (dropped {n1_dropped_check} in-check post-solution) ({t_n1:.2f}s)")

    # Pool N2: real quiet play (§2.3: every 3rd ply)
    t0_n2 = time.time()
    n2_negatives: list[dict[str, Any]] = []
    total_n2_positions_found = 0

    with open(pgn_path, "r", encoding="utf-8", errors="ignore") as f:
        game_idx = 0
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            moves = list(game.mainline_moves())
            total_plies = len(moves)
            # §2.3: Sample at every 3rd ply, skipping first 8 and last 10 plies
            valid_plies = set(range(9, total_plies - 10 + 1, 3))
            total_n2_positions_found += len(valid_plies)

            if valid_plies:
                board = game.board()
                ply = 0
                for m in moves:
                    board.push(m)
                    ply += 1
                    if ply in valid_plies:
                        bb = encode(board)
                        mat_key, phase_bucket, counts = compute_material_and_phase(board)
                        in_check, n_legal, cap_avail, n_checks, mobility_bucket = compute_tactical_features(board)
                        features_14 = counts + (float(in_check), float(n_legal), float(cap_avail), float(n_checks))
                        is_white_to_move = (board.turn == chess.WHITE)
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
                            "rating": None,
                            "themes": "",
                            "is_white_to_move": is_white_to_move,
                        })
            game_idx += 1
    t_n2 = time.time() - t0_n2
    print(f"Total N2 positions in PGN at step 3: {total_n2_positions_found}")
    print(f"Pool N2 (n2_quiet) size: {len(n2_negatives)} ({t_n2:.2f}s)")

    # -------------------------------------------------------------------------
    # STEP 4: Matching (§2.2: Extended matching key)
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 4: Matching Negatives to Positives under Extended Key...")
    t0_match = time.time()

    # Bucket negatives by extended 4-tuple key: (material_key, phase_bucket, in_check, mobility_bucket)
    # and partitioned by is_white_to_move to preserve side-to-move parity
    n2_buckets: dict[tuple[str, int, bool, int], dict[bool, list[dict[str, Any]]]] = (
        collections.defaultdict(lambda: {True: [], False: []})
    )
    for neg in n2_negatives:
        k = (neg["material_key"], neg["phase_bucket"], neg["in_check"], neg["mobility_bucket"])
        n2_buckets[k][neg["is_white_to_move"]].append(neg)

    n1_buckets: dict[tuple[str, int, bool, int], dict[bool, list[dict[str, Any]]]] = (
        collections.defaultdict(lambda: {True: [], False: []})
    )
    for neg in n1_negatives:
        k = (neg["material_key"], neg["phase_bucket"], neg["in_check"], neg["mobility_bucket"])
        n1_buckets[k][neg["is_white_to_move"]].append(neg)

    # Shuffle buckets deterministically
    for key, subdict in n2_buckets.items():
        for items in subdict.values():
            random.shuffle(items)
    for key, subdict in n1_buckets.items():
        for items in subdict.values():
            random.shuffle(items)

    matched_positives: list[dict[str, Any]] = []
    matched_negatives: list[dict[str, Any]] = []
    matched_n1_count = 0
    matched_n2_count = 0

    # Shuffle positives before matching
    positives_order = list(positives)
    random.shuffle(positives_order)

    for pos in positives_order:
        k = (pos["material_key"], pos["phase_bucket"], pos["in_check"], pos["mobility_bucket"])
        wtm = pos["is_white_to_move"]

        # Priority 1: N2 (quiet play) with same turn
        if n2_buckets[k][wtm]:
            neg = n2_buckets[k][wtm].pop()
            matched_positives.append(pos)
            matched_negatives.append(neg)
            matched_n2_count += 1
        # Priority 2: N1 (spent tactic) with same turn
        elif n1_buckets[k][wtm]:
            neg = n1_buckets[k][wtm].pop()
            matched_positives.append(pos)
            matched_negatives.append(neg)
            matched_n1_count += 1
        else:
            # Positive dropped with no match — never backfilled
            pass

    match_rate = len(matched_positives) / len(positives)
    t_match = time.time() - t0_match

    print(f"Match rate: {match_rate * 100:.2f}% ({len(matched_positives)} / {len(positives)})")
    print(f"Final positive count: {len(matched_positives)}")
    print(f"Final negative count: {len(matched_negatives)}")
    print(f"Matched N2 (quiet): {matched_n2_count}")
    print(f"Matched N1 (spent): {matched_n1_count}")

    if match_rate < 0.60:
        raise RuntimeError(
            f"Match rate {match_rate:.4f} is below 60% threshold! Stop and report."
        )

    # -------------------------------------------------------------------------
    # STEP 5: Split & Write (§2.5: Store source array)
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
    print(f"Top 20 themes: {top20_themes}")

    # Build motif vector helper
    def make_motif(themes_str: str) -> np.ndarray:
        vec = np.zeros(20, dtype=np.uint8)
        if themes_str:
            for t in themes_str.split():
                if t in theme_to_idx:
                    vec[theme_to_idx[t]] = 1
        return vec

    # Assign split, motif vector, and source
    splits_data: dict[str, list[dict[str, Any]]] = {
        "train": [],
        "val": [],
        "test": [],
    }

    # Add positives (source = 0)
    for pos in matched_positives:
        s_name = get_split_name(pos["puzzle_id"])
        pos["motif"] = make_motif(pos["themes"])
        splits_data[s_name].append(pos)

    # Add negatives (source = 1 for N1, 2 for N2)
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
        "sources": {"s_err": 0, "n1_spent": 0, "n2_quiet": 0},
    }

    for s_name in ["train", "val", "test"]:
        recs = splits_data[s_name]
        random.shuffle(recs)
        bb_arr = np.stack([r["bb"] for r in recs]).astype(np.uint64)
        y_arr = np.array([r["label"] for r in recs], dtype=np.uint8)
        motif_arr = np.stack([r["motif"] for r in recs]).astype(np.uint8)
        source_arr = np.array([r["source"] for r in recs], dtype=np.uint8)

        npz_file = output_dir / f"{s_name}.npz"
        np.savez(npz_file, bb=bb_arr, y=y_arr, motif=motif_arr, source=source_arr)

        n_pos = sum(1 for r in recs if r["label"] == 1)
        n_neg = sum(1 for r in recs if r["label"] == 0)
        n_s_err = sum(1 for r in recs if r["source"] == 0)
        n_n1 = sum(1 for r in recs if r["source"] == 1)
        n_n2 = sum(1 for r in recs if r["source"] == 2)

        manifest_counts[s_name] = {
            "total": len(recs),
            "positives": n_pos,
            "negatives": n_neg,
            "sources": {
                "s_err": n_s_err,
                "n1_spent": n_n1,
                "n2_quiet": n_n2,
            },
        }

        overall_counts["total"] += len(recs)
        overall_counts["positives"] += n_pos
        overall_counts["negatives"] += n_neg
        overall_counts["sources"]["s_err"] += n_s_err
        overall_counts["sources"]["n1_spent"] += n_n1
        overall_counts["sources"]["n2_quiet"] += n_n2

    manifest_data = {
        "build_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "seed": seed,
        "sampling_stride": stride,
        "rating_window": [rating_min, rating_max],
        "theme_vocabulary_20": top20_themes,
        "counts": {
            **manifest_counts,
            "overall": overall_counts,
        },
    }

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    t_split = time.time() - t0_split

    # -------------------------------------------------------------------------
    # STEP 6: Alarms A1, A2, A3, and A4
    # -------------------------------------------------------------------------
    print("=" * 70)
    print("STEP 6: Evaluating Alarms (A1, A2, A3, A4)...")
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
    # N1-only subset: positives (source 0) + N1 negatives (source 1)
    mask_n1 = (val_sources == 0) | (val_sources == 1)
    a4_auc_n1 = compute_roc_auc(y_val[mask_n1], val_probs_14[mask_n1])

    # N2-only subset: positives (source 0) + N2 negatives (source 2)
    mask_n2 = (val_sources == 0) | (val_sources == 2)
    a4_auc_n2 = compute_roc_auc(y_val[mask_n2], val_probs_14[mask_n2])

    # Single-feature AUCs on validation split
    # Feature indices in 14: 10=in_check, 11=n_legal_moves, 12=capture_available, 13=n_checks_available
    auc_in_check = compute_roc_auc(y_val, X_val_14[:, 10])
    auc_n_legal = compute_roc_auc(y_val, X_val_14[:, 11])
    auc_cap_avail = compute_roc_auc(y_val, X_val_14[:, 12])
    auc_n_checks = compute_roc_auc(y_val, X_val_14[:, 13])

    # Means comparison on validation split (Check, Legal Moves, Capture Available)
    pos_mask_val = (y_val == 1)
    neg_mask_val = (y_val == 0)

    val_pos_check_mean = float(np.mean(X_val_14[pos_mask_val, 10])) * 100
    val_neg_check_mean = float(np.mean(X_val_14[neg_mask_val, 10])) * 100

    val_pos_legal_mean = float(np.mean(X_val_14[pos_mask_val, 11]))
    val_neg_legal_mean = float(np.mean(X_val_14[neg_mask_val, 11]))

    val_pos_cap_mean = float(np.mean(X_val_14[pos_mask_val, 12])) * 100
    val_neg_cap_mean = float(np.mean(X_val_14[neg_mask_val, 12])) * 100

    t_alarms = time.time() - t0_alarms

    # Write STATS.md
    stats_md_content = f"""# Configuration Steering Dataset Rebuild — STATS.md

**Build Date:** {manifest_data["build_timestamp"]}
**Seed:** {seed}
**Sampling Stride:** {stride} (from {total_in_rating} puzzles in rating window [{rating_min}, {rating_max}])
**Match Rate:** {match_rate * 100:.2f}% ({len(matched_positives)} / {len(positives)})

---

## 1. Summary Counts

| Split | Positives (s_err) | Negatives (Total) | N1 (n1_spent) | N2 (n2_quiet) | Total Rows |
|---|---|---|---|---|---|
| **train** | {manifest_counts["train"]["positives"]} | {manifest_counts["train"]["negatives"]} | {manifest_counts["train"]["sources"]["n1_spent"]} | {manifest_counts["train"]["sources"]["n2_quiet"]} | {manifest_counts["train"]["total"]} |
| **val** | {manifest_counts["val"]["positives"]} | {manifest_counts["val"]["negatives"]} | {manifest_counts["val"]["sources"]["n1_spent"]} | {manifest_counts["val"]["sources"]["n2_quiet"]} | {manifest_counts["val"]["total"]} |
| **test** | {manifest_counts["test"]["positives"]} | {manifest_counts["test"]["negatives"]} | {manifest_counts["test"]["sources"]["n1_spent"]} | {manifest_counts["test"]["sources"]["n2_quiet"]} | {manifest_counts["test"]["total"]} |
| **TOTAL** | {overall_counts["positives"]} | {overall_counts["negatives"]} | {overall_counts["sources"]["n1_spent"]} | {overall_counts["sources"]["n2_quiet"]} | {overall_counts["total"]} |

---

## 2. Tactical Balance Table (Audit Checkpoint 5)

Comparison of tactical leak features on the held-out validation set:

| Feature | Positives (s_err) | Negatives (Matched) | Delta | Audit Baseline (Old Build) |
|---|---|---|---|---|
| **In check** | {val_pos_check_mean:.2f}% | {val_neg_check_mean:.2f}% | {abs(val_pos_check_mean - val_neg_check_mean):.2f}% | Pos: 11.2% vs Neg: 36.7% |
| **Mean legal moves** | {val_pos_legal_mean:.2f} | {val_neg_legal_mean:.2f} | {abs(val_pos_legal_mean - val_neg_legal_mean):.2f} | Pos: 28.3 vs Neg: 19.4 |
| **Capture available** | {val_pos_cap_mean:.2f}% | {val_neg_cap_mean:.2f}% | {abs(val_pos_cap_mean - val_neg_cap_mean):.2f}% | Pos: 77.9% vs Neg: 51.6% |

---

## 3. The Four Alarms

| Alarm | Measurement | Target / Threshold | Status |
|---|---|---|---|
| **A1 Side-to-move balance** | Positives: {pos_w_ratio * 100:.2f}% WTM<br>Negatives: {neg_w_ratio * 100:.2f}% WTM | 50 ± 2% in both classes | **{"PASS" if a1_pass else "FAIL"}** |
| **A2 Material key overlap** | Top 10 overlap: {overlap_count}/10 shared | Substantial overlap | **{"PASS" if a2_pass else "FAIL"}** |
| **A3 Material-only AUC** | 10 piece counts: **AUC = {a3_auc:.4f}** | **AUC < 0.65** | **{"PASS" if a3_pass else "FAIL"}** |
| **A4 Cheap-tactical + material AUC** | 14 features: **AUC = {a4_auc_overall:.4f}**<br>• N1-only: {a4_auc_n1:.4f}<br>• N2-only: {a4_auc_n2:.4f} | **AUC < 0.60** | **{"PASS" if a4_pass else "FAIL"}** |

---

## 4. Single-Feature AUCs (Validation Split)

| Feature | Single-Feature ROC AUC | Notes |
|---|---|---|
| `in_check` | {auc_in_check:.4f} | Exactly matched |
| `n_legal_moves` | {auc_n_legal:.4f} | Mobility bucket matched |
| `capture_available` | {auc_cap_avail:.4f} | Informative / balanced |
| `n_checks_available` | {auc_n_checks:.4f} | Tactical check threat |

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

## 6. Top 20 Motif Themes (Vocabulary)

{", ".join(f"`{t}`" for t in top20_themes)}
"""

    with open(output_dir / "STATS.md", "w", encoding="utf-8") as f:
        f.write(stats_md_content)

    print(f"Alarm A1 (Side balance): Positives={pos_w_ratio:.4f}, Negatives={neg_w_ratio:.4f} -> {'PASS' if a1_pass else 'FAIL'}")
    print(f"Alarm A2 (Material overlap): {overlap_count}/10 in top 10 -> {'PASS' if a2_pass else 'FAIL'}")
    print(f"Alarm A3 (Material-only AUC): {a3_auc:.4f} (threshold < 0.65) -> {'PASS' if a3_pass else 'FAIL'}")
    print(f"Alarm A4 (14-feature AUC): {a4_auc_overall:.4f} (N1-only: {a4_auc_n1:.4f}, N2-only: {a4_auc_n2:.4f}) (threshold < 0.60) -> {'PASS' if a4_pass else 'FAIL'}")

    if not a4_pass:
        raise RuntimeError(
            f"Alarm A4 FIRED: 14-feature AUC {a4_auc_overall:.4f} >= 0.60 threshold! Stop and report."
        )

    wall_clock_total = time.time() - start_time_all
    print("=" * 70)
    print(f"BUILD COMPLETED in {wall_clock_total:.2f}s")
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
        "stride": stride,
        "rows_scanned": row_idx,
        "target_positives": target_positives,
        "positives_kept": len(positives),
        "top5_pos_material": top5_pos_mat,
        "n1_size": len(n1_negatives),
        "n2_size": len(n2_negatives),
        "total_n2_found": total_n2_positions_found,
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
            "single_features": {
                "in_check": auc_in_check,
                "n_legal_moves": auc_n_legal,
                "capture_available": auc_cap_avail,
                "n_checks_available": auc_n_checks,
            },
        },
        "tactical_means": {
            "val_pos_check": val_pos_check_mean,
            "val_neg_check": val_neg_check_mean,
            "val_pos_legal": val_pos_legal_mean,
            "val_neg_legal": val_neg_legal_mean,
            "val_pos_cap": val_pos_cap_mean,
            "val_neg_cap": val_neg_cap_mean,
        },
        "stats_md": stats_md_content,
    }


if __name__ == "__main__":
    build_dataset()
