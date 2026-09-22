"""
Export BT3 Transformer Attention matrices as JSON for the public web demo.

Extracts head-averaged, per-layer [15, 64, 64] attention matrices from BT3 (via NeuralVision),
applies frame correction so both axes are TRUE absolute board squares (a1..h8, python-chess square indexing)
for both White-to-move and Black-to-move positions, quantizes each layer to uint8 (with layer scale),
and records NeuralVision.saliency_absolute as the reference ground truth.
"""
import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import chess
import numpy as np
import torch

from backend.neural_vision import NeuralVision

logger = logging.getLogger(__name__)

DEFAULT_ONNX_PATH = Path("engine") / "bt3.onnx"
DEFAULT_OUTPUT_PATH = Path("scratch") / "attention_export.json"

PINNED_POSITIONS = [
    {
        "id": "tactical",
        "label": "A tactical position",
        "fen": "r1b2rk1/pp1nqppp/2pbpn2/8/2BP4/2N1PN2/PP2QPPP/R1B2RK1 w - - 0 11",
    },
    {
        "id": "quiet",
        "label": "A quiet middlegame",
        "fen": "r1bq1rk1/pp2bppp/2n1pn2/3p4/3P4/2NBPN2/PP3PPP/R1B1QRK1 w - - 0 9",
    },
    {
        "id": "black_to_move",
        "label": "Black to move",
        "fen": "4r1k1/3q1rp1/p1pbpp1p/3p3N/3P2QP/4P1P1/PP4P1/2R2RK1 b - - 2 29",
    },
]


def extract_layer_attention(
    nv: NeuralVision,
    fen: str,
    history_ucis: Optional[list[str]] = None,
) -> np.ndarray:
    """
    Extract [15, 64, 64] float attention matrices from BT3 in TRUE absolute board squares.

    Axis 0: layer index (0..14)
    Axis 1: from_square (0..63, python-chess index: a1=0..h8=63)
    Axis 2: to_square (0..63, python-chess index: a1=0..h8=63)

    Each row (axis 2) sums to 1.0 (softmax distribution over key squares).
    """
    if nv.mode != "attention" or nv.model is None:
        raise RuntimeError("NeuralVision is not loaded in attention mode")

    board = chess.Board(fen)
    is_black = board.turn == chess.BLACK

    # Construct model input tensor (mirrored if black to move)
    inp_tensor, _ = nv._input_tensor(fen, history_ucis=history_ucis)
    batch_tensor = inp_tensor.unsqueeze(0).to(nv.device)

    attention_tensors = []

    def hook_fn(module, inp, out):
        t = out[0] if isinstance(out, (tuple, list)) else out
        attention_tensors.append(t.detach().cpu())

    hooks = [
        mod.register_forward_hook(hook_fn)
        for name, mod in nv.model.named_modules()
        if name in nv._attn_module_names
    ]

    try:
        with torch.no_grad():
            nv.model(batch_tensor)
    finally:
        for h in hooks:
            h.remove()

    if not attention_tensors or len(attention_tensors) != 15:
        raise RuntimeError(f"Expected 15 attention tensors, captured {len(attention_tensors)}")

    # Shape: [15, 1, 24, 64, 64]
    stacked = torch.stack(attention_tensors)
    # Average across 24 heads -> [15, 64, 64]
    layer_attn = stacked.mean(dim=2).squeeze(1)

    # Frame correction for Black to move:
    # BT3 evaluates mirrored board (White perspective).
    # Mirrored square index q corresponds to absolute square Q = q ^ 56.
    if is_black:
        flip = torch.tensor([i ^ 56 for i in range(64)])
        layer_attn = layer_attn[:, flip, :][:, :, flip]

    return layer_attn.numpy().astype(np.float64)


def reduce_to_saliency_absolute(layer_attn: np.ndarray) -> dict[str, float]:
    """
    Reduce [15, 64, 64] absolute attention matrices to [0, 1] normalized per-square saliency.
    Matches NeuralVision._saliency_absolute reduction verbatim.
    """
    # Average over layers -> [64, 64]
    avg_layers = layer_attn.mean(axis=0)
    # Average over query squares (axis 0) -> [64] (attention received per square)
    vec = avg_layers.mean(axis=0)

    max_val = float(vec.max())
    min_val = float(vec.min())
    if max_val > min_val:
        norm_vec = (vec - min_val) / (max_val - min_val)
    else:
        norm_vec = np.zeros_like(vec)

    return {chess.SQUARE_NAMES[i]: float(norm_vec[i]) for i in range(64)}


