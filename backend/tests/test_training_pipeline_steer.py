import pytest
import chess.pgn
from backend.training.pipeline import run_diagnosis
from backend.training import store, metrics
import dataclasses

class MockEngine:
    def __init__(self, evaluate_val=50, evaluate_played=50):
        self.analyze_calls = 0
        self.evaluate_val = evaluate_val
        self.evaluate_played = evaluate_played

    async def get_policy_distribution(self, fen, nodes=None):
        return [
            {"uci": "e2e4", "san": "e4", "p": 0.5},
            {"uci": "d2d4", "san": "d4", "p": 0.3},
        ]

    async def analyze(self, fen, depth=None, multipv=1, time_limit=None, nodes=None):
        self.analyze_calls += 1
        return {
            "evaluation": {"type": "cp", "value": self.evaluate_val},
            "wdl": [333, 333, 334],
            "best_moves": [{"move": "e2e4", "score": self.evaluate_val}, {"move": "d2d4", "score": self.evaluate_val - 10}],
            "pv_lines": ["e2e4"]
        }

class MockVision:
    def saliency_absolute(self, fen):
        return {"e4": 1.0}

@pytest.mark.anyio
async def test_steer_budget_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    pgn_text = '[White "TestPlayer"]\n[Black "Opponent"]\n\n1. e4 e5 *'
    engine = MockEngine()
    vision = MockVision()
    orig_budget = metrics.DEFAULT_CONFIG.steer_search_budget
    object.__setattr__(metrics.DEFAULT_CONFIG, "steer_search_budget", 1)

    try:
        await run_diagnosis("test_job_1", pgn_text, "TestPlayer", engine, vision)

        profile = store.load_profile()
        assert profile is not None
        assert profile["steer_budget_exhausted"] is True
        assert engine.analyze_calls == 1
    finally:
        object.__setattr__(metrics.DEFAULT_CONFIG, "steer_search_budget", orig_budget)

