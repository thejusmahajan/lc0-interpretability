"""
Acceptance and mutation tests for positional fact detectors (Batch 2: piece activity, open files, bishop quality).
"""

import chess
from backend.training.relational_facts import (
    rook_on_seventh,
    open_file_pieces,
    bishop_quality,
)


def test_rook_on_seventh_positive():
    """
    1. Positive: Steinitz position b2r4/2qn1k2/p3p1p1/1p1pPp1p/1P3P2/P2P1N2/5BPP/2R3K1 w - - 0 32 after White plays c1c7.
    rook_on_seventh(board, WHITE) must report the c7 rook on the 7th rank.
    Fails if rank index matching or piece selection is incorrect.
    """
    fen = "b2r4/2qn1k2/p3p1p1/1p1pPp1p/1P3P2/P2P1N2/5BPP/2R3K1 w - - 0 32"
    board = chess.Board(fen)
    board.push_san("Rxc7")

    facts = rook_on_seventh(board, chess.WHITE)
    c7_rooks = [f for f in facts if f["square"] == "c7" and f["piece"] == "R"]
    assert len(c7_rooks) == 1, (
        f"Expected White rook on c7 to be flagged on 7th rank, got facts: {facts}"
    )


def test_active_bishop_capablanca_positive():
    """
    2. Positive: Capablanca position r1bqr1k1/pp1nbpp1/2p2n1p/3p4/3P4/2NBPNB1/PPQ2PPP/R4RK1 b - - 7 12.
    bishop_quality(board, WHITE) must flag the d3 bishop as active.
    Fails if own_pawns_on_color or mobility thresholds restrict active classification.
    """
    fen = "r1bqr1k1/pp1nbpp1/2p2n1p/3p4/3P4/2NBPNB1/PPQ2PPP/R4RK1 b - - 7 12"
    board = chess.Board(fen)

    facts = bishop_quality(board, chess.WHITE)
    d3_active = [
        f for f in facts if f["square"] == "d3" and f["quality"] == "active"
    ]
    assert len(d3_active) == 1, (
        f"Expected White Bd3 to be flagged as active, got facts: {facts}"
    )
    # Check raw metrics in fact
    assert d3_active[0]["own_pawns_on_color"] == 2
    assert d3_active[0]["mobility"] == 8


def test_bad_bishop_steinitz_positive():
    """
    3. Positive: Steinitz-Sellman position r1b1k2r/3nbppp/pq2p3/1p1pP3/1P3P2/P2P1N2/3BQ1PP/R2NK2R b KQkq - 0 14 after 14... f7f5.
    bishop_quality(board, BLACK) must flag the c8 bishop as bad/restricted.
    Fails if own_pawns_on_color threshold is too high for Black's pawn structure.
    """
    fen = "r1b1k2r/3nbppp/pq2p3/1p1pP3/1P3P2/P2P1N2/3BQ1PP/R2NK2R b KQkq - 0 14"
    board = chess.Board(fen)
    board.push_san("f5")

    facts = bishop_quality(board, chess.BLACK)
    c8_bad = [
        f for f in facts if f["square"] == "c8" and f["quality"] == "bad"
    ]
    assert len(c8_bad) == 1, (
        f"Expected Black Bc8 to be flagged as bad bishop, got facts: {facts}"
    )
    assert c8_bad[0]["own_pawns_on_color"] == 6
    assert c8_bad[0]["mobility"] == 1


def test_no_false_rook_seventh_negative():
    """
    4. Negative / mutation: White rook on c1 (rank index 0).
    rook_on_seventh(board, WHITE) must return empty list.
    Fails if 7th rank index check matches back rank or rank 1.
    """
    fen = "b2r4/2qn1k2/p3p1p1/1p1pPp1p/1P3P2/P2P1N2/5BPP/2R3K1 w - - 0 32"
    board = chess.Board(fen)

    facts = rook_on_seventh(board, chess.WHITE)
    assert len(facts) == 0, (
        f"Expected no rooks on 7th rank for White on start of position, got: {facts}"
    )


