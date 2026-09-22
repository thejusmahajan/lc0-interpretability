"""
Unit & acceptance tests for descriptive notation generator and matcher (backend/training/descriptive_notation.py).
"""

import chess
import pytest
from backend.training.descriptive_notation import (
    to_descriptive,
    match_descriptive_move,
    parse_descriptive_game,
)


def test_basic_pawn_and_knight_moves():
    """1. Basic opening moves P-K4, P-K4, Kt-KB3, Kt-QB3."""
    b = chess.Board()
    # 1. P-K4
    m, matches = match_descriptive_move(b, "P-K4")
    assert m == chess.Move.from_uci("e2e4")
    b.push(m)

    # 1... P-K4
    m, matches = match_descriptive_move(b, "P-K4")
    assert m == chess.Move.from_uci("e7e5")
    b.push(m)

    # 2. Kt-KB3 / N-KB3
    m, matches = match_descriptive_move(b, "Kt-KB3")
    assert m == chess.Move.from_uci("g1f3")
    b.push(m)

    # 2... Kt-QB3 / N-QB3
    m, matches = match_descriptive_move(b, "N-QB3")
    assert m == chess.Move.from_uci("b8c6")


def test_two_knights_reach_same_square_disambiguation():
    """2. Two knights able to reach the same square (e.g. Nd3 vs Nf3 both able to play to e5)."""
    # White Knights on d3 and f3. Both can play to e5.
    fen = "rnbqk2r/pppp1ppp/8/8/8/3N1N2/PPPPPPPP/R2QKB1R w KQkq - 0 1"
    b = chess.Board(fen)

    m1, _ = match_descriptive_move(b, "KKt-E5")
    assert m1 == chess.Move.from_uci("f3e5")

    m2, _ = match_descriptive_move(b, "QKt-E5")
    assert m2 == chess.Move.from_uci("d3e5")


def test_two_rooks_on_same_rank_disambiguation():
    """3. Two rooks on a rank (e.g. Rooks on a1 and f1, playing QR-d1 vs KR-d1)."""
    # King on g1 so f1d1 is unblocked.
    fen = "r1b2rk1/pppp1ppp/2n2n2/4p3/4P3/2NP1N2/PPP2PPP/R4RK1 w - - 0 1"
    b = chess.Board(fen)

    m1, _ = match_descriptive_move(b, "QR-D1")
    assert m1 == chess.Move.from_uci("a1d1")

    m2, _ = match_descriptive_move(b, "KR-D1")
    assert m2 == chess.Move.from_uci("f1d1")


def test_pawn_capture_two_legal_takers():
    """4. Pawn capture with two legal takers (e.g. BPxP vs KPxP when d4 pawn can be taken by c5 or e5)."""
    # White pawn on d4, Black pawns on c5 and e5.
    fen = "rnbqkbnr/pp3ppp/8/2p1p3/3P4/8/PPP2PPP/RNBQKBNR b KQkq - 0 1"
    b = chess.Board(fen)

    m1, _ = match_descriptive_move(b, "BPxP")
    assert m1 == chess.Move.from_uci("c5d4")

    m2, _ = match_descriptive_move(b, "KPxP")
    assert m2 == chess.Move.from_uci("e5d4")


def test_all_four_promotions():
    """5. Promotions to Queen, Rook, Bishop, Knight (P-K8(Q), P-K8(R), P-K8(B), P-K8(Kt))."""
    # King on d8 so e8 is empty and promotion is legal.
    fen = "3k4/4P3/8/8/8/8/8/4K3 w - - 0 1"
    b = chess.Board(fen)

    mq, _ = match_descriptive_move(b, "P-K8(Q)")
    assert mq == chess.Move.from_uci("e7e8q")

    mr, _ = match_descriptive_move(b, "P-K8(R)")
    assert mr == chess.Move.from_uci("e7e8r")

    mb, _ = match_descriptive_move(b, "P-K8(B)")
    assert mb == chess.Move.from_uci("e7e8b")

    mn, _ = match_descriptive_move(b, "P-K8(Kt)")
    assert mn == chess.Move.from_uci("e7e8n")


