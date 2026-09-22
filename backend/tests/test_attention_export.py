"""
Tests for BT3 attention JSON export (backend/training/attention_export.py).

Guards:
1. Schema integrity & shape verification (3 positions, 15 layers, 4096 bytes per layer).
2. Softmax row-sum probability distribution check (each row sums to ~1.0).
3. Frame correctness matching audited NeuralVision.saliency_absolute API.
4. Non-mirrored orientation check on Black-to-move position.
5. Quantization round-trip error bound check.
"""
import base64
import os
from pathlib import Path

import chess
import numpy as np
import pytest

from backend.neural_vision import NeuralVision
from backend.training.attention_export import (
    PINNED_POSITIONS,
    build_export_payload,
    dequantize_layer,
    extract_layer_attention,
    quantize_layer,
    reduce_to_saliency_absolute,
)

_BT3 = os.path.join("engine", "bt3.onnx")
pytestmark = pytest.mark.skipif(
    not os.path.exists(_BT3),
    reason="BT3 ONNX model not found at engine/bt3.onnx",
)


@pytest.fixture(scope="module")
def vision():
    v = NeuralVision(onnx_path=_BT3)
    assert v.mode == "attention", "BT3 did not load in attention mode"
    return v


@pytest.fixture(scope="module")
def payload(vision):
    return build_export_payload(vision)


def test_shapes_and_schema(payload):
    """
    1. test_shapes_and_schema — 3 positions, each with 15 layers, each attn_u8
       decoding to exactly 4096 bytes; all required keys present.
    """
    assert payload["schema"] == "bt3-attention-v1"
    assert payload["net"] == "BT3-768x15x24h"
    assert payload["n_layers"] == 15
    assert payload["n_heads"] == 24
    assert "generated_utc" in payload
    assert "note" in payload
    assert len(payload["positions"]) == 3

    expected_ids = ["tactical", "quiet", "black_to_move"]
    actual_ids = [p["id"] for p in payload["positions"]]
    assert actual_ids == expected_ids

    for pos in payload["positions"]:
        assert "id" in pos
        assert "label" in pos
        assert "fen" in pos
        assert pos["side_to_move"] in ("white", "black")
        assert pos["history_ucis"] is None
        assert len(pos["layers"]) == 15

        for idx, layer_data in enumerate(pos["layers"]):
            assert layer_data["layer"] == idx
            assert isinstance(layer_data["scale"], float)
            assert layer_data["scale"] > 0.0

            raw = base64.b64decode(layer_data["attn_u8"])
            assert len(raw) == 4096, f"Layer {idx} raw byte length was {len(raw)}, expected 4096"

        assert len(pos["saliency_absolute"]) == 64
        for sq in chess.SQUARE_NAMES:
            assert sq in pos["saliency_absolute"]
            val = pos["saliency_absolute"][sq]
            assert 0.0 <= val <= 1.0


def test_rows_are_probability_distributions(payload):
    """
    2. test_rows_are_probability_distributions — attention comes from softmax,
       so each row of the de-quantised 64x64 matrix must sum to ~1.0 (within 0.02).
       If this fails, axes are transposed.
    """
    for pos in payload["positions"]:
        # Test every layer across all positions
        for layer_data in pos["layers"]:
            matrix = dequantize_layer(layer_data["scale"], layer_data["attn_u8"])
            assert matrix.shape == (64, 64)

            row_sums = matrix.sum(axis=1)  # sum across to_square columns
            for r_idx, r_sum in enumerate(row_sums):
                assert abs(r_sum - 1.0) < 0.02, (
                    f"Position {pos['id']} layer {layer_data['layer']} row {r_idx} "
                    f"summed to {r_sum:.6f}, expected ~1.0 (axis transposition error)"
                )


def test_frame_matches_the_audited_api(vision, payload):
    """
    3. test_frame_matches_the_audited_api — THE critical guard.
       For each position, reduce exported [15,64,64] tensors the same way
       _saliency_absolute reduces attention, and assert result equals
       saliency_absolute(fen) within 1e-4 (unquantized) and within 2e-3 (dequantized).
    """
    for pos in payload["positions"]:
        fen = pos["fen"]
        ref = vision.saliency_absolute(fen)

        # A. Unquantized float attention reduction
        raw_attn = extract_layer_attention(vision, fen, history_ucis=None)
        raw_reduced = reduce_to_saliency_absolute(raw_attn)

        for sq in chess.SQUARE_NAMES:
            diff_raw = abs(raw_reduced[sq] - ref[sq])
            assert diff_raw < 1e-4, (
                f"Position {pos['id']} sq {sq} raw reduction {raw_reduced[sq]} "
                f"differs from ref {ref[sq]} by {diff_raw}"
            )

        # B. Dequantized attention reduction
        dequant_layers = np.stack([
            dequantize_layer(l["scale"], l["attn_u8"])
            for l in pos["layers"]
        ], axis=0)
        dequant_reduced = reduce_to_saliency_absolute(dequant_layers)

        for sq in chess.SQUARE_NAMES:
            diff_dequant = abs(dequant_reduced[sq] - ref[sq])
            assert diff_dequant < 2e-3, (
                f"Position {pos['id']} sq {sq} dequantized reduction {dequant_reduced[sq]} "
                f"differs from ref {ref[sq]} by {diff_dequant}"
            )


def test_black_to_move_is_not_mirrored(vision, payload):
    """
    4. test_black_to_move_is_not_mirrored — for black_to_move position, assert
       exported per-square totals match saliency_absolute(fen) AND do NOT match
       vertically-mirrored version of themselves.
    """
    btm_pos = next(p for p in payload["positions"] if p["id"] == "black_to_move")
    assert btm_pos["side_to_move"] == "black"

    ref = vision.saliency_absolute(btm_pos["fen"])
    exported = btm_pos["saliency_absolute"]

    # 1. Matches ground truth
    max_diff_ref = max(abs(exported[sq] - ref[sq]) for sq in chess.SQUARE_NAMES)
    assert max_diff_ref < 1e-4, f"Mismatch vs saliency_absolute: {max_diff_ref}"

    # 2. Strong asymmetry against vertical reflection
    # Mirroring rank r -> 9-r (sq ^ 56)
    mirrored_map = {
        chess.SQUARE_NAMES[i ^ 56]: exported[chess.SQUARE_NAMES[i]]
        for i in range(64)
    }
    max_diff_mirror = max(abs(exported[sq] - mirrored_map[sq]) for sq in chess.SQUARE_NAMES)
    assert max_diff_mirror > 0.5, (
        f"Black-to-move position appears symmetric (diff vs mirror = {max_diff_mirror:.4f}). "
        f"Expected > 0.5 to prove non-mirrored orientation."
    )


def test_quantisation_round_trip(vision):
    """
    5. test_quantisation_round_trip — de-quantised values are within scale/255 of originals.
    """
    sample_fen = PINNED_POSITIONS[0]["fen"]
    raw_attn = extract_layer_attention(vision, sample_fen)

    for l_idx in range(15):
        orig = raw_attn[l_idx]
        scale, b64_str = quantize_layer(orig)
        recovered = dequantize_layer(scale, b64_str)

        max_err = float(np.max(np.abs(orig - recovered)))
        max_allowed = (scale / 255.0) + 1e-7
        assert max_err <= max_allowed, (
            f"Layer {l_idx} quantization error {max_err:.8f} exceeded {max_allowed:.8f}"
        )
