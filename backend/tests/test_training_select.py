"""TS3 gate: style-rooted tactical repertoire — ingrained openings mined,
classified kept/repaired/dry, tinted via steer_candidates.

Mock engine returns wdl AND evaluation as a real int or "M5" string (not a
dict), exactly matching the LC0 wire format.
"""

import anyio
import chess

from backend.training import select_repertoire as sr
from backend.training import openings, metrics


START_FEN = chess.Board().fen()


def run(coro):
    return anyio.run(lambda: coro)


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

def _make_profile(
    by_opening: dict,
    findings: list | None = None,
    steer_summary: dict | None = None,
    by_motif: dict | None = None,
):
    return {
        "aggregates": {
            "by_opening": by_opening,
            "by_motif": by_motif or {},
        },
        "findings": findings or [],
        "steer_summary": steer_summary or {},
    }


class MockEngine:
    """Mock engine whose analyze returns wdl AND evaluation as int/str."""

    def __init__(self, eval_by_fen=None, wdl=(400, 300, 300),
                 policy_by_fen=None, best_moves_by_fen=None):
        self.eval_by_fen = eval_by_fen or {}
        self.wdl = list(wdl)
        self.policy_by_fen = policy_by_fen or {}
        self.best_moves_by_fen = best_moves_by_fen or {}
        self.analyze_calls = []

    async def analyze(self, fen, depth=None, multipv=1, time_limit=None, nodes=None):
        self.analyze_calls.append(fen)
        ev = self.eval_by_fen.get(fen, 0)
        bm = self.best_moves_by_fen.get(fen, [])
        return {"evaluation": ev, "pv_lines": [], "wdl": self.wdl,
                "best_moves": bm}

    async def get_policy_distribution(self, fen, nodes=1):
        return self.policy_by_fen.get(fen, [])


def _stub_openings(monkeypatch, eco_lines):
    """eco_lines: dict eco -> {"name", "uci_moves", "fen"}"""
    # Populate the trie directly
    trie = {}
    fens = {}
    for eco, info in eco_lines.items():
        seq = tuple(info["uci_moves"])
        trie[seq] = {"eco": eco, "name": info["name"]}
        fens[(eco, info["name"])] = info["fen"]

    monkeypatch.setattr(openings, "_openings_trie", trie)
    monkeypatch.setattr(openings, "_tabiya_fens", fens)
    monkeypatch.setattr(openings, "_loaded", True)


# -----------------------------------------------------------------------
# Test: leaky ECO → origin:"repaired"
# -----------------------------------------------------------------------

