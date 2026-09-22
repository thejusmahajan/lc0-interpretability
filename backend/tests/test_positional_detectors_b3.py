"""
Acceptance and mutation tests for positional fact detectors (Batch 3: colour-complex weakness).
"""

import chess
from backend.training.relational_facts import color_complex_weakness


def test_steinitz_weak_dark_squares_positive():
    """
    1. Positive: Steinitz position b2r4/2qn1k2/p3p1p1/1p1pPp1p/1P3P2/P2P1N2/5BPP/2R3K1 w - - 0 32.
    Black has only a light-squared bishop on a8; the dark-squared bishop is gone.
    color_complex_weakness(board, BLACK) must report a dark color-complex weakness (8 dark holes in camp).
    Fails if hard gate or hole counting fails to identify Black's dark-square weakness.
    """
    fen = "b2r4/2qn1k2/p3p1p1/1p1pPp1p/1P3P2/P2P1N2/5BPP/2R3K1 w - - 0 32"
    board = chess.Board(fen)

    facts = color_complex_weakness(board, chess.BLACK)
    dark_complexes = [
        f for f in facts if f["complex_color"] == "dark" and f["bishop_gone"]
    ]
    assert len(dark_complexes) == 1, (
        f"Expected Black to be flagged with weak dark-square complex, got facts: {facts}"
    )
    assert len(dark_complexes[0]["holes"]) == 8
    assert "a5" in dark_complexes[0]["holes"]
    assert "e5" in dark_complexes[0]["holes"]


def test_no_complex_starting_position_negative():
    """
    2. Negative / mutation: Starting position.
    Both White and Black have both bishops present; hard gate MUST block any complex facts.
    Fails if hard gate fails to check presence of friendly defending bishop.
    """
    board = chess.Board()
    white_facts = color_complex_weakness(board, chess.WHITE)
    black_facts = color_complex_weakness(board, chess.BLACK)

    assert len(white_facts) == 0, f"False complex reported for White in start position: {white_facts}"
    assert len(black_facts) == 0, f"False complex reported for Black in start position: {black_facts}"


def test_no_complex_both_bishops_middlegame_negative():
    """
    3. Negative / mutation: Both-bishops Italian Game middlegame.
    r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7.
    Both sides retain both bishops; hard gate MUST block any complex facts.
    Fails if hard gate allows complexes when defending bishop is still on board.
    """
    fen = "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7"
    board = chess.Board(fen)

    white_facts = color_complex_weakness(board, chess.WHITE)
    black_facts = color_complex_weakness(board, chess.BLACK)

    assert len(white_facts) == 0, f"False complex reported for White in middlegame: {white_facts}"
    assert len(black_facts) == 0, f"False complex reported for Black in middlegame: {black_facts}"


def test_no_complex_bishop_gone_but_pawns_intact_negative():
    """
    4. Negative / mutation: Black dark bishop is gone, but Black's rank-7 pawn shield is untouched.
    Holes count in camp is 0 (< 3 threshold), so NO color_complex fact must be emitted.
    Fails if hole threshold ignores pawn coverage on adjacent files behind camp squares.
    """
    # Black lacks dark bishop (only c8 bishop is absent or light bishop present)
    fen = "r1b1k2r/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
    board = chess.Board(fen)

    facts = color_complex_weakness(board, chess.BLACK)
    assert len(facts) == 0, (
        f"False complex reported for Black when pawn shield is intact: {facts}"
    )
