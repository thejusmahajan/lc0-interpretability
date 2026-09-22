"""
Guard for NeuralVision.saliency_absolute_batch: the batched BT3 saliency must
(a) run ONE forward pass for the whole list (not a per-board loop) and
(b) return square-for-square identical maps to the serial saliency_absolute,
for both white- and black-to-move positions.

Requires the real BT3 net (engine/bt3.onnx, ~392 MB, gitignored) and is slow
(~1-2 min to load), so it is OPT-IN: it skips unless RUN_SLOW_BT3=1 is set and
the net is present. Run it with:
    RUN_SLOW_BT3=1 python -m pytest backend/tests/test_batched_saliency.py -q
Mutation-verified: breaking the black-to-move rank-flip fails (b); duplicating
the forward fails (a).
"""
import os
import pytest

_BT3 = os.path.join("engine", "bt3.onnx")
pytestmark = pytest.mark.skipif(
    not (os.environ.get("RUN_SLOW_BT3") and os.path.exists(_BT3)),
    reason="opt-in: set RUN_SLOW_BT3=1 and provide engine/bt3.onnx",
)

_FENS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",          # black
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",   # black
    "8/8/4k3/8/4P3/4K3/8/8 w - - 0 1",                                      # endgame white
    "6k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1",                                  # endgame black
]


@pytest.fixture(scope="module")
def vision():
    from backend.neural_vision import NeuralVision
    v = NeuralVision(onnx_path=_BT3)
    assert v.mode == "attention", "BT3 did not load in attention mode"
    return v


def test_batched_saliency_is_one_forward(vision):
    # (a) REAL BATCH: the model's forward runs exactly once for the whole list.
    calls = {"n": 0}
    orig = vision.model.forward

    def counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    vision.model.forward = counting
    try:
        vision.saliency_absolute_batch(_FENS)
    finally:
        vision.model.forward = orig
    assert calls["n"] == 1, f"expected one batched forward, got {calls['n']} (looping)"


def test_batched_saliency_matches_serial(vision):
    # (b) CORRECTNESS: batch == serial, square-for-square, white and black to move.
    serial = [vision.saliency_absolute(f) for f in _FENS]
    batched = vision.saliency_absolute_batch(_FENS)
    assert len(batched) == len(_FENS)
    maxdiff = 0.0
    for i, (s, b) in enumerate(zip(serial, batched)):
        assert set(s) == set(b), f"square-key mismatch at {i}"
        for sq in s:
            maxdiff = max(maxdiff, abs(s[sq] - b[sq]))
    assert maxdiff < 1e-3, f"batch != serial, max per-square diff {maxdiff}"
