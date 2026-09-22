import pytest
from backend.training import sac_drill, openings_sharpness


def test_sharpness_is_not_sacrifice():
    """Mutation Test 1: Sharpness (had_sharp_move) does NOT count as a sacrifice.
    select_missed_sacrifices must return ONLY findings with 'sacrifice' motif,
    never falling back to had_sharp_move or steer_findings.
    """
    mock_profile = {
        "steer_findings": [
            {
                "id": "s-001",
                "fen_before": "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
                "had_sharp_move": True,
                "steer": {"complexity": 0.8, "uci": "b8c6"},
                "best": {"complexity": 0.2, "uci": "g8f6"},
            }
        ],
        "findings": [
            {
                "id": "f-001",
                "fen_before": "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
                "motifs": ["quietMove", "advantage"],  # NO "sacrifice" motif!
            }
        ]
    }

    # 1. select_missed_sacrifices must NOT return the steer finding or non-sacrifice finding
    missed_sacs = sac_drill.select_missed_sacrifices(mock_profile)
    assert len(missed_sacs) == 0

    # 2. Steer finding with had_sharp_move=True is sharp, NOT a sacrifice
    sharp_items = [sf for sf in mock_profile["steer_findings"] if sf.get("had_sharp_move") is True]
    assert len(sharp_items) == 1


def test_real_sacrifice_selected():
    """Mutation Test 2: Real sacrifice (finding with 'sacrifice' in motifs) IS selected by select_missed_sacrifices."""
    mock_profile = {
        "findings": [
            {
                "id": "f-sac-001",
                "fen_before": "r1bqk2r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4",
                "motifs": ["sacrifice", "mating"],
                "opening": {"eco": "C50"},
                "best": {"uci": "c4f7"},
            },
            {
                "id": "f-nosac-002",
                "fen_before": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
                "motifs": ["fork"],
                "opening": {"eco": "B00"},
                "best": {"uci": "e7e5"},
            }
        ]
    }

    sacs = sac_drill.select_missed_sacrifices(mock_profile)
    assert len(sacs) == 1
    assert sacs[0]["id"] == "f-sac-001"
    assert sacs[0]["best"]["uci"] == "c4f7"

    # Test ECO filter
    sacs_c50 = sac_drill.select_missed_sacrifices(mock_profile, eco="C50")
    assert len(sacs_c50) == 1
    sacs_b00 = sac_drill.select_missed_sacrifices(mock_profile, eco="B00")
    assert len(sacs_b00) == 0


def test_openings_sharpness_splits_sharp_and_missed_sacrifices():
    """Mutation Test 3: openings_sharpness outputs sharp_positions AND missed_sacrifices separately."""
    mock_profile = {
        "findings": [
            {
                "id": "f-001",
                "opening": {"eco": "C50", "name": "Italian Game"},
                "motifs": ["sacrifice"],
            }
        ],
        "steer_findings": [
            {
                "id": "s-001",
                "opening": {"eco": "C50", "name": "Italian Game"},
                "had_sharp_move": True,
                "steer": {"complexity": 0.75, "uci": "c4f7"},
            }
        ]
    }

    res = openings_sharpness.sharpness_by_opening(mock_profile)
    c50 = next(item for item in res if item["eco"] == "C50")
    assert c50["sharp_positions"] == 1
    assert c50["missed_sacrifices"] == 1
