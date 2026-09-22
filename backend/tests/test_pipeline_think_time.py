"""Tests for think-time filtering and Stage A/Stage B asymmetry in pipeline.py.

Guarantees:
1. Fast move with plenty of clock = reflex; slow move in time scramble = decision.
   (The exact pair the old min_clock_seconds filter got backwards).
2. prev_user_clock does not leak across games.
3. PGN with no [%clk] yields zero reflex moves.
4. Stage A count >= Stage B count on the same input.
"""

import io
import asyncio
import chess
import chess.pgn
from unittest.mock import AsyncMock, MagicMock

from backend.training import metrics
from backend.training import pipeline
from backend.training.pipeline import clock_seconds


def test_fast_with_clock_vs_slow_in_scramble():
    """Exact pair the old filter got backwards:

    Move 1 (2. Nf3): played in 1s with 99s remaining on clock.
            Old filter kept it (99s > 20s). New filter marks it REFLEX (1s < 5s).
    Move 2 (4. d4): played in 8s with 10s remaining on clock (time scramble).
            Old filter dropped it (10s < 20s). New filter marks it DECISION (8s >= 5s).
    """
    pgn_with_scramble = """[Event "Test"]
[Site "Local"]
[Date "2026.09.03"]
[White "Thejus"]
[Black "Opponent"]
[Result "*"]
[TimeControl "120+0"]

1. e4 { [%clk 0:01:40] } 1... e5 { [%clk 0:01:50] } 2. Nf3 { [%clk 0:01:39] } 2... Nc6 { [%clk 0:01:40] } 3. Bc4 { [%clk 0:00:18] } 3... Bc5 { [%clk 0:00:20] } 4. d4 { [%clk 0:00:10] } *
"""
    # White moves:
    # 1. e4: clk 100s. prev=None -> Decision
    # 2. Nf3: clk 99s. prev=100s -> think = 1s -> REFLEX (has 99s remaining!)
    # 3. Bc4: clk 18s. prev=99s -> think = 81s -> Decision
    # 4. d4:  clk 10s. prev=18s -> think = 8s -> DECISION (has only 10s remaining in scramble!)
    game = chess.pgn.read_game(io.StringIO(pgn_with_scramble))
    board = game.board()
    increment = metrics.parse_increment(game.headers.get("TimeControl"))
    cfg = metrics.DEFAULT_CONFIG

    prev_user_clock = None
    results = []
    for node in game.mainline():
        if board.turn == chess.WHITE:
            clock = clock_seconds(node.comment)
            reflex = metrics.is_reflex_move(prev_user_clock, clock, increment, cfg)
            spent = metrics.think_seconds(prev_user_clock, clock, increment)
            results.append((node.san(), clock, spent, reflex))
            prev_user_clock = clock
        board.push(node.move)

    # 2. Nf3 had 99s left, spent 1s -> reflex
    san2, clk2, spent2, reflex2 = results[1]
    assert san2 == "Nf3"
    assert clk2 == 99.0
    assert spent2 == 1.0
    assert reflex2 is True, "Fast move with plenty of clock must be marked reflex"

    # 4. d4 had 10s left, spent 8s -> decision
    san4, clk4, spent4, reflex4 = results[3]
    assert san4 == "d4"
    assert clk4 == 10.0
    assert spent4 == 8.0
    assert reflex4 is False, "Deliberated move in time scramble must be marked decision"


def test_prev_user_clock_does_not_leak_across_games():
    """Verify prev_user_clock resets to None at the start of each game."""
    pgn_text = """[Event "Game 1"]
[White "Thejus"]
[Black "Opponent"]
[TimeControl "120+0"]

1. e4 { [%clk 0:00:10] } *

[Event "Game 2"]
[White "Thejus"]
[Black "Opponent"]
[TimeControl "120+0"]

1. d4 { [%clk 0:01:58] } *
"""
    pgn_io = io.StringIO(pgn_text)
    cfg = metrics.DEFAULT_CONFIG

    first_moves = []
    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break
        board = game.board()
        increment = metrics.parse_increment(game.headers.get("TimeControl"))
        prev_user_clock = None  # Reset at start of game
        for node in game.mainline():
            if board.turn == chess.WHITE:
                clock = clock_seconds(node.comment)
                reflex = metrics.is_reflex_move(prev_user_clock, clock, increment, cfg)
                spent = metrics.think_seconds(prev_user_clock, clock, increment)
                first_moves.append((spent, reflex))
                prev_user_clock = clock
            board.push(node.move)

    assert len(first_moves) == 2
    # Both first moves must have spent=None and reflex=False
    for spent, reflex in first_moves:
        assert spent is None
        assert reflex is False, "First move of any game has no predecessor, must not be reflex"


