"""Epoch III R2 — repertoire drills from variation trees + SRS wiring."""
import chess
import pytest

from backend.training import drills, attempts, store


def _fen_after(ucis):
    b = chess.Board()
    for u in ucis:
        b.push_uci(u)
    return b.fen()


def _sample_tree(explanation=None):
    """White repertoire: critical root (d4) -> e6 -> non-critical Nf3 node."""
    return {
        "eco": "A40", "color": "white", "root_fen": chess.Board().fen(),
        "tabiya_ply": 1, "depth": 6, "n_games": 10,
        "nodes": [
            {
                "id": "A40-w-0001",
                "fen_before": chess.Board().fen(),
                "ply": 0, "is_user_node": True,
                "user_move": {"uci": "d2d4", "san": "d4"},
                "eval_cp": 26, "complexity": 0.3, "user_blind_rate": 0.6,
                "critical": True, "critical_reason": "blind_rate",
                "parent": None, "children": ["A40-w-0002"],
                "opponent_replies": [{"uci": "e7e6", "san": "e6", "count": 10, "pct": 1.0}],
                "explanation": explanation,
            },
            {
                "id": "A40-w-0002",
                "fen_before": _fen_after(["d2d4", "e7e6"]),
                "ply": 2, "is_user_node": True,
                "user_move": {"uci": "g1f3", "san": "Nf3"},
                "eval_cp": 30, "complexity": 0.2, "user_blind_rate": 0.0,
                "critical": False,
                "parent": "A40-w-0001", "children": [],
                "opponent_replies": [],
            },
        ],
    }


def test_only_critical_nodes_become_drills():
    ds = drills.build_repertoire_drills(_sample_tree())
    assert len(ds) == 1
    d = ds[0]
    assert d["source"] == "repertoire"
    assert d["solution_uci"] == "d2d4"
    assert d["origin"]["critical_reason"] == "blind_rate"


def test_drill_line_walks_main_line_and_completes_via_check_attempt():
    d = drills.build_repertoire_drills(_sample_tree())[0]
    # line follows the most-played branch: d4, e6 (opp), Nf3 (next user move)
    assert d["line_uci"] == ["d2d4", "e7e6", "g1f3"]

    # ply 0: correct move -> reply auto-played, not complete
    v0 = drills.check_attempt(d, 0, "d2d4")
    assert v0["correct"] and not v0["complete"] and v0["reply_uci"] == "e7e6"
    # ply 2: final user move -> complete
    v2 = drills.check_attempt(d, 2, "g1f3")
    assert v2["correct"] and v2["complete"]
    # a wrong first move fails
    assert drills.check_attempt(d, 0, "e2e4")["correct"] is False


def test_drill_id_is_stable_across_rebuilds():
    id1 = drills.build_repertoire_drills(_sample_tree())[0]["id"]
    # a rebuilt tree with DIFFERENT node ids but the same positions
    t2 = _sample_tree()
    for i, n in enumerate(t2["nodes"]):
        n["id"] = f"REBUILT-{i}"
    id2 = drills.build_repertoire_drills(t2)[0]["id"]
    assert id1 == id2  # keyed by position (EPD) + color, not node id


def test_castling_alt_spelling_accepted():
    fen = "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"
    tree = {
        "eco": "A00", "color": "white", "nodes": [{
            "id": "n1", "fen_before": fen, "ply": 0, "is_user_node": True,
            "user_move": {"uci": "e1g1", "san": "O-O"},
            "critical": True, "critical_reason": "eval_swing",
            "opponent_replies": [], "children": [],
        }],
    }
    d = drills.build_repertoire_drills(tree)[0]
    assert set(d["alt_solution_ucis"]) >= {"e1g1", "e1h1"}
    # entering the LC0 king-takes-rook spelling is accepted
    assert drills.check_attempt(d, 0, "e1h1")["correct"] is True


def test_explanation_carried_into_reveal():
    d = drills.build_repertoire_drills(_sample_tree(explanation="Grab the center."))[0]
    assert d["reveal"]["explanation"] == "Grab the center."
    d2 = drills.build_repertoire_drills(_sample_tree())[0]
    assert d2["reveal"]["explanation"] is None


def test_drill_set_envelope_shape():
    s = drills.build_repertoire_drill_set(_sample_tree())
    assert s["source"] == "repertoire" and s["eco"] == "A40" and s["color"] == "white"
    assert isinstance(s["drills"], list) and len(s["drills"]) == 1
    assert s["id"].startswith("rep-A40-white-")


def test_srs_schedules_repertoire_drill(monkeypatch, tmp_path):
    import datetime
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    d = drills.build_repertoire_drills(_sample_tree())[0]

    now = datetime.datetime(2026, 7, 21, 12, 0, 0)
    # a correct attempt climbs the ladder and schedules a future review
    e1 = attempts.record_attempt("set-rep", d, correct=True, now=now)
    assert e1["reps"] == 1 and e1["step"] == 1 and e1["lapses"] == 0
    srs = attempts.load_srs()
    assert d["id"] in srs and srs[d["id"]]["due"] > now.isoformat()

    # a failed attempt resets to step 0 and counts a lapse
    e2 = attempts.record_attempt("set-rep", d, correct=False, now=now)
    assert e2["step"] == 0 and e2["lapses"] == 1
    # it surfaces in the due queue once its (short) interval elapses
    future = now + datetime.timedelta(days=2)
    due_ids = [e["drill_id"] for e in attempts.due_drills(now=future)]
    assert d["id"] in due_ids
