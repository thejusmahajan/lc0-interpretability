"""
Acceptance and mutation tests for positional fact detectors (Batch 1: pawn weaknesses, tied defenders, outposts).
"""

import chess
from backend.training.relational_facts import (
    pawn_weaknesses,
    tied_defenders,
    outposts,
)


def test_backward_pawn_steinitz_sellman_positive():
    """
    1. Positive: Steinitz-Sellman game position after 14... f7f5.
    e6 pawn must be identified as backward.
    Fails if direction of advance or adjacent pawn support checking is inverted/incorrect.
    """
    fen = "r1b1k2r/3nbppp/pq2p3/1p1pP3/1P3P2/P2P1N2/3BQ1PP/R2NK2R b KQkq - 0 14"
    board = chess.Board(fen)
    board.push_san("f5")  # Black plays f7f5

    facts = pawn_weaknesses(board, chess.BLACK)
    e6_backward = [
        f for f in facts if f["square"] == "e6" and f["weakness"] == "backward"
    ]
    assert len(e6_backward) == 1, (
        f"Expected e6 to be flagged as backward pawn, got facts: {facts}"
    )


def test_outpost_positive():
    """
    2. Positive: White knight on d5 with no Black pawn able to attack it.
    outposts(board, BLACK) reports the Nd5 knight.
    Fails if outpost detector miscalculates board halves or pawn challenge capabilities.
    """
    fen = "3rk3/pp3ppp/8/3N4/8/8/PPP2PPP/3RK3 b - - 0 1"
    board = chess.Board(fen)

    facts = outposts(board, chess.BLACK)
    d5_outposts = [
        f for f in facts if f["square"] == "d5" and f["enemy_piece"] == "N"
    ]
    assert len(d5_outposts) == 1, (
        f"Expected White Nd5 to be identified as outpost in Black's half, got facts: {facts}"
    )


def test_tied_defender_positive():
    """
    3. Positive: Weak attacked Black pawn (isolated e6) defended by Black Rook on e8.
    tied_defenders(board, BLACK) reports that Re8 is tied to the defence of e6.
    Fails if defender binding or weakness linkage fails.
    """
    # Black pawn on e6 is isolated (no pawns on d/f files) and attacked by White Rook on e1.
    # Defended by Black Rook on e8.
    fen = "4r1k1/8/4p3/8/8/8/4R3/4K3 b - - 0 1"
    board = chess.Board(fen)

    facts = tied_defenders(board, chess.BLACK)
    tied = [
        f for f in facts if f["square"] == "e8" and f["defends"] == "e6"
    ]
    assert len(tied) == 1, (
        f"Expected Re8 to be tied to defense of weak e6 pawn, got facts: {facts}"
    )
    assert tied[0]["piece"] == "R"


def test_no_false_backward_starting_position_negative():
    """
    4. Negative / mutation: starting position must NOT report any backward pawns for White.
    Fails if backward detector lacks adjacent support verification or misidentifies initial structure.
    """
    board = chess.Board()
    facts = pawn_weaknesses(board, chess.WHITE)

    backward_pawns = [f for f in facts if f["weakness"] == "backward"]
    assert len(backward_pawns) == 0, (
        f"Found false backward pawns in starting position: {backward_pawns}"
    )


def test_no_false_outpost_pawn_can_attack_negative():
    """
    5. Negative / mutation: White knight on d5, but Black has a pawn on c6 that CAN advance/attack d5.
    outposts(board, BLACK) must NOT report d5 as an outpost.
    Fails if outpost detector ignores pawns behind the square on adjacent files.
    """
    # Black pawn on c6 (rank index 5 for Black, behind d5 at rank index 4)
    fen = "3rk3/p4ppp/2p5/3N4/8/8/PPP2PPP/3RK3 b - - 0 1"
    board = chess.Board(fen)

    facts = outposts(board, chess.BLACK)
    d5_outposts = [f for f in facts if f["square"] == "d5"]
    assert len(d5_outposts) == 0, (
        f"Found false outpost on d5 when c6 pawn can still challenge it: {d5_outposts}"
    )