def test_castling_spellings():
    """6. All castling spellings (O-O, 0-0, Castles, Castles KR, Castles QR, O-O-O, 0-0-0, K-Kt sq)."""
    # Kingside and Queenside castling available for White
    fen = "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"
    b = chess.Board(fen)

    for spelling in ["O-O", "0-0", "Castles", "Castles KR", "K-Kt sq"]:
        m, _ = match_descriptive_move(b, spelling)
        assert m == chess.Move.from_uci("e1g1"), f"Failed on kingside spelling {spelling}"

    for spelling in ["O-O-O", "0-0-0", "Castles QR"]:
        m, _ = match_descriptive_move(b, spelling)
        assert m == chess.Move.from_uci("e1c1"), f"Failed on queenside spelling {spelling}"


def test_en_passant_capture():
    """7. En passant capture (PxP e.p. / PxP ep)."""
    # White pawn on e5, Black pawn plays f7f5 (giving ep square f6)
    b = chess.Board("rnbqkbnr/ppppp1pp/8/4Pp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 1")

    m, _ = match_descriptive_move(b, "PxP e.p.")
    assert m == chess.Move.from_uci("e5f6")

    m2, _ = match_descriptive_move(b, "PxP ep")
    assert m2 == chess.Move.from_uci("e5f6")


def test_checks_and_mates_suffixes():
    """8. Checks and checkmate tokens (ch, dbl ch, dis ch, mate, #)."""
    # White Queen gives check on f7: QxP ch (Queen on f3, no piece blocking f-file)
    b = chess.Board("r1bqkb1r/pppp1ppp/2n5/4p3/4P3/5Q2/PPPP1PPP/RNB1KBNR w KQkq - 0 1")

    m, _ = match_descriptive_move(b, "QxP ch")
    assert m == chess.Move.from_uci("f3f7")

    m2, _ = match_descriptive_move(b, "QxP dbl ch")
    assert m2 == chess.Move.from_uci("f3f7")

    # Fool's mate: Q-R5#
    b_fools = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 1")
    m3, _ = match_descriptive_move(b_fools, "Q-R5#")
    assert m3 == chess.Move.from_uci("d8h4")


def test_deliberately_ambiguous_token_produces_failure():
    """9. Deliberately ambiguous token must NOT guess; must return None and matches count > 1."""
    # White Rooks on a1 and f1, King on g1. Move "R-D1" is ambiguous (a1d1 vs f1d1).
    fen = "rnbqkbnr/pppppppp/8/8/8/3P4/PPP1PPPP/R4RK1 w - - 0 1"
    b = chess.Board(fen)

    m, matches = match_descriptive_move(b, "R-D1")
    assert m is None, "Ambiguous token R-D1 must return None"
    assert len(matches) == 2, f"Expected 2 matching moves for R-D1, got {matches}"


def test_real_consecutive_book_game_parse():
    """10. 10+ real consecutive moves from Capablanca / Alekhine classic game."""
    # Capablanca vs Blanco, Havana 1913 (first 10 moves in descriptive notation)
    tokens = [
        "P-K4", "P-K4",
        "Kt-KB3", "Kt-QB3",
        "P-Q4", "PxP",
        "KtxP", "Kt-KB3",
        "Kt-QB3", "B-Kt5",
        "KtxKt", "KtPxKt",
        "B-Q3", "P-Q4",
        "PxP", "PxP",
        "Castles", "Castles",
        "B-KKt5", "P-B3",
    ]
    game, failures = parse_descriptive_game(tokens, {"White": "Capablanca", "Black": "Blanco"})

    assert failures == [], f"Game parsing produced failures: {failures}"
    assert game is not None
    assert len(list(game.mainline())) == 20
    assert game.headers["White"] == "Capablanca"


