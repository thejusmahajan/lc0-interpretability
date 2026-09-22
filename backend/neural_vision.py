"""
Neural Vision implementation.
Retrieves real transformer encoder attention saliency from lczerolens via ONNX.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional
import chess

logger = logging.getLogger(__name__)

class NeuralVision:
    def __init__(self, onnx_path: str):
        import torch
        self.mode = "policy_fallback"
        self.model = None
        self.device = torch.device("cpu")
        self._attn_module_names = [
            f"module.encoder{i}/mha/QK/softmax" for i in range(15)
        ]
        
        try:
            import lczerolens
            from lczerolens import LczeroModel

            # Monkey patch for Windows NamedTemporaryFile issue inside onnx2torch
            import lczerolens.model
            original_safe = lczerolens.model.safe_shape_inference
            def patched_safe_shape_inference(onnx_model_or_path, **kwargs):
                if not isinstance(onnx_model_or_path, (str, os.PathLike)):
                    return original_safe(onnx_model_or_path, **kwargs)
                # Write the temp shape-inference model next to the onnx when that
                # dir is writable (local/Windows), else fall back to the system
                # temp dir. On Kaggle the onnx lives under read-only /kaggle/input,
                # where mkstemp(dir=parent) throws Errno 30 and kills attention mode.
                _parent = Path(onnx_model_or_path).parent
                _tmpdir = str(_parent) if os.access(_parent, os.W_OK) else tempfile.gettempdir()
                fd, path = tempfile.mkstemp(dir=_tmpdir)
                os.close(fd)
                try:
                    import onnx2torch.utils.safe_shape_inference as ssi
                    res = ssi._shape_inference_by_model_path(onnx_model_or_path, output_path=path, **kwargs)
                    return res
                finally:
                    try: os.remove(path)
                    except OSError: pass
            lczerolens.model.safe_shape_inference = patched_safe_shape_inference

            self.model = LczeroModel.from_onnx_path(onnx_path)
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model.to(self.device)
            self.model.eval()
            self.mode = "attention"
            logger.info("NeuralVision loaded BT3 ONNX in attention mode on device: %s", self.device)
        except Exception as exc:
            logger.warning("NeuralVision attention unavailable (%s) — policy_fallback", exc)

    def is_available(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Input construction
    #
    # BT3's input is 112 planes, ~84 of which encode the previous 8 positions.
    # Building the tensor from a bare FEN leaves all of those empty, which is
    # input the network never sees in play: evaluate_batch then returns
    # value=-1.0 / wdl=[0,0,1] on essentially every midgame position, and the
    # attention maps shift by 0.11-0.20 per square against a properly-fed pass.
    # The starting position is the one case where a bare FEN is correct, since
    # its true history really is empty -- which is exactly why this hid so long.
    #
    # The trap when fixing it: chess.Board.mirror() returns a board with an
    # EMPTY move_stack, so mirroring a black-to-move position for the
    # white-to-move frame silently throws the history away again. The mirrored
    # frame has to be built by replaying mirrored moves.
    # ------------------------------------------------------------------

    _warned_no_history = False

    @staticmethod
    def _mirror_move(move: chess.Move) -> chess.Move:
        """Vertical flip of a move (a1<->a8), matching Board.mirror()."""
        return chess.Move(move.from_square ^ 56, move.to_square ^ 56,
                          promotion=move.promotion)

    @staticmethod
    def _same_position(a: chess.Board, b: chess.Board) -> bool:
        """Position equality ignoring move counters, which shift under mirroring.

        En passant is compared the way FEN reports it — only when the capture is
        actually legal. A replayed board sets ep_square after any double pawn
        push, while a board parsed from a FEN that printed "-" has none, so a
        raw ep_square comparison rejects perfectly valid replays.
        """
        def eff_ep(board: chess.Board):
            return board.ep_square if board.has_legal_en_passant() else None

        return (a.board_fen() == b.board_fen() and a.turn == b.turn
                and a.castling_rights == b.castling_rights
                and eff_ep(a) == eff_ep(b))

    def _input_board(self, fen: str, history_ucis: Optional[list[str]] = None,
                     root_fen: Optional[str] = None):
        """(LczeroBoard in the white-to-move frame with history, is_black).

        history_ucis are the moves from root_fen (default: the standard start)
        that lead to fen. Without them the tensor is built from the bare FEN and
        the history planes are empty -- degraded, and warned about once.
        """
        from lczerolens import LczeroBoard

        target = chess.Board(fen)
        is_black = target.turn == chess.BLACK

        if not history_ucis:
            if not NeuralVision._warned_no_history:
                NeuralVision._warned_no_history = True
                logger.warning(
                    "NeuralVision called without move history: %d of BT3's 112 "
                    "input planes will be empty and results are unreliable for "
                    "anything but the starting position. Pass history_ucis.",
                    84)
            src = target.mirror() if is_black else target
            return LczeroBoard(src.fen()), is_black

        root = chess.Board(root_fen) if root_fen else chess.Board()
        moves = [chess.Move.from_uci(u) for u in history_ucis]

        if is_black:
            board = LczeroBoard(root.mirror().fen())
            for mv in moves:
                board.push(self._mirror_move(mv))
            expected = target.mirror()
        else:
            board = LczeroBoard(root.fen())
            for mv in moves:
                board.push(mv)
            expected = target

        if not self._same_position(board, expected):
            # Bad history is worse than none: it would feed the network a
            # plausible-looking tensor for a different game.
            raise ValueError(
                f"history_ucis do not lead to {fen!r} "
                f"(replay reached {board.board_fen()!r}, expected {expected.board_fen()!r})")
        return board, is_black

    def _input_tensor(self, fen: str, history_ucis: Optional[list[str]] = None,
                      root_fen: Optional[str] = None):
        board, is_black = self._input_board(fen, history_ucis, root_fen)
        return board.to_input_tensor(), is_black


    def saliency(self, fen: str, policy_dist: list[dict] = None) -> dict[str, float]:
        if self.mode == "attention" and self.model is not None:
            try:
                return self._attention_saliency(fen)
            except Exception as exc:
                logger.error("attention saliency failed (%s) — fallback", exc)
        return self._policy_fallback(fen, policy_dist)

    def _attention_saliency(self, fen: str) -> dict[str, float]:
        import torch
        from lczerolens import LczeroBoard
        
        attention_tensors = []
        
        def hook_fn(module, inp, out):
            t = out[0] if isinstance(out, (tuple, list)) else out
            attention_tensors.append(t.detach())
            
        hooks = []
        for name, mod in self.model.named_modules():
            if name in self._attn_module_names:
                hooks.append(mod.register_forward_hook(hook_fn))
                
        board = LczeroBoard(fen)
        input_tensor = board.to_input_tensor().unsqueeze(0).to(self.device)
        with torch.no_grad():
            self.model(input_tensor)
            
        for h in hooks:
            h.remove()
            
        if not attention_tensors:
            raise RuntimeError("No attention tensors captured")
            
        # attention_tensors has tensors of shape [batch, heads, 64, 64]
        stacked = torch.stack(attention_tensors)
        
        # Average over layers (0) and heads (2) and batch (1)
        # shape [15, 1, 24, 64, 64] -> mean(0,1,2) -> [64, 64]
        avg_attn = stacked.mean(dim=(0, 1, 2))
        
        # We want the attention *received* per square (source),
        # so we average over the queries (axis=0).
        saliency_vec = avg_attn.mean(dim=0)
        
        # Normalize to [0,1]
        max_val = saliency_vec.max()
        min_val = saliency_vec.min()
        if max_val > min_val:
            saliency_vec = (saliency_vec - min_val) / (max_val - min_val)
        else:
            saliency_vec = torch.zeros_like(saliency_vec)
            
        saliency_vec = saliency_vec.tolist()
        
        saliency_map = {}
        files = "abcdefgh"
        ranks = "12345678"
        
        # LC0 token 0 is a1 from White's view
        for i in range(64):
            rank_idx = i // 8
            file_idx = i % 8
            sq = f"{files[file_idx]}{ranks[rank_idx]}"
            saliency_map[sq] = saliency_vec[i]
            
        return saliency_map

    def saliency_absolute(self, fen: str,
                          history_ucis: Optional[list[str]] = None) -> dict[str, float]:
        """
        Public API: BT3 attention saliency keyed by TRUE absolute squares,
        correct for BOTH white-to-move and black-to-move positions.

        Training-system code (diagnostician, drills, hidden gems) MUST use
        this instead of saliency(), which is only frame-correct for
        white-to-move positions. Falls back to policy_fallback shape (all
        zeros without a policy dist) if attention mode is unavailable.
        """
        if self.mode != "attention" or self.model is None:
            return self._policy_fallback(fen, None)
        try:
            return self._saliency_absolute(chess.Board(fen), history_ucis)
        except Exception as exc:
            logger.error("saliency_absolute failed (%s) — fallback", exc)
            return self._policy_fallback(fen, None)

    def saliency_absolute_batch(self, fens: list[str],
                                histories: Optional[list[list[str]]] = None) -> list[dict[str, float]]:
        """
        Public API: Batched BT3 attention saliency for a list of FENs, keyed by
        TRUE absolute squares, correct for BOTH white- and black-to-move positions.
        Runs ONE forward pass for the whole list.

        Falls back to policy_fallback per FEN if attention mode is unavailable, or
        to serial _saliency_absolute on any error in the batched path.
        """
        if not fens:
            return []
        if self.mode != "attention" or self.model is None:
            return [self._policy_fallback(f, None) for f in fens]
        try:
            return self._saliency_absolute_batch(fens, histories)
        except Exception as exc:
            logger.error("saliency_absolute_batch failed (%s) — fallback to serial", exc)
            return [self._saliency_absolute(chess.Board(f),
                                            histories[i] if histories else None)
                    for i, f in enumerate(fens)]

    def _saliency_absolute_batch(self, fens: list[str],
                                 histories: Optional[list[list[str]]] = None) -> list[dict[str, float]]:
        import torch
        from lczerolens import LczeroBoard

        input_tensors = []
        is_black_list = []

        for i, f in enumerate(fens):
            t, is_black = self._input_tensor(
                f, histories[i] if histories else None)
            input_tensors.append(t)
            is_black_list.append(is_black)

        batch_tensor = torch.stack(input_tensors).to(self.device)

        attention_tensors = []
        def hook_fn(module, inp, out):
            t = out[0] if isinstance(out, (tuple, list)) else out
            attention_tensors.append(t.detach())

        hooks = [
            mod.register_forward_hook(hook_fn)
            for name, mod in self.model.named_modules()
            if name in self._attn_module_names
        ]

        try:
            with torch.no_grad():
                self.model(batch_tensor)
        finally:
            for h in hooks:
                h.remove()

        if not attention_tensors:
            raise RuntimeError("No attention tensors captured")

        stacked = torch.stack(attention_tensors)  # [15, N, 24, 64, 64]
        avg_attn = stacked.mean(dim=(0, 2))      # [N, 64, 64]

        files = "abcdefgh"
        ranks = "12345678"
        results = []

        for b_idx in range(len(fens)):
            vec = avg_attn[b_idx].mean(dim=0)     # mean over queries -> [64]
            max_val = vec.max()
            min_val = vec.min()
            if max_val > min_val:
                vec = (vec - min_val) / (max_val - min_val)
            else:
                vec = torch.zeros_like(vec)

            vec_list = vec.tolist()
            saliency_map = {
                f"{files[i % 8]}{ranks[i // 8]}": vec_list[i] for i in range(64)
            }

            if is_black_list[b_idx]:
                saliency_map = {
                    sq[0] + str(9 - int(sq[1])): v for sq, v in saliency_map.items()
                }

            results.append(saliency_map)

        return results

    def evaluate_batch(self, fens: list[str],
                       histories: Optional[list[list[str]]] = None) -> list[dict]:
        """
        Public API: Batched BT3 position evaluation (value + WDL + legal policy) for a
        list of FENs in ONE forward pass.

        Returns per-FEN dict:
        {
            "value": float,       # side-to-move win-ish score in [-1, 1] (w - l)
            "wdl": [w, d, l],     # probabilities from net's WDL head
            "policy": [{"uci": str, "p": float}, ...] # legal moves, p in [0,1], sorted desc
        }
        """
        if not fens:
            return []
        if self.mode != "attention" or self.model is None:
            return [self._eval_fallback(f) for f in fens]
        try:
            return self._evaluate_batch(fens, histories)
        except Exception as exc:
            logger.error("evaluate_batch failed (%s) — fallback to serial", exc)
            return [self._evaluate_one(f) for f in fens]

    def _evaluate_batch(self, fens: list[str],
                        histories: Optional[list[list[str]]] = None) -> list[dict]:
        import torch
        from lczerolens import LczeroBoard

        boards = [chess.Board(f) for f in fens]
        input_tensors = [self._input_tensor(f, histories[i] if histories else None)[0]
                         for i, f in enumerate(fens)]

        batch_tensor = torch.stack(input_tensors).to(self.device)

        with torch.no_grad():
            outputs = self.model(batch_tensor)

        wdl_tensor = outputs["wdl"]       # [N, 3]
        policy_tensor = outputs["policy"] # [N, 1858]
        policy_probs = torch.softmax(policy_tensor, dim=-1)

        results = []
        for i, b in enumerate(boards):
            wdl_row = wdl_tensor[i].tolist()
            w, d, l = float(wdl_row[0]), float(wdl_row[1]), float(wdl_row[2])
            val = w - l

            p_row = policy_probs[i]
            legal_moves = []
            for m in b.legal_moves:
                idx = LczeroBoard.encode_move(m, b.turn)
                legal_moves.append({
                    "uci": m.uci(),
                    "p": float(p_row[idx].item())
                })
            # Renormalize over LEGAL moves (mask illegal), matching lc0's policy
            # semantics. Softmax over all 1858 outputs leaves ~97% of the mass on
            # illegal indices, so the raw legal probs are near-uniform (~0.001)
            # and useless as priors. Dividing by the legal mass is equivalent to
            # a softmax over just the legal-move logits and yields usable priors.
            total_p = sum(x["p"] for x in legal_moves)
            if total_p > 0:
                for x in legal_moves:
                    x["p"] /= total_p
            legal_moves.sort(key=lambda x: x["p"], reverse=True)

            results.append({
                "value": val,
                "wdl": [w, d, l],
                "policy": legal_moves,
            })

        return results

    def _evaluate_one(self, fen: str) -> dict:
        try:
            return self._evaluate_batch([fen])[0]
        except Exception as exc:
            logger.error("_evaluate_one failed for FEN %s (%s)", fen, exc)
            return self._eval_fallback(fen)

    def _eval_fallback(self, fen: str) -> dict:
        board = chess.Board(fen)
        legal = list(board.legal_moves)
        p_uniform = 1.0 / len(legal) if legal else 0.0
        return {
            "value": 0.0,
            "wdl": [0.3333, 0.3334, 0.3333],
            "policy": [{"uci": m.uci(), "p": p_uniform} for m in legal],
        }

    def _saliency_absolute(self, board: "chess.Board",
                           history_ucis: Optional[list[str]] = None) -> dict[str, float]:
        """
        BT3 attention for `board`, always keyed by TRUE absolute squares.

        _attention_saliency is only correct for white-to-move positions. For
        black-to-move positions LC0/BT3 works in the flipped side-to-move frame,
        so we evaluate the vertically-mirrored (white-to-move) board and flip the
        square keys back (rank r -> 9-r). Verified against the white-to-move map.
        """
        return self._saliency_absolute_batch(
            [board.fen()], [history_ucis] if history_ucis else None)[0]

    def calculation_saliency(
        self,
        root_board: "chess.Board",
        lines: list[dict],
        max_positions: int = 8,
        decay: float = 0.85,
    ) -> dict[str, float]:
        """
        Aggregate absolute-frame BT3 attention over the future positions along the
        engine's top PV lines. `lines` = [{"moves": [chess.Move, ...], "weight": float}, ...].
        Weighting: line weight * decay**ply. Deduplicates positions. Caps at
        max_positions total BT3 forwards (each ~1.5s). Returns a [0,1]-normalized map.
        """
        agg = {sq: 0.0 for sq in chess.SQUARE_NAMES}
        total_w = 0.0
        used = 0
        seen: set[str] = set()

        for line in sorted(lines, key=lambda ln: -ln.get("weight", 0.0)):
            if used >= max_positions:
                break
            board = root_board.copy()
            w = line.get("weight", 0.0)
            for ply, mv in enumerate(line.get("moves", [])):
                if used >= max_positions:
                    break
                try:
                    board.push(mv)
                except Exception:
                    break
                key = board.epd()
                if key in seen:
                    continue
                seen.add(key)
                weight = w * (decay ** ply)
                s = self._saliency_absolute(board)
                for sq, v in s.items():
                    agg[sq] += weight * v
                total_w += weight
                used += 1

        if total_w > 0:
            for sq in agg:
                agg[sq] /= total_w
        mx = max(agg.values()) if agg else 0.0
        if mx > 0:
            for sq in agg:
                agg[sq] /= mx
        return agg

    def _policy_fallback(self, fen: str, policy_dist: list[dict] = None) -> dict[str, float]:
        # Sum each move's p onto its from and to squares
        saliency_map = {f"{f}{r}": 0.0 for f in "abcdefgh" for r in "12345678"}
        if not policy_dist:
            return saliency_map
        for move in policy_dist:
            p = move.get("p", 0.0)
            frm = move.get("from")
            to = move.get("to")
            if frm in saliency_map: saliency_map[frm] += p
            if to in saliency_map: saliency_map[to] += p
        max_val = max(saliency_map.values()) if saliency_map else 0.0
        if max_val > 0:
            for sq in saliency_map: saliency_map[sq] /= max_val
        return saliency_map