@pytest.mark.anyio
async def test_opening_sidelines_excluded(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    pgn_text = '[White "TestPlayer"]\n[Black "Opponent"]\n\n1. e4 e5 *'
    
    class DivergenceEngine(MockEngine):
        async def get_policy_distribution(self, fen, nodes=None):
            # Best is d4, played is e4. Divergence severity is blind.
            return [
                {"uci": "d2d4", "san": "d4", "p": 0.99},
                {"uci": "e2e4", "san": "e4", "p": 0.00},
            ]

    # Use small eval swing so it's not confirmed.
    engine = DivergenceEngine(evaluate_val=10)
    vision = MockVision()
    orig_budget = metrics.DEFAULT_CONFIG.steer_search_budget
    orig_ply = metrics.DEFAULT_CONFIG.opening_max_ply
    
    object.__setattr__(metrics.DEFAULT_CONFIG, "steer_search_budget", 100)
    try:
        await run_diagnosis("test_job_2", pgn_text, "TestPlayer", engine, vision)

        profile = store.load_profile()
        assert profile is not None
        assert profile["opening_sidelines_excluded"] == 1
        assert len(profile["findings"]) == 0

        object.__setattr__(metrics.DEFAULT_CONFIG, "opening_max_ply", 0)
        
        await run_diagnosis("test_job_3", pgn_text, "TestPlayer", engine, vision)
        profile = store.load_profile()
        assert profile["opening_sidelines_excluded"] == 0
        assert len(profile["findings"]) == 1
    finally:
        object.__setattr__(metrics.DEFAULT_CONFIG, "steer_search_budget", orig_budget)
        object.__setattr__(metrics.DEFAULT_CONFIG, "opening_max_ply", orig_ply)


# A steer finding is suppressed at a lost node because steer_candidates drops
# every candidate below the steer_min_eval_cp floor, leaving nothing playable.
# To make THAT the thing under test (not some unrelated short-circuit) the test
# below pins two knobs:
#   * the eval is a plain int, the real LC0 shape. A dict makes eval_cp_number
#     return None -> candidates never build -> a vacuous pass that survives even
#     if the floor is deleted.
#   * steer_highlight_complexity is set to 0, so ANY playable node emits via the
#     complexity branch. The loss floor is then the ONLY thing that can suppress
#     the finding -> deleting the floor makes the losing assertion fail.
# The sound-eval run is the positive control proving the node is genuinely live.
class IntEvalEngine(MockEngine):
    async def get_policy_distribution(self, fen, nodes=None):
        return [
            {"uci": "e2e4", "san": "e4", "p": 0.6},
            {"uci": "d2d4", "san": "d4", "p": 0.4},
        ]

    async def analyze(self, fen, depth=None, multipv=1, time_limit=None, nodes=None):
        self.analyze_calls += 1
        return {
            "evaluation": self.evaluate_val,  # plain int == real LC0 shape
            "wdl": [333, 333, 334],
            "best_moves": [{"move": "e2e4", "score": self.evaluate_val},
                           {"move": "d2d4", "score": self.evaluate_val - 10}],
            "pv_lines": ["e2e4"],
        }


_STEER_PGN = '[White "TestPlayer"]\n[Black "Opponent"]\n\n1. e4 e5 *'


async def _run_steer_pass(monkeypatch, tmp_path, evaluate_val):
    """Run one diagnosis over _STEER_PGN with the highlight threshold pinned to
    0 (so any *playable* node emits via the complexity branch) and return the
    resulting steer_findings. Each call gets its own tmp_path from pytest, which
    keeps the on-disk steer cache from leaking one run's analysis into another."""
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    cfg = metrics.DEFAULT_CONFIG
    orig_hi = cfg.steer_highlight_complexity
    orig_budget = cfg.steer_search_budget
    object.__setattr__(cfg, "steer_highlight_complexity", 0.0)
    object.__setattr__(cfg, "steer_search_budget", 100)
    try:
        await run_diagnosis("job_steer", _STEER_PGN, "TestPlayer",
                            IntEvalEngine(evaluate_val=evaluate_val), MockVision())
        profile = store.load_profile()
        assert profile is not None
        return profile.get("steer_findings", [])
    finally:
        object.__setattr__(cfg, "steer_highlight_complexity", orig_hi)
        object.__setattr__(cfg, "steer_search_budget", orig_budget)


@pytest.mark.anyio
async def test_losing_node_emits_no_steer_finding(monkeypatch, tmp_path):
    # Best eval (-300 mover POV) sits below the -60 floor -> steer_candidates
    # finds nothing playable -> no steer finding. With highlight pinned to 0 the
    # floor is the ONLY thing that can suppress emission here, so deleting it
    # would make this assertion fail. The paired positive control below proves
    # the node is genuinely live (not silently short-circuited).
    findings = await _run_steer_pass(monkeypatch, tmp_path, evaluate_val=-300)
    assert len(findings) == 0


@pytest.mark.anyio
async def test_sound_node_emits_steer_finding(monkeypatch, tmp_path):
    # Positive control for test_losing_node_emits_no_steer_finding: the SAME node
    # with a sound eval (>= floor) is playable and DOES emit under highlight=0.
    findings = await _run_steer_pass(monkeypatch, tmp_path, evaluate_val=50)
    assert len(findings) >= 1


@pytest.mark.anyio
async def test_node_budget_is_forwarded_to_engine(monkeypatch, tmp_path):
    # Guard for the GPU node-limit path: when confirm_played_nodes is configured,
    # the TS2 steering search must pass nodes=<budget> to engine.analyze (so a
    # fast backend does a fixed-depth search instead of a fixed-time one). Deleting
    # `nodes=...` from the pipeline call makes the recorded value None -> fails.
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    seen_nodes = []

    class RecordingEngine(IntEvalEngine):
        async def analyze(self, fen, depth=None, multipv=1, time_limit=None, nodes=None):
            seen_nodes.append(nodes)
            return await super().analyze(fen, depth, multipv, time_limit, nodes)

    cfg = metrics.DEFAULT_CONFIG
    saved = (cfg.steer_highlight_complexity, cfg.steer_search_budget, cfg.confirm_played_nodes)
    object.__setattr__(cfg, "steer_highlight_complexity", 0.0)
    object.__setattr__(cfg, "steer_search_budget", 100)
    object.__setattr__(cfg, "confirm_played_nodes", 55000)
    try:
        await run_diagnosis("job_nodes", _STEER_PGN, "TestPlayer",
                            RecordingEngine(evaluate_val=50), MockVision())
        # at least one TS2 search ran, and it carried the configured node budget
        assert 55000 in seen_nodes, f"node budget not forwarded; saw {seen_nodes}"
    finally:
        (object.__setattr__(cfg, "steer_highlight_complexity", saved[0]),
         object.__setattr__(cfg, "steer_search_budget", saved[1]),
         object.__setattr__(cfg, "confirm_played_nodes", saved[2]))

