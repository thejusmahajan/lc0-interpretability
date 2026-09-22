"""
Wiring test: position_plan_facts runs LC0's line through the relational-fact composer,
surfacing PLAN-level facts (the north-star "LC0 chooses the line, facts describe it").
Uses a stub engine (no real LC0) with a canned line; leader does the live-engine smoke separately.
"""

import asyncio
import chess

from backend.training import critical_points as CP


class FakeEngine:
    """Returns a canned SAN principal variation for any position."""

    def __init__(self, pv_san: str):
        self.pv_san = pv_san
        self.calls = 0

    async def analyze(self, fen, multipv=1, nodes=None, time_limit=2.0):
        self.calls += 1
        return {"evaluation": 0, "best_moves": [{"move": "a1a1", "san": "?", "score": 0}],
                "pv_lines": [self.pv_san], "nodes": nodes or 0}


def _all_plan_texts(res):
    texts = []
    for step in res.get("plan_facts", []):
        for c in (step.get("creates") or []) + (step.get("removes") or []):
            if isinstance(c, dict) and c.get("text"):
                texts.append(c["text"])
    return texts


def test_position_plan_facts_surfaces_the_plan():
    """LC0's line (canned) — the Steinitz Nc6 knight tour — must produce plan-level facts
    via relational_facts, including the defender-removal when the knight captures on e7.
    Fails if the engine's line is not fed through the composer."""
    fen = "2rq3r/1b1nbk2/p3p1p1/1p1pPp1p/1P1N1P2/PN1PB3/4Q1PP/2R2RK1 w - - 4 23"
    line = "Na5 Ba8 Rxc8 Qxc8 Rc1 Qb8 Nac6 Qe8 Nxe7"
    eng = FakeEngine(line)
    res = asyncio.run(CP.position_plan_facts(fen, chess.WHITE, eng, nodes=1))

    assert res["line_san"] == line
    assert res["line_uci"], "the SAN line must convert to UCIs"
    texts = _all_plan_texts(res)
    assert any("removes defender" in t for t in texts), \
        "the plan should surface the Nxe7 defender-removal from LC0's own line"


def test_position_plan_facts_engine_unavailable():
    """Empty PV (mock engine) -> no crash, plan_facts empty, note set."""
    eng = FakeEngine("")
    res = asyncio.run(CP.position_plan_facts(chess.STARTING_FEN, chess.WHITE, eng, nodes=1))
    assert res["plan_facts"] == []
    assert res.get("note") == "engine_unavailable"
