import io
import pytest
import chess
import chess.pgn
from backend.training.pipeline import aggregate_phase_clock, _clock_bucket
from backend.training import metrics


def make_game(pgn_str: str):
    game = chess.pgn.read_game(io.StringIO(pgn_str))
    assert game is not None
    return game


def test_clock_bucket_helper():
    assert _clock_bucket(None) == "no_clock"
    assert _clock_bucket(10.0) == "fast"
    assert _clock_bucket(59.9) == "fast"
    assert _clock_bucket(60.0) == "normal"
    assert _clock_bucket(179.9) == "normal"
    assert _clock_bucket(180.0) == "slow"
    assert _clock_bucket(300.0) == "slow"


def test_phase_bucketing_and_blind_rate():
    # Valid 14-move game: 12 opening fullmoves + 2 middlegame fullmoves
    pgn_str = """[Event "Test"]
[White "User"]
[Black "Opponent"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. d3 Nf6 5. Nc3 d6 6. h3 h6
7. a3 a6 8. Be3 Bxe3 9. fxe3 Be6 10. Bxe6 fxe6 11. O-O O-O
12. Qe1 Qe8 13. Qg3 Kh7 14. Rf2 Qg6 *
"""
    game = make_game(pgn_str)
    games_to_process = [(game, chess.WHITE)]

    # Ply 1 (1. e4) is opening. Flag it as blind.
    findings = [{"game_idx": 0, "ply": 1, "severity": "blind"}]

    by_phase, by_clock = aggregate_phase_clock(games_to_process, findings)

    # 12 opening moves (ply 1, 3, ..., 23) + 2 middlegame moves (ply 25, 27) for White
    assert by_phase["opening"]["moves"] == 12
    assert by_phase["opening"]["blind"] == 1
    assert pytest.approx(by_phase["opening"]["blind_rate"], rel=1e-3) == 1 / 12

    assert by_phase["middlegame"]["moves"] == 2
    assert by_phase["middlegame"]["blind"] == 0
    assert by_phase["middlegame"]["blind_rate"] == 0.0


def test_clock_bucketing():
    pgn_str = """[Event "Test"]
[White "User"]
[Black "Opponent"]

1. e4 { [%clk 0:05:00] } e5 { [%clk 0:05:00] }
2. Nf3 { [%clk 0:02:00] } Nc6 { [%clk 0:02:00] }
3. Bc4 { [%clk 0:00:45] } Bc5 { [%clk 0:00:45] }
4. d3 d6 *
"""
    game = make_game(pgn_str)
    games_to_process = [(game, chess.WHITE)]
    findings = []

    by_phase, by_clock = aggregate_phase_clock(games_to_process, findings)

    assert by_clock["slow"]["moves"] == 1      # 1. e4 (5:00)
    assert by_clock["normal"]["moves"] == 1    # 2. Nf3 (2:00)
    assert by_clock["fast"]["moves"] == 1      # 3. Bc4 (0:45)
    assert by_clock["no_clock"]["moves"] == 1  # 4. d3 (no clk)


def test_game_idx_ply_off_by_one_guard():
    pgn_str = """[Event "Test"]
[White "User"]
[Black "Opponent"]

1. e4 { [%clk 0:05:00] } e5 { [%clk 0:05:00] }
2. Nf3 { [%clk 0:02:00] } Nc6 { [%clk 0:02:00] } *
"""
    game = make_game(pgn_str)
    games_to_process = [(game, chess.WHITE)]

    # Ply 1 (1. e4) is slow (5:00). Ply 3 (2. Nf3) is normal (2:00).
    findings_ply1 = [{"game_idx": 0, "ply": 1, "severity": "blind"}]
    by_phase, by_clock = aggregate_phase_clock(games_to_process, findings_ply1)
    assert by_clock["slow"]["blind"] == 1
    assert by_clock["normal"]["blind"] == 0

    # Mutate ply to 3 (normal)
    findings_ply3 = [{"game_idx": 0, "ply": 3, "severity": "blind"}]
    _, by_clock_3 = aggregate_phase_clock(games_to_process, findings_ply3)
    assert by_clock_3["slow"]["blind"] == 0
    assert by_clock_3["normal"]["blind"] == 1

    # Mutate ply to 2 (opponent move) or off-by-one ply 0
    findings_ply2 = [{"game_idx": 0, "ply": 2, "severity": "blind"}]
    _, by_clock_2 = aggregate_phase_clock(games_to_process, findings_ply2)
    assert by_clock_2["slow"]["blind"] == 0
    assert by_clock_2["normal"]["blind"] == 0


def test_time_scramble_moves_excluded():
    pgn_str = """[Event "Test"]
[White "User"]
[Black "Opponent"]

1. e4 { [%clk 0:00:05] } e5 { [%clk 0:05:00] } *
"""
    game = make_game(pgn_str)
    games_to_process = [(game, chess.WHITE)]
    findings = [{"game_idx": 0, "ply": 1, "severity": "blind"}]

    by_phase, by_clock = aggregate_phase_clock(games_to_process, findings)

    total_moves = sum(b["moves"] for b in by_phase.values())
    total_blind = sum(b["blind"] for b in by_phase.values())
    assert total_moves == 0
    assert total_blind == 0


def test_opponent_moves_ignored():
    pgn_str = """[Event "Test"]
[White "Opponent"]
[Black "User"]

1. e4 { [%clk 0:05:00] } e5 { [%clk 0:05:00] } *
"""
    game = make_game(pgn_str)
    games_to_process = [(game, chess.BLACK)]

    # Ply 1 is White (opponent), Ply 2 is Black (user)
    findings = [
        {"game_idx": 0, "ply": 1, "severity": "blind"},
        {"game_idx": 0, "ply": 2, "severity": "blind"},
    ]

    by_phase, by_clock = aggregate_phase_clock(games_to_process, findings)

    total_moves = sum(b["moves"] for b in by_phase.values())
    total_blind = sum(b["blind"] for b in by_phase.values())
    assert total_moves == 1  # Only ply 2
    assert total_blind == 1  # Only ply 2


def test_missed_counted_and_empty_inputs_safe():
    pgn_str = """[Event "Test"]
[White "User"]
[Black "Opponent"]

1. e4 { [%clk 0:05:00] } e5 { [%clk 0:05:00] } *
"""
    game = make_game(pgn_str)
    games_to_process = [(game, chess.WHITE)]
    findings = [{"game_idx": 0, "ply": 1, "severity": "missed"}]

    by_phase, by_clock = aggregate_phase_clock(games_to_process, findings)
    assert by_phase["opening"]["missed"] == 1
    assert by_clock["slow"]["missed"] == 1

    # Empty inputs check
    empty_phase, empty_clock = aggregate_phase_clock([], [])
    for d in (empty_phase, empty_clock):
        for b in d.values():
            assert b["moves"] == 0
            assert b["blind"] == 0
            assert b["missed"] == 0
            assert b["blind_rate"] == 0.0
