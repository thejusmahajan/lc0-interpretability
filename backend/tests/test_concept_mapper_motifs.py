"""
Tests for concept_mapper tactical motif observation integration.
"""

from unittest.mock import patch
import chess
from backend.concept_mapper import analyze_position
from backend.tactics import MotifDetector


def test_real_tactic_tagged():
    # Back-rank mate setup:
    # pre_fen: Black to move with pawn on a7 (rank 7: p4ppp), plays 1... a6 (setup_uci = "a7a6")
    pre_fen = "6k1/p4ppp/8/8/8/8/8/4R1K1 b - - 0 1"
    setup_uci = "a7a6"
    # fen: position reached after 1... a6 (White to move)
    fen = "6k1/5ppp/p7/8/8/8/8/4R1K1 w - - 0 2"
    engine_analysis = {
        "pv_lines": ["Re8#"],
        "evaluation": 1000,
        "best_moves": [{"move": "e1e8"}],
    }

    result = analyze_position(
        fen=fen,
        engine_analysis=engine_analysis,
        pre_fen=pre_fen,
        setup_uci=setup_uci,
    )

    motif_obs = [
        obs for obs in result["observations"] if obs["category"] == "tactical_motifs"
    ]
    assert len(motif_obs) == 1
    assert "tactical motifs" in motif_obs[0]["text"].lower()


def test_no_context_no_false_observation():
    # Same position and engine output, but without pre_fen and setup_uci (e.g. /analyze bare FEN)
    fen = "6k1/5ppp/p7/8/8/8/8/4R1K1 w - - 0 2"
    engine_analysis = {
        "pv_lines": ["Re8#"],
        "evaluation": 1000,
        "best_moves": [{"move": "e1e8"}],
    }

    result = analyze_position(fen=fen, engine_analysis=engine_analysis)

    motif_obs = [
        obs for obs in result["observations"] if obs["category"] == "tactical_motifs"
    ]
    assert len(motif_obs) == 0


def test_eval_pov_negated_for_black():
    # Position where Black is to move (solver is Black)
    # pre_fen: White to move, plays 1. e4 (setup_uci = "e2e4")
    pre_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    setup_uci = "e2e4"
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    engine_analysis = {
        "pv_lines": ["e7e5 Nf3 Nc6"],
        "evaluation": 300,  # +300 in White POV
        "best_moves": [{"move": "e7e5"}],
    }

    captured_cp = None

    def spy_analyze_pv(pre_fen_arg, setup_uci_arg, pv_san, cp):
        nonlocal captured_cp
        captured_cp = cp
        return set()

    with patch.object(MotifDetector, "analyze_pv", side_effect=spy_analyze_pv):
        analyze_position(
            fen=fen,
            engine_analysis=engine_analysis,
            pre_fen=pre_fen,
            setup_uci=setup_uci,
        )

    # Since Black is solver (side to move at fen), +300 White POV must be -300 mover POV
    assert captured_cp == -300