def test_leaky_eco_gets_repaired(monkeypatch):
    """A profile whose by_opening has a leaky ECO (Track A findings in it)
    should produce a recommendation with origin:"repaired"."""
    fen_after_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    eco_lines = {
        "B00": {
            "name": "King's Pawn Opening",
            "uci_moves": ["e2e4"],
            "fen": fen_after_e4,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={"B00": {"moves": 10, "missed": 2, "blind": 1, "blind_rate": 0.1}},
        findings=[{"opening": {"eco": "B00", "name": "King's Pawn Opening"}}],
        steer_summary={"B00": {"moves": 10, "sharp_moves": 1, "mean_complexity": 0.35}},
    )
    # Engine: tabiya is sound (+10cp), sharp (40/30/30 wdl), no policy → no tint
    engine = MockEngine(eval_by_fen={fen_after_e4: 10})

    rep = run(sr.build_repertoire(profile, "white", engine))
    assert len(rep["recommendations"]) == 1
    rec = rep["recommendations"][0]
    assert rec["origin"] == "repaired"
    assert rec["eco"] == "B00"
    assert rec["eval_cp"] == 10


# -----------------------------------------------------------------------
# Test: tinted rec with eval_loss_cp <= steer_max_loss_cp
# -----------------------------------------------------------------------

def test_tinted_rec_bounded_eval_loss(monkeypatch):
    """A mocked engine yielding a Tal move should produce a tinted rec whose
    eval_loss_cp <= steer_max_loss_cp."""
    fen_tab = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    # After e4 e5
    fen_after_e5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    # After e4 c5
    fen_after_c5 = "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"

    eco_lines = {
        "C00": {
            "name": "French Opening",
            "uci_moves": ["e2e4"],
            "fen": fen_tab,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={"C00": {"moves": 20, "missed": 0, "blind": 0, "blind_rate": 0.0}},
        steer_summary={"C00": {"moves": 20, "sharp_moves": 0, "mean_complexity": 0.30}},
    )

    # Policy at tabiya: two candidate moves
    policy_tab = [
        {"uci": "e7e5", "san": "e5", "p": 0.5},
        {"uci": "c7c5", "san": "c5", "p": 0.3},
    ]

    # After e5: calm (complexity low) — the "best" move
    # After c5: sharp (complexity high) — the "Tal" move
    # Both well within eval loss bound
    best_moves_calm = [
        {"move": "d2d4", "score": 30},
        {"move": "g1f3", "score": 25},
    ]
    best_moves_sharp = [
        {"move": "d2d4", "score": 50},   # big gap → narrow
        {"move": "g1f3", "score": -100},  # = 150cp gap → narrowness 0.75
    ]
    # Policy after c5: saving reply has LOW prior → policy trap fires
    policy_after_c5 = [
        {"uci": "d2d4", "p": 0.08},  # sole saving reply, low prior
        {"uci": "g1f3", "p": 0.4},
    ]
    policy_after_e5 = [
        {"uci": "d2d4", "p": 0.5},
        {"uci": "g1f3", "p": 0.3},
    ]

    engine = MockEngine(
        eval_by_fen={
            fen_tab: 10,           # tabiya sound
            fen_after_e5: 15,      # after e5: +15 (best)
            fen_after_c5: -10,     # after c5: -10 (slight cost but within bound)
        },
        wdl=(400, 300, 300),       # sharp (30% draws)
        policy_by_fen={
            fen_tab: policy_tab,
            fen_after_e5: policy_after_e5,
            fen_after_c5: policy_after_c5,
        },
        best_moves_by_fen={
            fen_after_e5: best_moves_calm,
            fen_after_c5: best_moves_sharp,
        },
    )

    rep = run(sr.build_repertoire(profile, "white", engine))
    assert len(rep["recommendations"]) >= 1
    rec = rep["recommendations"][0]
    # Must be tinted since the Tal move (c5) has higher complexity than e5
    assert rec["origin"] == "tinted"
    assert rec["tint_move"] is not None
    assert rec["eval_loss_cp"] is not None
    assert rec["eval_loss_cp"] <= metrics.DEFAULT_CONFIG.steer_max_loss_cp


# -----------------------------------------------------------------------
# Test: no rec has eval_cp below the floor
# -----------------------------------------------------------------------

def test_no_rec_below_eval_floor(monkeypatch):
    """Recommendations must not have an eval worse than -sound_eval_cp
    for the requested color."""
    fen_good = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    fen_bad = "rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1"

    eco_lines = {
        "B00": {
            "name": "King Pawn",
            "uci_moves": ["e2e4"],
            "fen": fen_good,
        },
        "D00": {
            "name": "Queen Pawn",
            "uci_moves": ["d2d4"],
            "fen": fen_bad,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={
            "B00": {"moves": 10, "missed": 0, "blind": 0, "blind_rate": 0.0},
            "D00": {"moves": 10, "missed": 0, "blind": 0, "blind_rate": 0.0},
        },
    )

    # D00's tabiya is -200 white POV → unsound for white (pov_cp = -200 < -50)
    engine = MockEngine(eval_by_fen={fen_good: 10, fen_bad: -200})

    rep = run(sr.build_repertoire(profile, "white", engine))
    for rec in rep["recommendations"]:
        pov_cp = rec["eval_cp"] if "white" == "white" else -rec["eval_cp"]
        assert pov_cp >= -metrics.DEFAULT_CONFIG.sound_eval_cp, \
            f"rec {rec['eco']} has pov_cp {pov_cp} below floor"
    # D00 should be filtered out
    ecos = [r["eco"] for r in rep["recommendations"]]
    assert "D00" not in ecos
    assert "B00" in ecos


# -----------------------------------------------------------------------
# Test: black repertoire filters by color
# -----------------------------------------------------------------------

def test_black_repertoire_color_filter(monkeypatch):
    """Only ECOs whose line is black-owned appear in a black repertoire."""
    fen_w = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    fen_b = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"

    eco_lines = {
        "B00": {
            "name": "King Pawn",
            "uci_moves": ["e2e4"],            # white-owned (1 move)
            "fen": fen_w,
        },
        "C20": {
            "name": "Open Game",
            "uci_moves": ["e2e4", "e7e5"],    # black-owned (2 moves)
            "fen": fen_b,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={
            "B00": {"moves": 15, "missed": 0, "blind": 0, "blind_rate": 0.0},
            "C20": {"moves": 15, "missed": 0, "blind": 0, "blind_rate": 0.0},
        },
    )

    engine = MockEngine(eval_by_fen={fen_w: 10, fen_b: -5})

    rep = run(sr.build_repertoire(profile, "black", engine))
    ecos = [r["eco"] for r in rep["recommendations"]]
    assert "C20" in ecos
    assert "B00" not in ecos


# -----------------------------------------------------------------------
# Test: soundness sign handling for black
# -----------------------------------------------------------------------

def test_soundness_sign_for_black(monkeypatch):
    """White-POV +200 is UNSOUND for a black repertoire."""
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"

    eco_lines = {
        "C20": {
            "name": "Open Game",
            "uci_moves": ["e2e4", "e7e5"],
            "fen": fen,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={"C20": {"moves": 10, "missed": 0, "blind": 0, "blind_rate": 0.0}},
    )

    # +200 white POV = -200 for black → unsound
    engine = MockEngine(eval_by_fen={fen: 200})

    rep = run(sr.build_repertoire(profile, "black", engine))
    assert rep["recommendations"] == []


# -----------------------------------------------------------------------
# Test: sharpness gate (too drawish rejected)
# -----------------------------------------------------------------------

def test_sharpness_gate(monkeypatch):
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    eco_lines = {
        "B00": {
            "name": "King Pawn",
            "uci_moves": ["e2e4"],
            "fen": fen,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={"B00": {"moves": 10, "missed": 0, "blind": 0, "blind_rate": 0.0}},
    )

    # 60% draws → too drawish
    engine = MockEngine(eval_by_fen={fen: 0}, wdl=(200, 600, 200))

    rep = run(sr.build_repertoire(profile, "white", engine))
    assert rep["recommendations"] == []


# -----------------------------------------------------------------------
# Test: engine budget cap
# -----------------------------------------------------------------------

def test_engine_budget_cap(monkeypatch):
    """Engine calls must not exceed MAX_ENGINE_CALLS."""
    eco_lines = {}
    evals = {}
    by_opening = {}
    for i in range(20):
        eco = f"X{i:02d}"
        fen = f"rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 {i + 1}"
        eco_lines[eco] = {
            "name": f"Line {i}",
            "uci_moves": ["e2e4"],  # white-owned
            "fen": fen,
        }
        evals[fen] = -200  # all unsound → no early top_n break
        by_opening[eco] = {"moves": 10, "missed": 0, "blind": 0, "blind_rate": 0.0}

    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(by_opening=by_opening)
    engine = MockEngine(eval_by_fen=evals)

    rep = run(sr.build_repertoire(profile, "white", engine, top_n=20))
    assert rep["recommendations"] == []
    assert len(engine.analyze_calls) <= sr.MAX_ENGINE_CALLS


# -----------------------------------------------------------------------
# Test: dry classification
# -----------------------------------------------------------------------

def test_dry_eco_classification(monkeypatch):
    """An ECO with low mean_complexity and 0 tal_moves among enough moves
    is classified as 'dry'."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    eco_lines = {
        "A00": {
            "name": "Boring Opening",
            "uci_moves": ["e2e4"],
            "fen": fen,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={"A00": {"moves": 15, "missed": 0, "blind": 0, "blind_rate": 0.0}},
        steer_summary={"A00": {"moves": 10, "sharp_moves": 0, "mean_complexity": 0.15}},
    )

    engine = MockEngine(eval_by_fen={fen: 5})

    rep = run(sr.build_repertoire(profile, "white", engine))
    assert len(rep["recommendations"]) == 1
    rec = rep["recommendations"][0]
    assert rec["classification"] == "dry"
    # Without a tint, origin falls back to classification → "kept" (dry is
    # just a classification, origin is kept unless tinted or repaired)
    assert rec["origin"] == "kept"


# -----------------------------------------------------------------------
# Test: ECOs below min moves threshold are excluded
# -----------------------------------------------------------------------

def test_min_moves_threshold(monkeypatch):
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    eco_lines = {
        "B00": {
            "name": "King Pawn",
            "uci_moves": ["e2e4"],
            "fen": fen,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={"B00": {"moves": 3}},  # below REPERTOIRE_MIN_MOVES=5
    )

    engine = MockEngine(eval_by_fen={fen: 0})

    rep = run(sr.build_repertoire(profile, "white", engine))
    assert rep["recommendations"] == []
    assert len(engine.analyze_calls) == 0  # no engine calls wasted


# -----------------------------------------------------------------------
# Test: version 2 in output
# -----------------------------------------------------------------------

def test_output_version(monkeypatch):
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    eco_lines = {
        "B00": {
            "name": "King Pawn",
            "uci_moves": ["e2e4"],
            "fen": fen,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={"B00": {"moves": 10, "missed": 0, "blind": 0, "blind_rate": 0.0}},
    )

    engine = MockEngine(eval_by_fen={fen: 0})

    rep = run(sr.build_repertoire(profile, "white", engine))
    assert rep["version"] == 2
    assert rep["color"] == "white"


# -----------------------------------------------------------------------
# Test: explicitly authoritative color counts override parity
# -----------------------------------------------------------------------

def test_color_counts_override_parity(monkeypatch):
    """An ECO whose uci_moves length parity points to one color but whose
    explicit counts point to the other should use the explicit counts."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    eco_lines = {
        "B00": {
            "name": "King Pawn",
            "uci_moves": ["e2e4"],  # 1 move = parity "white"
            "fen": fen,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={
            "B00": {
                "moves": 10,
                "moves_white": 0,
                "moves_black": 10,  # >= REPERTOIRE_MIN_MOVES
                "missed": 0,
                "blind": 0,
                "blind_rate": 0.0,
            }
        },
    )

    # Engine eval is good for black (-10 cp white POV -> +10 black POV)
    engine = MockEngine(eval_by_fen={fen: -10})

    # For black, it should be included
    rep_black = run(sr.build_repertoire(profile, "black", engine))
    ecos_black = [r["eco"] for r in rep_black["recommendations"]]
    assert "B00" in ecos_black

    # For white, it should be excluded (moves_white = 0 < 5)
    # Re-mock engine with a good eval for white just to be sure it's not excluded by eval
    engine = MockEngine(eval_by_fen={fen: 10})
    rep_white = run(sr.build_repertoire(profile, "white", engine))
    ecos_white = [r["eco"] for r in rep_white["recommendations"]]
    assert "B00" not in ecos_white


# -----------------------------------------------------------------------
# Test: color count below min moves is excluded
# -----------------------------------------------------------------------

def test_color_count_below_min_moves_excluded(monkeypatch):
    """An ECO with total moves >= 5 but neither color >= 5 is excluded."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    eco_lines = {
        "B00": {
            "name": "King Pawn",
            "uci_moves": ["e2e4"],
            "fen": fen,
        },
    }
    _stub_openings(monkeypatch, eco_lines)

    profile = _make_profile(
        by_opening={
            "B00": {
                "moves": 6,          # >= REPERTOIRE_MIN_MOVES (5)
                "moves_white": 3,
                "moves_black": 3,
                "missed": 0,
                "blind": 0,
                "blind_rate": 0.0,
            }
        },
    )

    # Give it a good eval for both colors
    engine = MockEngine(eval_by_fen={fen: 10})

    rep_white = run(sr.build_repertoire(profile, "white", engine))
    ecos_white = [r["eco"] for r in rep_white["recommendations"]]
    assert "B00" not in ecos_white

    engine = MockEngine(eval_by_fen={fen: -10})
    rep_black = run(sr.build_repertoire(profile, "black", engine))
    ecos_black = [r["eco"] for r in rep_black["recommendations"]]
    assert "B00" not in ecos_black
