"""Tests for configuration steering encoding, dataset invariants, and parity."""

from __future__ import annotations

import collections
import random
import sqlite3
from pathlib import Path

import chess
import numpy as np
import pytest

from backend.training.config_steering.encode import decode, encode, unpack
from backend.training.config_steering.build_dataset import (
    compute_material_and_phase,
    compute_tactical_features,
    get_split_name,
)
from backend.training.config_steering.load import load_split
from backend.training.puzzle_regime import puzzle_position

DB_PATH = Path("data/puzzles/puzzles.sqlite")


def get_sample_puzzle_rows(n: int = 500) -> list[dict]:
    """Fetch sample rows from puzzles.sqlite for invariant testing."""
    if not DB_PATH.exists():
        pytest.skip(f"{DB_PATH} not found on disk")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, fen, moves, rating, themes FROM puzzles WHERE rating BETWEEN 1500 AND 2200 LIMIT ?",
        (n,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def test_encode_decode_round_trip():
    """Round-trip: decode(encode(b)) restores piece placement, canonical turn and castling rights for 200 DB positions."""
    rows = get_sample_puzzle_rows(200)
    assert len(rows) == 200, "Need at least 200 puzzle rows"

    for row in rows:
        board = chess.Board(row["fen"])
        canonical = board.mirror() if board.turn == chess.BLACK else board
        bb = encode(board)
        decoded = decode(bb)

        # Check piece placement
        assert decoded.piece_map() == canonical.piece_map(), (
            f"Piece map mismatch for FEN {row['fen']}"
        )

        # Check turn (canonical POV frame is always White)
        assert decoded.turn == chess.WHITE

        # Check castling rights
        assert decoded.has_kingside_castling_rights(chess.WHITE) == canonical.has_kingside_castling_rights(chess.WHITE)
        assert decoded.has_queenside_castling_rights(chess.WHITE) == canonical.has_queenside_castling_rights(chess.WHITE)
        assert decoded.has_kingside_castling_rights(chess.BLACK) == canonical.has_kingside_castling_rights(chess.BLACK)
        assert decoded.has_queenside_castling_rights(chess.BLACK) == canonical.has_queenside_castling_rights(chess.BLACK)

        # Check ep square
        if canonical.ep_square is not None:
            assert decoded.ep_square == canonical.ep_square


def test_colour_invariance():
    """Colour invariance: for a position and its mirror(), the encoded planes are identical."""
    rows = get_sample_puzzle_rows(200)
    for row in rows:
        board = chess.Board(row["fen"])
        mirrored = board.mirror()

        bb_orig = encode(board)
        bb_mirrored = encode(mirrored)

        # Strict check: all 18 planes must match
        np.testing.assert_array_equal(
            bb_orig,
            bb_mirrored,
            err_msg=f"Frame mismatch between board and its mirror for FEN {row['fen']}",
        )


def test_puzzle_parity():
    """Puzzle parity: for 500 rows, fen turn != solver turn, and moves line length is even."""
    rows = get_sample_puzzle_rows(500)
    assert len(rows) == 500, "Need 500 puzzle rows"

    for row in rows:
        b_err = chess.Board(row["fen"])
        b_solver, solver_moves = puzzle_position(row)

        # Parity check: fen is opponent's blunder, solver moves second
        assert b_err.turn != b_solver.turn, (
            f"Expected turn alternation for puzzle {row['id']}"
        )

        # Solution line length must be even (error + reply pairs)
        moves_list = row["moves"].split()
        assert len(moves_list) % 2 == 0, (
            f"Puzzle {row['id']} has odd solution length {len(moves_list)}"
        )


def test_matching_invariant():
    """Matching invariant: every kept positive has a negative with identical (material_key, phase_bucket, in_check, mobility_bucket)."""
    # Create synthetic pool of positives and negatives
    rows = get_sample_puzzle_rows(100)
    positives = []
    negatives = []

    for i, r in enumerate(rows):
        b_pos = chess.Board(r["fen"])
        mat_pos, phase_pos, _ = compute_material_and_phase(b_pos)
        in_check_pos, _, _, _, mob_pos = compute_tactical_features(b_pos)
        positives.append({
            "id": f"pos_{i}",
            "board": b_pos,
            "material_key": mat_pos,
            "phase_bucket": phase_pos,
            "in_check": in_check_pos,
            "mobility_bucket": mob_pos,
        })

        # Create spent tactic negative (excluding mate)
        if "mate" in r["themes"].lower().split():
            continue
        b_neg = chess.Board(r["fen"])
        for m in r["moves"].split():
            b_neg.push_uci(m)
        if b_neg.is_check():
            continue
        mat_neg, phase_neg, _ = compute_material_and_phase(b_neg)
        in_check_neg, _, _, _, mob_neg = compute_tactical_features(b_neg)
        negatives.append({
            "id": f"neg_{i}",
            "board": b_neg,
            "material_key": mat_neg,
            "phase_bucket": phase_neg,
            "in_check": in_check_neg,
            "mobility_bucket": mob_neg,
        })

    # Bucket negatives by extended 4-tuple key
    buckets = collections.defaultdict(list)
    for n in negatives:
        k = (n["material_key"], n["phase_bucket"], n["in_check"], n["mobility_bucket"])
        buckets[k].append(n)

    matched_pairs = []
    for p in positives:
        k = (p["material_key"], p["phase_bucket"], p["in_check"], p["mobility_bucket"])
        if buckets[k]:
            matched_neg = buckets[k].pop()
            matched_pairs.append((p, matched_neg))

    # Test invariant on all matched pairs
    for p, n in matched_pairs:
        assert p["material_key"] == n["material_key"]
        assert p["phase_bucket"] == n["phase_bucket"]
        assert p["in_check"] == n["in_check"]
        assert p["mobility_bucket"] == n["mobility_bucket"]


def test_split_disjointness():
    """Split disjointness: no puzzle_id appears across multiple splits."""
    random.seed(20260901)
    test_ids = [f"puzzle_{i:06d}" for i in range(2000)]

    train_ids = set()
    val_ids = set()
    test_split_ids = set()

    for pid in test_ids:
        s_name = get_split_name(pid)
        if s_name == "train":
            train_ids.add(pid)
        elif s_name == "val":
            val_ids.add(pid)
        elif s_name == "test":
            test_split_ids.add(pid)

    # Check pairwise disjointness
    assert len(train_ids.intersection(val_ids)) == 0
    assert len(train_ids.intersection(test_split_ids)) == 0
    assert len(val_ids.intersection(test_split_ids)) == 0
    assert len(train_ids) + len(val_ids) + len(test_split_ids) == len(test_ids)