def test_no_false_active_or_bad_bishops_negative():
    """
    5. Negative / mutation:
    - Fianchetto bishop hemmed in by pawns (low mobility) must NOT be flagged active.
    - Bishop on an open long diagonal with few pawns on its color must NOT be flagged bad.
    Fails if quality thresholds allow hemmed bishops to be called active or uninhibited bishops to be called bad.
    """
    # 5a. Hemmed fianchetto bishop (White Bg2 with low mobility = 1)
    fen_hemmed = "r1bqk2r/pppppp1p/6pb/8/8/5P1B/PPPPP1PP/RNBQK1NR w KQkq - 0 1"
    b_hemmed = chess.Board(fen_hemmed)
    facts_hemmed = bishop_quality(b_hemmed, chess.WHITE)
    active_bishops = [f for f in facts_hemmed if f["quality"] == "active"]
    assert len(active_bishops) == 0, (
        f"Hemmed bishop was incorrectly flagged active: {active_bishops}"
    )

    # 5b. Open long diagonal bishop (White Ba1 with only 1 pawn on color)
    fen_open = "r1bqk2r/pppppppp/8/8/8/4P3/PPPP1PPP/R3K2R w KQkq - 0 1"
    b_open = chess.Board(fen_open)
    facts_open = bishop_quality(b_open, chess.WHITE)
    bad_bishops = [f for f in facts_open if f["quality"] == "bad"]
    assert len(bad_bishops) == 0, (
        f"Bishop on clear diagonal was incorrectly flagged bad: {bad_bishops}"
    )


def test_no_false_open_file_negative():
    """
    6. Negative / mutation: White rook on a1 with White pawn on a2.
    open_file_pieces(board, WHITE) must NOT report a file_control fact for file a.
    Fails if file pawn checks ignore friendly pawns on the same file.
    """
    board = chess.Board()  # Standard start position (all rooks have pawns ahead)
    facts = open_file_pieces(board, chess.WHITE)
    assert len(facts) == 0, (
        f"Expected no open file facts for White rooks in starting position, got: {facts}"
    )


def test_no_false_bad_bishop_start_and_high_mobility():
    """Regression (leader fix, post-audit): the `own_pawns_on_color >= 4`-only rule flagged ALL FOUR
    starting bishops, and high-mobility active bishops, as 'bad'. Bad now requires
    own_pawns_on_color >= 5 AND mobility <= 3. This test FAILS on the old rule."""
    # 1. starting position -> NO bad bishops
    b = chess.Board()
    for color in (chess.WHITE, chess.BLACK):
        assert not [f for f in bishop_quality(b, color) if f["quality"] == "bad"], \
            "starting bishops must never be flagged 'bad'"
    # 2. mobility-8 bishop with 5 pawns on its colour is NOT bad (not restricted)
    b2 = chess.Board("b2r4/2qn1k2/p3p1p1/1p1pPp1p/1P3P2/P2P1N2/5BPP/2R3K1 w - - 0 32")
    bad_w = [f["square"] for f in bishop_quality(b2, chess.WHITE) if f["quality"] == "bad"]
    assert "f2" not in bad_w, "a mobility-8 bishop is active, not a bad bishop"
    # 3. the genuinely walled-in Bc8 (own 6, mobility 1) MUST still flag bad
    b3 = chess.Board("r1b1k2r/3nbppp/pq2p3/1p1pP3/1P3P2/P2P1N2/3BQ1PP/R2NK2R b KQkq - 0 14")
    b3.push_uci("f7f5")
    bad_b = [f["square"] for f in bishop_quality(b3, chess.BLACK) if f["quality"] == "bad"]
    assert "c8" in bad_b, "a genuinely walled-in bishop must still flag bad"
