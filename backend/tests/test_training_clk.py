"""Time-scramble filter: [%clk] parsing and skip decisions."""

import io

import chess.pgn

from backend.training import metrics, pipeline


def test_clock_seconds_parses_lichess_format():
    assert pipeline.clock_seconds("[%clk 0:02:00]") == 120.0
    assert pipeline.clock_seconds("[%clk 1:00:05]") == 3605.0
    assert pipeline.clock_seconds("[%clk 0:00:03.5]") == 3.5
    assert pipeline.clock_seconds("text [%clk 0:00:19] more") == 19.0


def test_clock_seconds_none_without_annotation():
    assert pipeline.clock_seconds("") is None
    assert pipeline.clock_seconds(None) is None
    assert pipeline.clock_seconds("[%eval 0.3]") is None


def test_is_time_scramble_threshold():
    cfg = metrics.TrainingConfig()  # min_clock_seconds = 20
    assert pipeline.is_time_scramble("[%clk 0:00:19]", cfg) is True
    assert pipeline.is_time_scramble("[%clk 0:00:20]", cfg) is False
    assert pipeline.is_time_scramble("[%clk 0:01:30]", cfg) is False
    # No clock data -> never a scramble (full analysis for plain PGNs).
    assert pipeline.is_time_scramble("", cfg) is False


def test_mainline_comments_reach_filter():
    """The pipeline reads clocks off mainline nodes — make sure a real
    lichess-style PGN round-trips into per-move comments."""
    pgn = io.StringIO(
        '[Event "test"]\n[White "a"]\n[Black "b"]\n\n'
        "1. e4 { [%clk 0:02:00] } 1... e5 { [%clk 0:00:10] } 2. Nf3 *\n")
    game = chess.pgn.read_game(pgn)
    flags = [pipeline.is_time_scramble(node.comment) for node in game.mainline()]
    assert flags == [False, True, False]
