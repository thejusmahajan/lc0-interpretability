"""
Unit tests for MotifDetector.analyze_pv and Lichess tagger integration.
Mutation checks:
1. Real sacrifice on solver's side emits "sacrifice".
2. Material-winning line (old false positive) does NOT emit "sacrifice".
3. Puzzle.pov matches solver's turn at fen_before (not inverted).
4. Low/quiet centipawn eval (cp <= 200) does not force-tag "advantage".
5. None/empty inputs return set() safely.
"""

import chess
import chess.pgn
from backend.tactics import MotifDetector
from backend.lichess_tagger import Puzzle

def test_real_sacrifice_emits_sacrifice_tag():
    """Greek gift sac: White gives up Bishop for Pawn and stays winning."""
    # pre_fen: Black to move
    pre_fen = "r1bq1rk1/ppp2ppp/2n1pn2/3p4/2PP4/3BPN2/PP1N1PPP/R2Q1RK1 b - - 0 7"
    setup_uci = "a7a6"  # Black setup move reaching fen_before (White turn)

    # White solver line: 1. Bxh7+ Kxh7 2. Ng5+ Kg8 3. Qh5
    pv_san = ["Bxh7+", "Kxh7", "Ng5+", "Kg8", "Qh5"]
    tags = MotifDetector.analyze_pv(pre_fen, setup_uci, pv_san, cp=500)

    assert "sacrifice" in tags, f"Expected 'sacrifice' in tags, got: {tags}"


def test_material_winning_line_does_not_emit_sacrifice():
    """Line where solver wins material (e.g. fork winning a rook) is NOT a sacrifice."""
    # pre_fen: White to move
    pre_fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    setup_uci = "c2c3"  # White setup move reaching fen_before (Black turn)

    # Black solver line: 1... Qh4 2. g3 Qxe4+ 3. Qe2 Qxh1 (Black wins rook)
    pv_san = ["Qh4", "g3", "Qxe4+", "Qe2", "Qxh1"]
    tags = MotifDetector.analyze_pv(pre_fen, setup_uci, pv_san, cp=500)

    assert "sacrifice" not in tags, f"Expected 'sacrifice' NOT in tags for material-winning line, got: {tags}"


def test_puzzle_pov_matches_solver_turn_at_fen_before():
    """Puzzle.pov must equal the solver's color (the turn at fen_before), NOT inverted."""
    # pre_fen: Black to move
    pre_fen = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R b KQkq - 5 4"
    setup_uci = "h7h6"  # Reaches fen_before (White to move)

    board = chess.Board(pre_fen)
    game = chess.pgn.Game()
    game.setup(board)

    setup_move = chess.Move.from_uci(setup_uci)
    node = game.add_variation(setup_move)

    puzzle = Puzzle(id="lc0_pv", game=game, cp=300)

    # game.turn() is Black (pre_fen turn), so puzzle.pov = not game.turn() = White (solver turn)
    assert puzzle.pov == chess.WHITE
    assert puzzle.pov == chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 6 5").turn


def test_cp_evaluation_threshold_for_advantage_tag():
    """With a quiet/low cp eval (cp <= 200), 'advantage' tag is not emitted."""
    pre_fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    setup_uci = "a7a6"
    pv_san = ["d2d4", "e5d4"]

    tags = MotifDetector.analyze_pv(pre_fen, setup_uci, pv_san, cp=50)
    assert "advantage" not in tags, f"Expected 'advantage' NOT in tags for cp=50, got: {tags}"

    tags_high = MotifDetector.analyze_pv(pre_fen, setup_uci, pv_san, cp=300)
    assert "advantage" in tags_high, f"Expected 'advantage' in tags for cp=300, got: {tags_high}"


def test_edge_cases_none_or_empty_inputs_return_empty_set():
    """Missing pre_fen, setup_uci, or empty pv_san return empty set safely."""
    assert MotifDetector.analyze_pv(None, "e2e4", ["e5"], cp=300) == set()
    assert MotifDetector.analyze_pv("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", None, ["e5"], cp=300) == set()
    assert MotifDetector.analyze_pv("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "e2e4", [], cp=300) == set()
