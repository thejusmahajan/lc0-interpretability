"""The LLM seam interlock.

THE MOTTO: the LLM is a TRANSLATOR of LC0's thoughts, never a chess reasoner.
A bad coach does more harm than no coach.

`LLM_ENABLED = False` in `backend/app.py` was a sign, not an interlock: nothing
read it. `backend/training/explanations.py` reached
`llm_client.generate_move_explanation` with a FEN, a move and an eval -- no
search tree, no policy prior, no relational facts -- and `backend/app.py` called
it unconditionally from TWO endpoints. It had already run and cached its output:
9 of 16 entries in `data/training/cache/explanations.jsonl` carried the same
position-independent sentence, and the other 7 were real model output truncated
mid-word.

These two tests are what replaces the sign. The first is static and catches the
import before anything can call it; the second is behavioural and asserts the
tree an endpoint actually returns carries no generated prose.
"""
import ast
from pathlib import Path

import chess
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

#: Excluded on purpose. The tests are allowed to import it (this file does not,
#: but the module is scaffolding for the eventual *translator* role and its own
#: unit tests may legitimately reach it); `llm_client.py` obviously imports
#: itself into existence.
EXCLUDED = {BACKEND_DIR / "tests", BACKEND_DIR / "llm_client.py"}


def _is_excluded(path: Path) -> bool:
    return any(path == ex or ex in path.parents for ex in EXCLUDED)


def _imports_llm_client(tree: ast.AST) -> bool:
    """True if this module imports llm_client in any form.

    Covered: `import llm_client`, `import backend.llm_client`,
    `from backend import llm_client`, `from backend.llm_client import X`,
    `from . import llm_client`, `from .llm_client import X`.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # "backend.llm_client" or "llm_client"
                if alias.name == "llm_client" or alias.name.endswith(".llm_client"):
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""          # None for `from . import x`
            if module == "llm_client" or module.endswith(".llm_client"):
                return True
            for alias in node.names:
                if alias.name == "llm_client":
                    return True
    return False


def test_no_module_reachable_from_app_imports_llm_client():
    """Static interlock: no non-test backend module may import the LLM client.

    Uses `ast`, not a regex, so a mention inside a docstring or a comment does
    not trip it and a real import cannot hide behind unusual formatting.
    """
    offenders = []
    for path in sorted(BACKEND_DIR.rglob("*.py")):
        if _is_excluded(path) or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - a broken file is its own failure
            pytest.fail(f"could not parse {path}: {exc}")
        if _imports_llm_client(tree):
            offenders.append(str(path.relative_to(BACKEND_DIR.parent)))

    assert not offenders, (
        "These modules import backend/llm_client.py, so a request path can reach a "
        "language model:\n  "
        + "\n  ".join(offenders)
        + "\n\nThe motto is that the LLM translates LC0's thinking and never reasons about "
          "chess itself. If you are adding a TRANSLATOR that is handed LC0's search tree, "
          "policy prior and relational facts, then change this test deliberately and say so "
          "in the commit. If you are adding a path that asks a model to think about a "
          "position from a FEN and a number, that is the defect this test exists to stop."
    )


@pytest.mark.anyio
async def test_repertoire_tree_response_carries_no_generated_explanation(monkeypatch, tmp_path):
    """Behavioural: the tree the repertoire endpoints return carries no prose.

    `backend/app.py` called `explanations.enrich_tree_explanations(tree)` on the
    tree returned by `build_repertoire_tree`, at two endpoints, and that call
    attached an `explanation` key to every CRITICAL node. So this builds a tree
    with a genuinely critical node -- the exact case the old code enriched --
    and asserts nothing generated is attached to it.

    Tested against `build_repertoire_tree` directly rather than over HTTP: the
    endpoints require the live LC0 engine and a games corpus on disk.
    """
    # Imported INSIDE the test on purpose. The static guard above must stay
    # runnable even when a module under backend/ is broken or unimportable --
    # that is exactly when you most need it to tell you which file is at fault.
    from backend.tests.test_repertoire_tree import MockEngine, _epd_after, _game, _stub_eco
    from backend.training import select_repertoire as sr
    from backend.training import store

    monkeypatch.setattr(store, "TRAINING_DIR", str(tmp_path))
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    _stub_eco(monkeypatch, "B00", ["e2e4"])

    pgn = "\n\n".join([_game("1. e4 e5 2. Nf3 Nc6")] * 4)
    nc6_fen = _epd_after(["e2e4", "e7e5", "g1f3"]).fen()
    game_id = {"white": "Opp", "black": "Me", "date": "????.??.??", "result": "*"}
    profile = {"findings": [
        {"fen_before": nc6_fen, "severity": "blind", "game": game_id},
        {"fen_before": nc6_fen, "severity": "blind", "game": game_id},
        {"fen_before": nc6_fen, "severity": "blind", "game": game_id},
    ]}

    tree = await sr.build_repertoire_tree(
        eco="B00", color="black", pgn_path_or_text=pgn, player_name="Me",
        engine=MockEngine(), profile=profile, min_games=1, max_depth=8)

    # The test is only meaningful if the enrichable case is actually present.
    critical = [n for n in tree["nodes"] if n.get("critical")]
    assert critical, "no critical node was built - the test would pass vacuously"

    with_prose = [
        n.get("user_move", {}).get("uci")
        for n in tree["nodes"]
        if "explanation" in n
    ]
    assert not with_prose, (
        f"nodes carry a generated 'explanation': {with_prose}. "
        "Coaching text must be derived from LC0's own computed values, not written by a "
        "language model handed a FEN and an eval."
    )
