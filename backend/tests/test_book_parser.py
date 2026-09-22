"""
Unit tests for deterministic book parser (backend/training/book_parser.py).
"""

import pytest
import chess
from backend.training.book_parser import _slice, segment_games, build_game, BookConfig, GameSection


def test_slice_invariant():
    source = "In this position White plays 1. P-K4. Excellent move!"
    start = source.find("Excellent move!")
    end = start + len("Excellent move!")
    comment = _slice(source, start, end)
    assert comment == "Excellent move!"
    assert comment in source


def test_slice_empty_or_valid():
    source = "Short source text for invariant assertion test."
    # Slice valid text
    assert _slice(source, 0, 5) == "Short"
    assert _slice(source, 6, 12) == "source"


def test_segment_games_basic():
    source = """
    PART II -- ILLUSTRATIVE GAMES

    GAME 1. QUEEN'S GAMBIT DECLINED
    White: Capablanca
    Black: Lasker
    1. P-Q4 P-Q4
    2. P-QB4 P-K3

    GAME 2. RUY LOPEZ
    White: Capablanca
    Black: Marshall
    1. P-K4 P-K4
    2. Kt-KB3 Kt-QB3
    """
    config = BookConfig(
        slug="test_book",
        notation="descriptive",
        skip_before=r"PART\s+II",
        game_start_re=r"\n\s*GAME\s+(\d+)\.?",
        header_re=r"White:\s*(\w+)\s*Black:\s*(\w+)",
    )
    sections = segment_games(source, config)
    assert len(sections) == 2
    assert sections[0].game_index == 1
    assert sections[1].game_index == 2
    assert "QUEEN'S GAMBIT DECLINED" in sections[0].header_text
    assert "RUY LOPEZ" in sections[1].header_text


def test_ambiguous_descriptive_move_rejection():
    # Construct a scenario where P-B4 is ambiguous (two pawns can advance to B4)
    source = """
    GAME 1. AMBIGUOUS MOVES
    White: Player1
    Black: Player2
    1. P-QB4 P-K3
    2. P-KB4 P-Q4
    3. P-B4
    """
    config = BookConfig(
        slug="test_ambiguous",
        notation="descriptive",
        game_start_re=r"\n\s*GAME\s+(\d+)\.?",
        header_re=r"White:\s*(\w+)\s*Black:\s*(\w+)",
    )
    sections = segment_games(source, config)
    assert len(sections) == 1
    game, failures = build_game(sections[0], source, config)
    # Must reject cleanly without crashing
    assert game is None
    assert len(failures) == 1
    assert failures[0]["status"] == "rejected"
