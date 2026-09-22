"""Guards for the think-time filter (metrics.min_think_seconds), 2026-09-03.

This replaces the clock-remaining filter, which gated on the wrong variable:
in a 2+1 game a move played in one second with 60s left was KEPT, while a move
deliberated for eight seconds with 15s left was DISCARDED. These tests pin that
distinction, because it is invisible in any aggregate number.
"""

import pytest

from backend.training import metrics


# ----------------------------------------------------------------- increment
def test_parse_increment_reads_the_pgn_header():
    assert metrics.parse_increment("120+1") == 1.0
    assert metrics.parse_increment("300+3") == 3.0
    assert metrics.parse_increment("60+0") == 0.0


def test_parse_increment_is_zero_when_unknown():
    """Unknown increment must UNDER-state think time, so an unparseable header
    errs toward discarding a move rather than admitting a reflex one."""
    for header in (None, "", "-", "?", "300", "abc+xyz"):
        assert metrics.parse_increment(header) == 0.0


# --------------------------------------------------------------- think time
def test_think_seconds_includes_the_increment():
    # 120 -> 118 on the clock in a +1 game means 3 seconds were actually spent
    assert metrics.think_seconds(120.0, 118.0, 1.0) == 3.0


def test_think_seconds_without_increment():
    assert metrics.think_seconds(60.0, 52.0, 0.0) == 8.0


def test_think_seconds_is_none_when_a_clock_is_missing():
    """The first move of a game has no predecessor. Unknown must stay unknown
    and must never collapse to zero."""
    assert metrics.think_seconds(None, 100.0, 1.0) is None
    assert metrics.think_seconds(100.0, None, 1.0) is None


def test_think_seconds_rejects_impossible_negatives():
    """A clock that went UP is a berserk, an adjustment or a parse error. It must
    not silently become a small positive think time."""
    assert metrics.think_seconds(100.0, 120.0, 1.0) is None


# ------------------------------------------------------------------- filter
def test_fast_move_with_plenty_of_clock_is_a_reflex_move():
    """THE CASE THE OLD FILTER GOT WRONG. Played in ~1s with 100s left: the
    clock-remaining filter kept it; it is a reflex, not a decision."""
    assert metrics.is_reflex_move(prev_clock=101.0, clock=101.0, increment=1.0) is True


def test_slow_move_in_time_trouble_is_a_real_decision():
    """THE OTHER CASE THE OLD FILTER GOT WRONG. Eight seconds of thought with
    only 15s left: the clock-remaining filter discarded it; it is a decision."""
    assert metrics.is_reflex_move(prev_clock=22.0, clock=15.0, increment=1.0) is False


def test_threshold_is_min_think_seconds():
    cfg = metrics.TrainingConfig()
    assert cfg.min_think_seconds == 5.0
    # exactly at the threshold counts as a decision
    assert metrics.is_reflex_move(10.0, 5.0, 0.0, cfg) is False
    # just under does not
    assert metrics.is_reflex_move(10.0, 5.1, 0.0, cfg) is True


def test_unknown_think_time_is_analysed_not_discarded():
    """A PGN with no [%clk] must be analysed in full, exactly as before."""
    assert metrics.is_reflex_move(None, None, 0.0) is False


def test_threshold_is_configurable():
    strict = metrics.TrainingConfig(min_think_seconds=10.0)
    assert metrics.is_reflex_move(20.0, 13.0, 0.0, strict) is True   # 7s < 10s
    assert metrics.is_reflex_move(20.0, 13.0, 0.0) is False          # 7s >= 5s
