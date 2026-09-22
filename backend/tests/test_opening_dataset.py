"""Tests for opening dataset builder pure functions, family parsing, and alarms."""

import chess
import numpy as np
import pytest

from backend.training.config_steering.build_opening_dataset import (
    parse_opening_family,
    is_sharp_opening,
    compute_a5_features,
)


def test_parse_opening_family_accepted_declined_preserved():
    """Verify that family key is truncated at second underscore while preserving Accepted / Declined tokens."""
    # Italian Game Evans Gambit Declined -> Italian_Game_Declined
    assert parse_opening_family("Italian_Game Italian_Game_Evans_Gambit_Declined") == "Italian_Game_Declined"
    assert parse_opening_family("Italian_Game_Evans_Gambit_Declined") == "Italian_Game_Declined"

    # Danish Gambit Accepted -> Danish_Gambit_Accepted
    assert parse_opening_family("Danish_Gambit_Accepted_Classical_Defense") == "Danish_Gambit_Accepted"

    # Queen's Gambit Declined
    assert parse_opening_family("Queens_Gambit_Declined_Modern_Variation") == "Queens_Gambit_Declined"

    # Regular opening without Accepted/Declined -> truncated at 2nd underscore
    assert parse_opening_family("Sicilian_Defense Sicilian_Defense_Bowdler_Attack") == "Sicilian_Defense"
    assert parse_opening_family("Caro-Kann_Defense Caro-Kann_Defense_Classical_Variation") == "Caro-Kann_Defense"
    assert parse_opening_family("French_Defense French_Defense_Winawer_Variation") == "French_Defense"

    # Edge cases
    assert parse_opening_family("") == "Unknown"
    assert parse_opening_family(None) == "Unknown"


def test_is_sharp_opening():
    """Verify that sacrifice or kingsideAttack themes flag sharp positions."""
    assert is_sharp_opening("advantage sacrifice master opening") is True
    assert is_sharp_opening("kingsideAttack opening short") is True
    assert is_sharp_opening("crushing sacrifice kingsideAttack opening") is True
    assert is_sharp_opening("crushing fork opening") is False
    assert is_sharp_opening("advantage endgame short") is False
    assert is_sharp_opening("") is False


def test_compute_a5_features_starting_position():
    """Verify the 5 features extracted for Alarm A5 on standard starting position."""
    board = chess.Board()
    features = compute_a5_features(board)
    assert len(features) == 5
    total_pieces, pawn_count, castling_count, in_check, n_legal_moves = features

    assert total_pieces == 32.0
    assert pawn_count == 16.0
    assert castling_count == 4.0
    assert in_check == 0.0
    assert n_legal_moves == 20.0


def test_compute_a5_features_tactical_position():
    """Verify A5 features on an open / check position."""
    fen = "r1bqkb1r/pppp1Qpp/2n5/4p3/2B1n3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 5"  # Scholar's mate
    board = chess.Board(fen)
    total_pieces, pawn_count, castling_count, in_check, n_legal_moves = compute_a5_features(board)

    assert in_check == 1.0
    assert n_legal_moves == 0.0
    assert total_pieces == 30.0  # 1 pawn captured, 1 knight moved
    assert castling_count == 4.0  # KQkq in FEN string