def quantize_layer(matrix_64x64: np.ndarray) -> tuple[float, str]:
    """
    Quantize a 64x64 float matrix to uint8 relative to layer maximum scale.
    Returns (scale, base64_u8_string).
    """
    if matrix_64x64.shape != (64, 64):
        raise ValueError(f"Expected shape (64, 64), got {matrix_64x64.shape}")

    scale = float(matrix_64x64.max())
    if scale > 0.0:
        u8 = np.clip(np.round(255.0 * matrix_64x64 / scale), 0, 255).astype(np.uint8)
    else:
        u8 = np.zeros((64, 64), dtype=np.uint8)

    raw_bytes = u8.tobytes()
    if len(raw_bytes) != 4096:
        raise ValueError(f"Expected 4096 bytes, got {len(raw_bytes)}")

    b64_str = base64.b64encode(raw_bytes).decode("ascii")
    return scale, b64_str


def dequantize_layer(scale: float, attn_u8_b64: str) -> np.ndarray:
    """
    Dequantize a base64 uint8 attention string back to float 64x64 matrix.
    """
    raw_bytes = base64.b64decode(attn_u8_b64)
    if len(raw_bytes) != 4096:
        raise ValueError(f"Expected 4096 bytes, got {len(raw_bytes)}")
    u8 = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((64, 64))
    if scale > 0:
        return (u8.astype(np.float64) / 255.0) * scale
    return np.zeros((64, 64), dtype=np.float64)


def build_export_payload(
    nv: NeuralVision,
    positions: Optional[list[dict]] = None,
) -> dict:
    """
    Build the full JSON export payload for all specified positions.
    """
    if positions is None:
        positions = PINNED_POSITIONS

    pos_payloads = []
    for pos in positions:
        fen = pos["fen"]
        board = chess.Board(fen)
        side_to_move = "white" if board.turn == chess.WHITE else "black"

        # 1. Extract [15, 64, 64] float attention
        layer_attn = extract_layer_attention(nv, fen, history_ucis=None)

        # 2. Reference ground truth from audited API
        ref_saliency = nv.saliency_absolute(fen)

        # 3. Quantize all 15 layers
        layers_data = []
        for l_idx in range(15):
            scale, b64_data = quantize_layer(layer_attn[l_idx])
            layers_data.append({
                "layer": l_idx,
                "scale": round(scale, 6),
                "attn_u8": b64_data,
            })

        pos_payloads.append({
            "id": pos["id"],
            "label": pos["label"],
            "fen": fen,
            "side_to_move": side_to_move,
            "history_ucis": None,
            "layers": layers_data,
            "saliency_absolute": {sq: round(float(v), 6) for sq, v in ref_saliency.items()},
        })

    payload = {
        "schema": "bt3-attention-v1",
        "net": "BT3-768x15x24h",
        "n_layers": 15,
        "n_heads": 24,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Head-averaged attention per layer. Absolute board squares on both axes.",
        "positions": pos_payloads,
    }
    return payload


def export_attention_to_file(
    onnx_path: Union[str, Path] = DEFAULT_ONNX_PATH,
    output_path: Union[str, Path] = DEFAULT_OUTPUT_PATH,
    positions: Optional[list[dict]] = None,
) -> Path:
    """
    Run export using the BT3 ONNX model and save JSON payload to output_path.
    """
    onnx_path = Path(onnx_path)
    output_path = Path(output_path)

    if not onnx_path.exists():
        raise FileNotFoundError(f"BT3 ONNX model not found at {onnx_path}")

    nv = NeuralVision(onnx_path=str(onnx_path))
    if nv.mode != "attention" or nv.model is None:
        raise RuntimeError("Failed to load BT3 in attention mode")

    payload = build_export_payload(nv, positions=positions)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return output_path


def main():
    onnx_path = DEFAULT_ONNX_PATH
    output_path = DEFAULT_OUTPUT_PATH

    print(f"Loading BT3 ONNX from: {onnx_path}")
    nv = NeuralVision(onnx_path=str(onnx_path))
    if nv.mode != "attention" or nv.model is None:
        print(f"ERROR: BT3 model failed to load in attention mode (mode={nv.mode})")
        return

    print("Extracting and building attention payload for 3 positions...")
    payload = build_export_payload(nv)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    file_size = output_path.stat().st_size
    print(f"\nSuccessfully exported to {output_path}")
    print(f"File size: {file_size:,} bytes ({file_size / (1024 * 1024):.3f} MB)")

    print("\n--- Positions Summary ---")
    for pos in payload["positions"]:
        print(f"ID: {pos['id']:15} | side_to_move: {pos['side_to_move']:5} | FEN: {pos['fen']}")

    # Tactical top 5 squares
    tactical = next(p for p in payload["positions"] if p["id"] == "tactical")
    saliency = tactical["saliency_absolute"]
    top5 = sorted(saliency.items(), key=lambda x: -x[1])[:5]
    print("\n--- Tactical Position Top 5 Saliency Squares ---")
    for rank, (sq, val) in enumerate(top5, 1):
        print(f"  {rank}. {sq}: {val:.6f}")


if __name__ == "__main__":
    main()
