"""C1 gate: hidden-gem funnel order, BT3 budget, mock-mode skip, schema."""

import anyio
import chess

from backend.training import gems

# Distinct real positions (distinct EPDs).
FEN_A = chess.Board().fen()  # startpos
FEN_B = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"  # after 1.e4
FEN_C = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"  # after 1.d4
FEN_D = "rnbqkbnr/pppppppp/8/8/2P5/8/PP1PPPPP/RNBQKBNR b KQkq - 0 1"  # after 1.c4

GEM_POLICY = [
    {"uci": "e7e5", "san": "e5", "p": 0.50},
    {"uci": "c7c5", "san": "c5", "p": 0.20},
]
WEAK_POLICY = [
    {"uci": "e7e5", "san": "e5", "p": 0.10},  # below gem_top_prior (0.35)
    {"uci": "c7c5", "san": "c5", "p": 0.09},
]
# Concentrated on 4 squares -> top4_mass = 1.0 >= 0.45
GEM_SALIENCY = {"e4": 1.0, "d5": 0.8, "e5": 0.6, "f5": 0.5}


class FakeEngine:
    """Canned per-FEN responses with call counting."""

    def __init__(self, policies, evals, pv="e5 Nf3"):
        self.policies = policies
        self.evals = evals
        self.pv = pv
        self.policy_calls = []
        self.analyze_calls = []

    async def get_policy_distribution(self, fen, nodes=1):
        self.policy_calls.append(fen)
        return self.policies[fen]

    async def analyze(self, fen, depth=None, multipv=1, time_limit=None, nodes=None):
        self.analyze_calls.append((fen, multipv, time_limit))
        return {"evaluation": self.evals[fen], "pv_lines": [self.pv], "wdl": None}


class FakeVision:
    def __init__(self, saliency=GEM_SALIENCY):
        self.saliency = saliency
        self.calls = []

    def saliency_absolute(self, fen):
        self.calls.append(fen)
        return dict(self.saliency)


def run(coro):
    return anyio.run(lambda: coro)


def test_funnel_order_policy_gate_blocks_engine_and_bt3():
    """A fen failing the policy gate must trigger neither analyze nor BT3."""
    engine = FakeEngine(policies={FEN_A: WEAK_POLICY, FEN_B: GEM_POLICY},
                        evals={FEN_B: 10})
    vision = FakeVision()
    result = run(gems.scan_for_gems([FEN_A, FEN_B], engine, vision))

    assert FEN_A not in [c[0] for c in engine.analyze_calls]
    assert FEN_A not in vision.calls
    assert [g["fen"] for g in result] == [FEN_B]


def test_quiet_gate_blocks_bt3():
    """A loud position passes policy but must not spend a BT3 forward."""
    engine = FakeEngine(policies={FEN_A: GEM_POLICY}, evals={FEN_A: 300})
    vision = FakeVision()
    result = run(gems.scan_for_gems([FEN_A], engine, vision))

    assert result == []
    assert vision.calls == []
    # exactly one analyze: the quiet-gate probe; no confirmation search
    assert len(engine.analyze_calls) == 1


def test_mock_mode_skips_without_engine_calls():
    engine = FakeEngine(policies={FEN_A: []}, evals={})
    vision = FakeVision()
    result = run(gems.scan_for_gems([FEN_A], engine, vision))

    assert result == []
    assert engine.analyze_calls == []
    assert vision.calls == []


def test_max_bt3_budget_respected():
    fens = [FEN_A, FEN_B, FEN_C, FEN_D]
    engine = FakeEngine(policies={f: GEM_POLICY for f in fens},
                        evals={f: 0 for f in fens})
    vision = FakeVision()
    result = run(gems.scan_for_gems(fens, engine, vision, max_bt3=2))

    assert len(vision.calls) == 2
    assert len(result) == 2
    # the scan stopped: fens beyond the budget saw no engine work at all
    assert set(engine.policy_calls) == {FEN_A, FEN_B}


def test_dedupe_by_epd():
    """Same position with different move counters scans once."""
    fen_dup = chess.Board().fen().replace(" 0 1", " 5 20")
    engine = FakeEngine(policies={FEN_A: GEM_POLICY, fen_dup: GEM_POLICY},
                        evals={FEN_A: 0, fen_dup: 0})
    vision = FakeVision()
    result = run(gems.scan_for_gems([FEN_A, fen_dup], engine, vision))

    assert len(result) == 1
    assert len(vision.calls) == 1


def test_output_schema():
    engine = FakeEngine(policies={FEN_A: GEM_POLICY}, evals={FEN_A: 12})
    vision = FakeVision()
    result = run(gems.scan_for_gems([FEN_A], engine, vision))

    assert len(result) == 1
    g = result[0]
    assert set(g.keys()) == {
        "fen", "side_to_move", "policy", "saliency", "gem_stats",
        "solution_uci", "alt_solution_ucis", "solution_san", "pv_san",
        "eval_cp", "motifs",
    }
    assert g["side_to_move"] == "white"
    assert g["solution_uci"] == "e7e5"
    assert g["solution_san"] == "e5"
    assert g["eval_cp"] == 12
    assert g["pv_san"] == ["e5", "Nf3"]
    assert g["gem_stats"]["gem"] is True
    # alt solutions come from metrics.alt_solutions (margin 0.05 around 0.50)
    assert g["alt_solution_ucis"] == ["e7e5"]
    assert isinstance(g["motifs"], list)


def test_gem_candidates_from_profile():
    profile = {"findings": [{"fen_before": FEN_A}, {"fen_before": FEN_B}, {}]}
    assert gems.gem_candidates_from_profile(profile) == [FEN_A, FEN_B]
    assert gems.gem_candidates_from_profile(None) == []
    assert gems.gem_candidates_from_profile({}) == []
