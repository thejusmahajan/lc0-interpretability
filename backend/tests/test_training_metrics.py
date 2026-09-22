"""Castling UCI normalization: LC0 policy uses king-takes-rook ("e1h1"),
python-chess and chessground's standard frame use "e1g1". These tests pin the
regression found in the G3 gate output, where a played O-O was scored as a
false "blind" finding against a best move that was also O-O."""

import chess

from backend.training import metrics

# Position from the G3 gate output where the false positive occurred.
G3_FEN = "r1b2rk1/1p1n1ppp/p3p3/q2pP3/N2Q1P2/P1P5/1P2B1PP/R3K2R w KQ - 1 15"


def test_policy_uci_castling_kingside():
    board = chess.Board(G3_FEN)
    move = board.parse_san("O-O")
    assert move.uci() == "e1g1"
    assert metrics.policy_uci(board, move) == "e1h1"


def test_policy_uci_castling_queenside_black():
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R b kq - 0 1")
    move = board.parse_san("O-O-O")
    assert metrics.policy_uci(board, move) == "e8a8"


def test_policy_uci_noop_for_normal_moves():
    board = chess.Board()
    move = board.parse_san("e4")
    assert metrics.policy_uci(board, move) == "e2e4"


def test_accepted_ucis_castling_has_both_spellings():
    board = chess.Board(G3_FEN)
    assert metrics.accepted_ucis(board, "e1h1") == ["e1g1", "e1h1"]
    assert metrics.accepted_ucis(board, "e1g1") == ["e1g1", "e1h1"]


def test_accepted_ucis_normal_move_single():
    board = chess.Board()
    assert metrics.accepted_ucis(board, "e2e4") == ["e2e4"]


def test_accepted_ucis_illegal_passthrough():
    board = chess.Board()
    assert metrics.accepted_ucis(board, "a1a2") == ["a1a2"]


def test_divergence_no_false_positive_when_castling_played():
    """Played O-O must match a best move of e1h1 once normalized."""
    board = chess.Board(G3_FEN)
    played = board.parse_san("O-O")
    policy = [
        {"uci": "e1h1", "san": "O-O", "p": 0.339},
        {"uci": "d4d2", "san": "Qd2", "p": 0.20},
    ]
    div = metrics.policy_divergence(policy, metrics.policy_uci(board, played))
    assert div["severity"] is None
    assert div["p_played"] == 0.339
    assert div["divergence"] == 0.0