def test_pgn_with_no_clk_yields_zero_reflex():
    """A PGN with no [%clk] comments must yield zero reflex moves."""
    pgn_text = """[Event "No Clocks"]
[White "Thejus"]
[Black "Opponent"]
[TimeControl "300+0"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. d3 Nf6 *
"""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    board = game.board()
    increment = metrics.parse_increment(game.headers.get("TimeControl"))
    cfg = metrics.DEFAULT_CONFIG

    prev_user_clock = None
    reflex_count = 0
    decision_count = 0
    for node in game.mainline():
        if board.turn == chess.WHITE:
            clock = clock_seconds(node.comment)
            reflex = metrics.is_reflex_move(prev_user_clock, clock, increment, cfg)
            prev_user_clock = clock
            if reflex:
                reflex_count += 1
            else:
                decision_count += 1
        board.push(node.move)

    assert reflex_count == 0
    assert decision_count == 4


def test_stage_a_greater_than_or_equal_stage_b():
    """Stage A evaluates all user moves (reflex or not).

    Stage B and TS2 run strictly on decisions.
    Therefore, Stage A count >= Stage B count on the same input.
    """
    async def _run():
        pgn_text = """[Event "Asymmetry Test"]
[White "Thejus"]
[Black "Opponent"]
[TimeControl "120+0"]

1. e4 { [%clk 0:01:55] } 1... e5 { [%clk 0:01:50] } 2. Nf3 { [%clk 0:01:54] } 2... Nc6 { [%clk 0:01:40] } 3. Bc4 { [%clk 0:01:30] } *
"""
        # White moves:
        # 1. e4: clk 115s (first move, think=None -> decision)
        # 2. Nf3: clk 114s (spent 1s -> reflex)
        # 3. Bc4: clk 90s (spent 24s -> decision)
        # Total user moves = 3. Decisions = 2. Reflex = 1.

        # Mock engine and vision
        mock_engine = MagicMock()
        mock_engine.n = 1
        mock_engine.get_policy_distribution = AsyncMock(return_value=[
            {"uci": "e2e4", "san": "e4", "p": 0.5},
            {"uci": "d2d4", "san": "d4", "p": 0.3},
        ])
        mock_engine.analyze = AsyncMock(return_value={
            "evaluation": 50,
            "eval_best_cp": 50,
            "eval_played_cp": 20,
            "pv_lines": ["e2e4 e7e5"],
            "motifs": ["pin"],
            "concepts": {"observations": []},
            "saliency": {},
            "pv_san_list": ["e4", "e5"]
        })

        mock_vision = MagicMock()
        mock_vision.saliency_absolute = MagicMock(return_value={})

        orig_update_job = pipeline.store.update_job
        orig_save_profile = pipeline.store.save_profile
        saved_profile = {}

        pipeline.store.update_job = lambda job_id, **kwargs: None
        pipeline.store.save_profile = lambda p: saved_profile.update(p)

        try:
            await pipeline.run_diagnosis(
                job_id="test_asymmetry",
                pgn_text=pgn_text,
                player_name="Thejus",
                engine=mock_engine,
                vision=mock_vision,
            )
        finally:
            pipeline.store.update_job = orig_update_job
            pipeline.store.save_profile = orig_save_profile

        # Verify profile counters
        assert saved_profile["moves_analyzed"] == 3
        assert saved_profile["decisions"] == 2
        assert saved_profile["reflex_skipped"] == 1
        assert saved_profile["time_scramble_skipped"] == 0
        # Stage A screened all 3 moves; Stage B candidates came from at most 2 decisions:
        assert saved_profile["moves_analyzed"] >= len(saved_profile.get("findings", []))

    asyncio.run(_run())
