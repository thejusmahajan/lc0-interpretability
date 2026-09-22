"""Guard for engine_manager.terminal_analysis: no-legal-move positions
(checkmate / stalemate) must return a synthetic eval instead of being sent to
lc0, which emits 'bestmove a1a1' and crashes the UCI parser (real incident:
diagnosis crashed at TS2 on a candidate move that delivered mate)."""
import chess
from backend.engine_manager import terminal_analysis


def test_white_checkmated_is_white_pov_loss():
    # Fool's mate: white to move and checkmated -> white-POV loss.
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert board.is_checkmate() and board.turn == chess.WHITE
    r = terminal_analysis(board)
    assert r["evaluation"] == -10000
    assert r["wdl"] == [0, 0, 1000]
    assert r["best_moves"] == [] and r["pv_lines"] == []


def test_black_checkmated_is_white_pov_win():
    # Scholar's mate: black to move and checkmated -> white-POV win.
    board = chess.Board("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
    assert board.is_checkmate() and board.turn == chess.BLACK
    r = terminal_analysis(board)
    assert r["evaluation"] == 10000
    assert r["wdl"] == [1000, 0, 0]


def test_stalemate_is_draw():
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert board.is_stalemate()
    r = terminal_analysis(board)
    assert r["evaluation"] == 0
    assert r["wdl"] == [0, 1000, 0]
