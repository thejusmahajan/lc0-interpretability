"""Epoch III R1 — variation-tree builder (leader rewrite).

Guards the two things Gemini's version got wrong: the tree must root SHALLOW and
actually branch (not collapse to one deep-tabiya node), and `critical` must be
driven by real blindness (profile findings), not by move-inconsistency.
"""
import chess
import pytest

from backend.training import select_repertoire as sr
from backend.training import openings, store


class MockEngine:
    """Uniform sound eval + drawish WDL (=> low complexity) unless overridden
    per-fen. eval is a plain int (real LC0 shape)."""

    def __init__(self, eval_by_fen=None, wdl=(333, 333, 334), best_gap=0,
                 policy_by_fen=None):
        self.eval_by_fen = eval_by_fen or {}
        self.wdl = list(wdl)
        self.best_gap = best_gap
        self.policy_by_fen = policy_by_fen or {}

    async def analyze(self, fen, depth=None, multipv=1, time_limit=None, nodes=None):
        ev = self.eval_by_fen.get(fen, 15)
        return {
            "evaluation": ev,
            "wdl": self.wdl,
            "best_moves": [{"move": "a1a1", "score": ev},
                           {"move": "b1b1", "score": ev - self.best_gap}],
        }

    async def get_policy_distribution(self, fen, nodes=1):
        return self.policy_by_fen.get(fen, [])


def _stub_eco(monkeypatch, eco, uci_moves):
    """Stub the openings trie so `eco` resolves to a shallow tabiya."""
    board = chess.Board()
    for u in uci_moves:
        board.push_uci(u)
    seq = tuple(uci_moves)
    monkeypatch.setattr(openings, "_openings_trie", {seq: {"eco": eco, "name": eco}})
    monkeypatch.setattr(openings, "_tabiya_fens", {(eco, eco): board.fen()})
    monkeypatch.setattr(openings, "_loaded", True)
    # _find_eco_line calls openings._load_openings(); make it a no-op
    monkeypatch.setattr(openings, "_load_openings", lambda: None)


def _epd_after(ucis):
    b = chess.Board()
    for u in ucis:
        b.push_uci(u)
    return b


def _game(moves_san):
    return f'[White "Opp"]\n[Black "Me"]\n\n{moves_san} *'