def test_sq_back_rank_home_square_notation():
    """11. Back-rank home square notation (Q sq, R sq, Kt sq, B sq)."""
    b = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")

    # Q-Q sq / Q-Q1
    m, _ = match_descriptive_move(b, "Q-Q sq")
    assert m is None  # Queen is on d1 already
    m2, _ = match_descriptive_move(b, "B-K sq")
    assert m2 is None


def test_capture_piece_over_file_notation():
    """12. Captures like QxP, RxKt, KtxKt, BxP."""
    b = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQ1RK1 w kq - 0 1")

    # BxP ch (Bxf7+)
    m, _ = match_descriptive_move(b, "BxP ch")
    assert m == chess.Move.from_uci("c4f7")


def test_lower_case_and_mixed_case_tokens():
    """13. Lower case tokens p-k4, kt-kb3, castles."""
    b = chess.Board()

    m1, _ = match_descriptive_move(b, "p-k4")
    assert m1 == chess.Move.from_uci("e2e4")
    b.push(m1)

    m2, _ = match_descriptive_move(b, "p-k4")
    assert m2 == chess.Move.from_uci("e7e5")
    b.push(m2)

    m3, _ = match_descriptive_move(b, "kt-kb3")
    assert m3 == chess.Move.from_uci("g1f3")


def test_invalid_token_returns_none():
    """14. Invalid or nonsense token returns None."""
    b = chess.Board()
    m, matches = match_descriptive_move(b, "X-Y9")
    assert m is None
    assert matches == []


def test_pawn_double_step_descriptive():
    """15. Pawn double step P-Q4, P-QB4, P-KB4."""
    b = chess.Board()

    m1, _ = match_descriptive_move(b, "P-Q4")
    assert m1 == chess.Move.from_uci("d2d4")

    m2, _ = match_descriptive_move(b, "P-QB4")
    assert m2 == chess.Move.from_uci("c2c4")


def test_disambiguated_rook_file_capture():
    """16. Disambiguated rook captures like QRxP vs KRxP."""
    # Rooks on a1 and h1, Black pawns on a7 and h7, no white pawns on a2 or h2
    b = chess.Board("r3k2r/p6p/8/8/8/8/8/R3K2R w KQkq - 0 1")

    m1, _ = match_descriptive_move(b, "QRxP")
    assert m1 == chess.Move.from_uci("a1a7")

    m2, _ = match_descriptive_move(b, "KRxP")
    assert m2 == chess.Move.from_uci("h1h7")


def test_knight_spelling_variants_n_vs_kt():
    """17. Knight spelling N vs Kt support."""
    b = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")

    m1, _ = match_descriptive_move(b, "N-KB3")
    assert m1 == chess.Move.from_uci("g8f6")

    m2, _ = match_descriptive_move(b, "Kt-KB3")
    assert m2 == chess.Move.from_uci("g8f6")


def test_black_rank_conversion_mirror():
    """18. Black rank conversion (Black P-K4 = e5, Black P-K3 = e6)."""
    b = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")

    m, _ = match_descriptive_move(b, "P-K4")
    assert m == chess.Move.from_uci("e7e5")

    m2, _ = match_descriptive_move(b, "P-K3")
    assert m2 == chess.Move.from_uci("e7e6")


def test_pawn_capture_with_file_prefix():
    """19. Pawn captures with file prefix like PxP or BPxP."""
    b = chess.Board("rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 1")

    m, _ = match_descriptive_move(b, "P-Q4")
    assert m == chess.Move.from_uci("d2d4")
    b.push(m)

    m2, _ = match_descriptive_move(b, "PxP")
    assert m2 == chess.Move.from_uci("c5d4")


def test_zero_legal_moves_match_returns_none():
    """20. Move not legal in position returns None and empty matches."""
    b = chess.Board()
    # P-K5 is not legal on move 1
    m, matches = match_descriptive_move(b, "P-K5")
    assert m is None
    assert matches == []
