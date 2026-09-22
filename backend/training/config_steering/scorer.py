"""Configuration steering scorer and candidate move re-ranker.

Loads the trained dual-head PhiNet model (phi_b2.pt) and scores positions/moves:
1. Phi in [0, 1] -- opponent's blunder likelihood from the resulting position.
2. motif affinity in [0, 1]^20 -- multi-label probabilities over the 20 tactical themes.

Implements Stage B and D from PLAN_CONFIGURATION_STEERING.md section 6:
  Score(move) = Phi(position after move)
LC0 holds an absolute safety veto (steer_max_loss_cp); Phi re-ranks only what LC0 has
already declared sound.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import chess
import numpy as np
import torch

from backend.training.config_steering.encode import encode
from phi_net.data import _unpack
from phi_net.model import build_model

DEFAULT_CHECKPOINT = Path("phi_net/runs/phi_b2.pt")


class PhiScorer:
    """Inference wrapper for the trained Phi configuration potential model."""

    _instance: PhiScorer | None = None

    def __init__(
        self,
        checkpoint_path: str | Path | None = None,
        device: torch.device | str | None = None,
    ) -> None:
        ckpt_path = Path(checkpoint_path) if checkpoint_path else DEFAULT_CHECKPOINT
        if not ckpt_path.exists():
            raise FileNotFoundError(
                f"Model checkpoint not found at {ckpt_path}. "
                f"Ensure phi_b2.pt is downloaded into phi_net/runs/."
            )

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        args = ckpt.get("args", {})
        self.model = build_model(
            channels=args.get("channels", 64),
            blocks=args.get("blocks", 6),
            n_motifs=ckpt.get("n_motifs", 20),
        ).to(self.device)
        self.model.load_state_dict(ckpt["model"])
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad = False

        manifest = ckpt.get("dataset_manifest") or {}
        self.themes: list[str] = manifest.get(
            "theme_vocabulary_20",
            [
                "crushing", "short", "endgame", "middlegame", "advantage", "long",
                "master", "veryLong", "fork", "sacrifice", "defensiveMove", "mate",
                "advancedPawn", "pin", "kingsideAttack", "pawnEndgame", "rookEndgame",
                "quietMove", "opening", "discoveredAttack",
            ],
        )

        # Calibration curve for UI display (isotonic regression fitted on validation split)
        calib_path = ckpt_path.parent / f"{ckpt_path.stem}_calibration.json"
        if not calib_path.exists():
            calib_path = ckpt_path.parent / "phi_b2_calibration.json"

        self.calibrated = False
        self.grid_x: np.ndarray | None = None
        self.grid_y: np.ndarray | None = None

        if calib_path.exists():
            try:
                import json
                with open(calib_path, "r", encoding="utf-8") as f:
                    calib_data = json.load(f)
                self.grid_x = np.array(calib_data["grid_x"], dtype=np.float64)
                self.grid_y = np.array(calib_data["grid_y"], dtype=np.float64)
                self.calibrated = True
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to load calibration from %s: %s", calib_path, e)
        else:
            import logging
            logging.getLogger(__name__).warning(
                "Calibration file not found at %s. Falling back to raw values.", calib_path
            )

    def calibrate_phi(self, raw_phi: float) -> float:
        """Calibrate a raw Phi score using the isotonic regression curve for UI display.
        
        If calibration file is absent, falls back to raw_phi and logs a warning.
        """
        if not self.calibrated or self.grid_x is None or self.grid_y is None:
            import logging
            logging.getLogger(__name__).warning(
                "Calibrate called without calibration data. Falling back to raw value."
            )
            return float(raw_phi)
        val = float(
            np.interp(
                raw_phi,
                self.grid_x,
                self.grid_y,
                left=float(self.grid_y[0]),
                right=float(self.grid_y[-1]),
            )
        )
        return float(np.clip(val, 0.0, 1.0))

    @classmethod
    def get_instance(cls, checkpoint_path: str | Path | None = None) -> PhiScorer:
        """Cached singleton instance helper."""
        if cls._instance is None:
            cls._instance = cls(checkpoint_path=checkpoint_path)
        return cls._instance

    @torch.no_grad()
    def score_board(self, board: chess.Board) -> tuple[float, dict[str, float]]:
        """Score a board position.

        Returns:
          phi: probability in [0, 1] that the side to move blunders from this configuration.
          motifs: mapping of theme name to probability in [0, 1].
        """
        bb = encode(board)
        bb_t = torch.from_numpy(bb).unsqueeze(0).to(torch.int64)
        x = _unpack(bb_t, self.device)
        phi_logit, motif_logits = self.model(x)
        phi = float(torch.sigmoid(phi_logit).item())
        motif_probs = torch.sigmoid(motif_logits)[0].tolist()
        motifs = {name: float(prob) for name, prob in zip(self.themes, motif_probs)}
        return phi, motifs

    def score_move(self, board: chess.Board, move: chess.Move) -> tuple[float, dict[str, float]]:
        """Score the position *after* playing ``move``.

        The resulting position is evaluated from the opponent's perspective (side to move).
        High Phi means the opponent is under severe structural / configuration tension.
        """
        b_after = board.copy(stack=False)
        b_after.push(move)
        return self.score_board(b_after)

    def steer_candidates(
        self,
        board: chess.Board,
        candidates: list[dict],
        best_eval_cp: int,
        steer_max_loss_cp: int = 60,
        steer_min_eval_cp: int = -60,
        steer_edge: float = 0.03,
    ) -> dict:
        """Re-rank candidate moves by Phi potential under LC0's safety veto.

        Parameters:
          board: The position from which the mover is choosing.
          candidates: list of dicts with {"uci", "san", "eval_cp"}.
          best_eval_cp: mover-POV eval of the objective-best move.
          steer_max_loss_cp: maximum centipawn sacrifice vs best move (default 60 cp).
          steer_min_eval_cp: minimum centipawn evaluation allowed (default -60 cp).
          steer_edge: minimum Phi difference required to trigger had_sharp_move.

        Returns:
          dict with {"playable", "objective_best", "sharp_move", "had_sharp_move"}
        """
        playable = [
            c for c in candidates
            if best_eval_cp - c["eval_cp"] <= steer_max_loss_cp
            and c["eval_cp"] >= steer_min_eval_cp
        ]
        if not playable:
            return {
                "playable": [],
                "objective_best": None,
                "sharp_move": None,
                "had_sharp_move": False,
            }

        for c in playable:
            move = chess.Move.from_uci(c["uci"])
            phi_raw, motifs = self.score_move(board, move)
            c["phi_raw"] = phi_raw
            c["phi_display"] = self.calibrate_phi(phi_raw)
            c["phi"] = phi_raw  # Keep for backward compatibility
            c["motifs"] = motifs

        # Ranking is strictly on phi_raw, NEVER calibrated
        playable.sort(key=lambda c: c["phi_raw"], reverse=True)
        objective_best = max(playable, key=lambda c: c["eval_cp"])
        sharp_move = playable[0]
        had_sharp_move = (
            sharp_move["uci"] != objective_best["uci"]
            and sharp_move["phi_raw"] - objective_best["phi_raw"] >= steer_edge
        )

        return {
            "playable": playable,
            "objective_best": objective_best,
            "sharp_move": sharp_move,
            "had_sharp_move": had_sharp_move,
        }