@pytest.mark.anyio
async def test_tree_roots_shallow_and_branches(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    _stub_eco(monkeypatch, "B00", ["e2e4"])  # tabiya = after 1.e4 (ply 1)

    pgn = "\n\n".join([
        _game("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"),
        _game("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"),
        _game("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"),
        _game("1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5"),
        _game("1. e4 c5 2. Nf3 d6"),
    ])

    tree = await sr.build_repertoire_tree(
        eco="B00", color="black", pgn_path_or_text=pgn,
        player_name="Me", engine=MockEngine(), min_games=1, max_depth=8)

    nodes = tree["nodes"]
    assert tree["n_games"] == 5
    # roots at the initial position, NOT the deep tabiya
    assert tree["root_fen"] == chess.Board().fen()
    root = next(n for n in nodes if n["parent"] is None)
    assert root["ply"] == 0
    # a real, branched tree — not the 1-node collapse
    assert len(nodes) >= 4
    assert max(n["ply"] for n in nodes) > tree["tabiya_ply"]

    # linkage is consistent in both directions
    ids = {n["id"] for n in nodes}
    for n in nodes:
        if n["parent"] is not None:
            assert n["parent"] in ids
        for c in n["children"]:
            assert c in ids
            assert next(cn for cn in nodes if cn["id"] == c)["parent"] == n["id"]

    # the user's first move is e5 (played 4x vs c5 1x), and opponent replies
    # after it are frequency-weighted and sum to 1.0
    e5_node = next(n for n in nodes
                   if n.get("user_move", {}).get("uci") == "e7e5")
    assert e5_node["is_user_node"]
    reps = e5_node["opponent_replies"]
    assert sum(r["pct"] for r in reps) == pytest.approx(1.0)


@pytest.mark.anyio
async def test_blind_findings_mark_node_critical(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    _stub_eco(monkeypatch, "B00", ["e2e4"])

    pgn = "\n\n".join([_game("1. e4 e5 2. Nf3 Nc6")] * 4)
    # the user is blind at the position after 1.e4 e5 2.Nf3 (their Nc6 node)
    nc6_fen = _epd_after(["e2e4", "e7e5", "g1f3"]).fen()
    # findings carry the game identity (as real findings do) so they scope to
    # this tree's games; the synthetic games are White "Opp" / Black "Me".
    G = {"white": "Opp", "black": "Me", "date": "????.??.??", "result": "*"}
    profile = {"findings": [
        {"fen_before": nc6_fen, "severity": "blind", "game": G},
        {"fen_before": nc6_fen, "severity": "blind", "game": G},
        {"fen_before": nc6_fen, "severity": "blind", "game": G},
    ]}

    tree = await sr.build_repertoire_tree(
        eco="B00", color="black", pgn_path_or_text=pgn, player_name="Me",
        engine=MockEngine(), profile=profile, min_games=1, max_depth=8)

    nc6_node = next(n for n in tree["nodes"]
                    if n.get("user_move", {}).get("uci") == "b8c6")
    assert nc6_node["user_blind_rate"] == pytest.approx(0.75)  # 3 blind / 4 games
    assert nc6_node["critical"] is True
    assert nc6_node["critical_reason"] == "blind_rate"


@pytest.mark.anyio
async def test_blind_findings_from_other_games_ignored(monkeypatch, tmp_path):
    """Audit F5: blind findings at the same EPD but from a DIFFERENT game (a
    transposition from another opening, not in this tree) must NOT inflate the
    node's blind_rate. Without scoping these 3 would give 0.75 -> critical."""
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    _stub_eco(monkeypatch, "B00", ["e2e4"])
    pgn = "\n\n".join([_game("1. e4 e5 2. Nf3 Nc6")] * 4)
    nc6_fen = _epd_after(["e2e4", "e7e5", "g1f3"]).fen()
    other = {"white": "SomeoneElse", "black": "Me", "date": "2020.01.01", "result": "1-0"}
    profile = {"findings": [
        {"fen_before": nc6_fen, "severity": "blind", "game": other},
        {"fen_before": nc6_fen, "severity": "blind", "game": other},
        {"fen_before": nc6_fen, "severity": "blind", "game": other},
    ]}
    tree = await sr.build_repertoire_tree(
        eco="B00", color="black", pgn_path_or_text=pgn, player_name="Me",
        engine=MockEngine(), profile=profile, min_games=1, max_depth=8)
    nc6_node = next(n for n in tree["nodes"]
                    if n.get("user_move", {}).get("uci") == "b8c6")
    assert nc6_node["user_blind_rate"] == 0.0     # other-game findings ignored
    assert nc6_node["critical"] is False


@pytest.mark.anyio
async def test_move_inconsistency_alone_is_not_critical(monkeypatch, tmp_path):
    """The semantic fix: a node where the user plays many DIFFERENT moves must
    NOT be critical without real blindness. Gemini's blind_rate = 1 - chosen/total
    would mark this critical (0.6); findings-based blind_rate is 0."""
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    _stub_eco(monkeypatch, "B00", ["e2e4"])

    # after 1.e4 black plays e5 x2, c5 x2, e6 x1 -> chosen count 2 / total 5,
    # so the old proxy would be 1 - 2/5 = 0.6 (critical). No findings -> new is 0.
    pgn = "\n\n".join([
        _game("1. e4 e5"), _game("1. e4 e5"),
        _game("1. e4 c5"), _game("1. e4 c5"),
        _game("1. e4 e6"),
    ])
    tree = await sr.build_repertoire_tree(
        eco="B00", color="black", pgn_path_or_text=pgn, player_name="Me",
        engine=MockEngine(), profile=None, min_games=1, max_depth=6)

    ply1 = next(n for n in tree["nodes"] if n["ply"] == 1)
    assert ply1["is_user_node"]
    assert ply1["user_blind_rate"] == 0.0
    assert ply1["critical"] is False


@pytest.mark.anyio
async def test_sharp_position_marks_critical_complexity(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    _stub_eco(monkeypatch, "B00", ["e2e4"])

    pgn = "\n\n".join([_game("1. e4 e5 2. Nf3 Nc6")] * 3)
    # decisive WDL + a wide best-vs-2nd gap -> high tactical_complexity
    engine = MockEngine(wdl=(900, 50, 50), best_gap=200)

    tree = await sr.build_repertoire_tree(
        eco="B00", color="black", pgn_path_or_text=pgn, player_name="Me",
        engine=engine, profile=None, min_games=1, max_depth=8)

    crit = [n for n in tree["nodes"] if n.get("critical")]
    assert crit, "expected at least one critical node from sharpness"
    assert any(n["critical_reason"] == "complexity" for n in crit)
    # none should be blind_rate (no findings supplied)
    assert all(n["critical_reason"] != "blind_rate" for n in crit)
