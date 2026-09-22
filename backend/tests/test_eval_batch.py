"""
Guard for NeuralVision.evaluate_batch: batched BT3 value+policy for a list of
FENs in ONE forward, with policy renormalized over LEGAL moves and value from the
side-to-move POV, correct for both white- and black-to-move positions.

Opt-in (needs engine/bt3.onnx, slow): runs only with RUN_SLOW_BT3=1. Mutation-
verified: softmax-over-all-1858 (no legal renormalize) leaves ~3% legal mass and
fails test_policy_renormalized_over_legal.
    RUN_SLOW_BT3=1 python -m pytest backend/tests/test_eval_batch.py -q
"""
import os
import chess
import pytest

_BT3 = os.path.join("engine", "bt3.onnx")
pytestmark = pytest.mark.skipif(
    not (os.environ.get("RUN_SLOW_BT3") and os.path.exists(_BT3)),
    reason="opt-in: set RUN_SLOW_BT3=1 and provide engine/bt3.onnx",
)

# (start=white ~0, black-to-move, white up a queen, black up a bishop stm)
_FENS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
    "rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",   # white up a queen
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RN1QKBNR b KQkq - 0 1",   # black up a bishop, stm
]


@pytest.fixture(scope="module")
def vres():
    from backend.neural_vision import NeuralVision
    v = NeuralVision(onnx_path=_BT3)
    assert v.mode == "attention"
    return v, v.evaluate_batch(_FENS)


def test_eval_batch_is_one_forward(vres):
    v, _ = vres
    calls = {"n": 0}
    orig = v.model.forward

    def counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    v.model.forward = counting
    try:
        v.evaluate_batch(_FENS)
    finally:
        v.model.forward = orig
    assert calls["n"] == 1, f"expected one batched forward, got {calls['n']}"


def test_policy_renormalized_over_legal(vres):
    # Correct frame + renormalization => legal moves hold ~all the mass, for BOTH
    # white- and black-to-move (a wrong un-mirror or softmax-over-1858 fails this).
    _, res = vres
    for f, r in zip(_FENS, res):
        legal_uci = {m.uci() for m in chess.Board(f).legal_moves}
        assert {m["uci"] for m in r["policy"]} == legal_uci, "policy not over exactly the legal moves"
        assert abs(sum(m["p"] for m in r["policy"]) - 1.0) < 1e-3, "legal policy mass != 1"
    # start position: top move must carry a real prior, not a flat ~1/1858
    assert res[0]["policy"][0]["p"] > 0.05


def test_value_signs(vres):
    # side-to-move POV: up a queen (white) and up a bishop (black stm) are winning.
    _, res = vres
    assert res[2]["value"] > 0.3, f"white up a queen value {res[2]['value']}"
    assert res[3]["value"] > 0.3, f"black up a bishop (stm) value {res[3]['value']}"
