"""Tests for PhiScorer configuration steering inference and move re-ranking."""

from __future__ import annotations

from pathlib import Path
import chess
import pytest
import torch

from backend.training.config_steering.scorer import PhiScorer

CHECKPOINT = Path("phi_net/runs/phi_b2.pt")


@pytest.fixture(scope="module")
def scorer():
    if not CHECKPOINT.exists():
        pytest.skip(f"{CHECKPOINT} not found")
    return PhiScorer(checkpoint_path=CHECKPOINT, device="cpu")


def test_scorer_loads_and_has_20_motifs(scorer):
    assert len(scorer.themes) == 20
    assert "fork" in scorer.themes
    assert "pin" in scorer.themes


def test_score_board_quiet_vs_sharp(scorer):
    # Quiet starting position
    b_quiet = chess.Board()
    phi_quiet, motifs_quiet = scorer.score_board(b_quiet)
    assert 0.0 <= phi_quiet <= 1.0
    assert len(motifs_quiet) == 20

    # Sharp position where Black has played an aggressive piece sacrifice / fork setup
    b_sharp = chess.Board("r1bqkb1r/pppp1ppp/2n5/4p3/2B1n3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 5")
    phi_sharp, motifs_sharp = scorer.score_board(b_sharp)

    assert phi_sharp > phi_quiet, (
        f"Expected sharp position ({phi_sharp:.4f}) to have higher Phi than quiet ({phi_quiet:.4f})"
    )


def test_score_move_evaluates_opponent_perspective(scorer):
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    phi_after, motifs_after = scorer.score_move(board, move)
    assert 0.0 <= phi_after <= 1.0
    assert len(motifs_after) == 20


def test_steer_candidates_respects_lc0_veto_and_reranks_by_phi(scorer):
    board = chess.Board("r1bqkb1r/pppp1ppp/2n5/4p3/2B1n3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 5")
    candidates = [
        # Move 1: Objective best (+40 cp)
        {"uci": "d2d4", "san": "d4", "eval_cp": 40},
        # Move 2: Playable and sharp (+10 cp, 30 cp loss vs best, inside 60 cp threshold)
        {"uci": "c4f7", "san": "Bxf7+", "eval_cp": 10},
        # Move 3: Unsound blunder (-120 cp, vetoed by LC0)
        {"uci": "h2h3", "san": "h3", "eval_cp": -120},
    ]

    result = scorer.steer_candidates(
        board=board,
        candidates=candidates,
        best_eval_cp=40,
        steer_max_loss_cp=60,
        steer_min_eval_cp=-60,
        steer_edge=0.01,
    )

    playable = result["playable"]
    # Blunder must be vetoed
    assert len(playable) == 2
    assert "h2h3" not in [c["uci"] for c in playable]

    # Both playable moves must carry calculated Phi scores
    for c in playable:
        assert "phi" in c
        assert "motifs" in c

    # Ranked by Phi descending
    assert playable[0]["phi"] >= playable[1]["phi"]
    assert result["objective_best"]["uci"] == "d2d4"
    assert result["sharp_move"] is not None
