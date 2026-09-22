import chess
import chess.pgn
from typing import List, Set, Optional
from backend.lichess_tagger import Puzzle, cook

class MotifDetector:
    @classmethod
    def analyze_pv(
        cls,
        pre_fen: Optional[str] = None,
        setup_uci: Optional[str] = None,
        pv_san: Optional[List[str]] = None,
        cp: int = 0,
    ) -> Set[str]:
        """
        Uses the official Lichess Python Tagger to detect tactical motifs in a PV line.

        Reconstructs the Lichess puzzle structure:
        - pre_fen: position with opponent to move (1 ply before solver's move)
        - setup_uci: opponent's setup move that reached fen_before
        - pv_san: solver's forcing PV line (SAN strings)
        - cp: solver's POV centipawn score (positive = winning for solver)
        """
        # Handle legacy 2-argument calls (fen, pv_san) gracefully
        if isinstance(setup_uci, list) and pv_san is None:
            pv_san = setup_uci
            setup_uci = None

        if not pre_fen or not setup_uci or not pv_san:
            return set()

        try:
            # 1. Create game starting at pre_fen (opponent to move)
            board = chess.Board(pre_fen)
            game = chess.pgn.Game()
            game.setup(board)

            # 2. Push opponent's setup move to reach fen_before
            setup_move = chess.Move.from_uci(setup_uci)
            if setup_move not in board.legal_moves:
                return set()

            node = game.add_variation(setup_move)
            board.push(setup_move)

            # 3. Add solver's PV moves to the mainline
            for san in pv_san:
                move = board.parse_san(san)
                if move not in board.legal_moves:
                    return set()
                node = node.add_variation(move)
                board.push(move)

            # 4. Construct Puzzle (pov = not game.turn() = solver's POV)
            puzzle = Puzzle(id="lc0_pv", game=game, cp=cp)

            # 5. Cook puzzle to extract motif tags
            tags = cook(puzzle)
            return set(tags)

        except Exception:
            return set()

