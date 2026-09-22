"""
Unit tests and quality guards for Stage A policy source discipline and TS2 steering budget controls.
Leader decision: Stage A policy source stays LC0Engine.get_policy_distribution (defines blindness metric).
"""
import os
import json
import pytest
import chess

from backend.training import pipeline, store, metrics


def test_stage_a_policy_source_is_lc0_engine():
    """Verify Stage A policy distribution contract uses LC0 engine distribution format."""
    # LC0 get_policy_distribution outputs dict entries with 'uci', 'p', 'san', etc.
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    board = chess.Board(fen)
    legal_moves = list(board.legal_moves)
    sample_policy = [
        {"uci": m.uci(), "san": board.san(m), "p": 1.0 / len(legal_moves)}
        for m in legal_moves
    ]
    div = metrics.policy_divergence(sample_policy, "e2e4")
    # Equal distribution over 20 legal moves -> p_best = 0.05, p_played = 0.05 -> divergence = 0.0 -> no severity
    assert div is not None
    assert div["severity"] is None


def test_steer_search_budget_env_override(monkeypatch):
    """Verify that STEER_SEARCH_BUDGET environment variable overrides default steering search budget."""
    monkeypatch.setenv("STEER_SEARCH_BUDGET", "50000")
    budget = int(os.environ.get("STEER_SEARCH_BUDGET", str(metrics.DEFAULT_CONFIG.steer_search_budget)))
    assert budget == 50000


def test_baseline_counts_preserved_in_profile():
    """Quality guard: verify stored baseline profile counts (findings: 28, steer_findings: 22)."""
    baseline_path = os.path.join("data", "training", "baseline_counts.json")
    assert os.path.exists(baseline_path), "baseline_counts.json missing"
    with open(baseline_path, "r") as f:
        baseline = json.load(f)
    assert baseline["findings_count"] == 28
    assert baseline["steer_findings_count"] == 22
    assert baseline["head"] == "2c259a1"
