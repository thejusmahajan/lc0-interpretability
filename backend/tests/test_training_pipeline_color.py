import pytest
import chess.pgn
from backend.training.pipeline import run_diagnosis
from backend.training import store

class MockEngine:
    def __init__(self, evaluate_val=50):
        self.analyze_calls = 0
        self.evaluate_val = evaluate_val

    async def get_policy_distribution(self, fen, nodes=None):
        return [
            {"uci": "e2e4", "san": "e4", "p": 0.5},
            {"uci": "d2d4", "san": "d4", "p": 0.3},
        ]

    async def analyze(self, fen, depth=None, multipv=1, time_limit=None, nodes=None):
        self.analyze_calls += 1
        return {
            "evaluation": self.evaluate_val,
            "wdl": [333, 333, 334],
            "best_moves": [{"move": "e2e4", "score": self.evaluate_val}],
            "pv_lines": ["e2e4"]
        }

class MockVision:
    def saliency_absolute(self, fen):
        return {"e4": 1.0}

@pytest.mark.anyio
async def test_by_opening_color_aggregate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    # TestPlayer is playing Black
    pgn_text = '[White "Opponent"]\n[Black "TestPlayer"]\n\n1. e4 e5 2. Nf3 Nc6 *'
    engine = MockEngine()
    vision = MockVision()

    await run_diagnosis("test_job_color", pgn_text, "TestPlayer", engine, vision)

    profile = store.load_profile()
    assert profile is not None
    
    by_opening = profile["aggregates"]["by_opening"]
    
    found = False
    for eco, st in by_opening.items():
        if st["moves"] > 0:
            found = True
            assert st["moves_black"] >= 1
            assert st["moves_white"] == 0
            
    assert found
