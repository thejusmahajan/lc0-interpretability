"""
Mock engine analysis data for well-known chess positions.

Provides realistic pre-computed analysis results so the application
can function without a real engine binary. Each position includes
evaluation, best moves, PV lines, WDL percentages, and a hand-crafted
GM-style verbal summary.
"""

from typing import Optional

# ------------------------------------------------------------------
# Position database
# ------------------------------------------------------------------

MOCK_POSITIONS: dict[str, dict] = {
    # ---------------------------------------------------------------
    # 1. Starting position
    # ---------------------------------------------------------------
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1": {
        "evaluation": 20,
        "best_moves": [
            {"move": "e2e4", "san": "e4", "score": 20},
            {"move": "d2d4", "san": "d4", "score": 18},
            {"move": "c2c4", "san": "c4", "score": 12},
        ],
        "pv_lines": [
            "e4 e5 Nf3 Nc6 Bb5",
            "d4 d5 c4 e6 Nc3 Nf6",
            "c4 e5 Nc3 Nf6 g3",
        ],
        "nodes": 1_250_000,
        "wdl": [320, 590, 90],
        "coach_summary": (
            "This is the starting position — a blank canvas. White enjoys the "
            "natural advantage of the first move, which translates to roughly "
            "+0.20 according to modern engines. The most popular and theoretically "
            "critical choices are 1.e4 (seeking open, tactical play and immediate "
            "central influence) and 1.d4 (aiming for a more strategic, "
            "space-oriented game). The English (1.c4) is a flexible alternative "
            "that often transposes into d4 systems. At this stage, piece "
            "development, central control, and king safety are the three "
            "pillars to keep in mind."
        ),
    },

    # ---------------------------------------------------------------
    # 2. Italian Game — after 1.e4 e5 2.Nf3 Nc6 3.Bc4
    # ---------------------------------------------------------------
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3": {
        "evaluation": 5,
        "best_moves": [
            {"move": "f8c5", "san": "Bc5", "score": 5},
            {"move": "g8f6", "san": "Nf6", "score": 2},
            {"move": "f8e7", "san": "Be7", "score": -3},
        ],
        "pv_lines": [
            "Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+ Bd2",
            "Nf6 d3 Bc5 c3 O-O O-O d5",
            "Be7 d4 d6 dxe5 dxe5 Qxd8+ Bxd8",
        ],
        "nodes": 980_000,
        "wdl": [305, 600, 95],
        "coach_summary": (
            "We have reached the Italian Game after 1.e4 e5 2.Nf3 Nc6 3.Bc4, "
            "one of the oldest and most principled openings. White's bishop "
            "targets the f7-pawn, the weakest point in Black's camp, while the "
            "knight on f3 pressures e5. Black's most classical response is "
            "3…Bc5, leading to the Giuoco Piano ('quiet game'), where both sides "
            "develop naturally. 3…Nf6 is the sharper Two Knights Defense. The "
            "position is roughly equal; the key themes are central control, "
            "development tempo, and the fight for the d4 square."
        ),
    },

    # ---------------------------------------------------------------
    # 3. Sicilian Najdorf middlegame
    # ---------------------------------------------------------------
    "r1b1kb1r/1p1n1ppp/p2ppn2/6B1/3NPP2/2N5/PPP3PP/R2QKB1R w KQkq - 0 8": {
        "evaluation": 45,
        "best_moves": [
            {"move": "d1f3", "san": "Qf3", "score": 45},
            {"move": "f1c4", "san": "Bc4", "score": 38},
            {"move": "f4f5", "san": "f5", "score": 30},
        ],
        "pv_lines": [
            "Qf3 Qc7 O-O-O b5 Bd3 Bb7 Rhe1 Be7",
            "Bc4 Qc7 Qe2 b5 Bb3 Bb7 O-O-O Be7",
            "f5 e5 Nf3 Qc7 Bd3 b5 a3 Bb7",
        ],
        "nodes": 1_480_000,
        "wdl": [420, 480, 100],
        "coach_summary": (
            "This is a typical Sicilian Najdorf middlegame with the English "
            "Attack set-up (f4 + Be3/Bg5). White has a strong central presence "
            "with pawns on d4 and e4, and the Bg5 pins or pressures the f6-knight. "
            "White's plan revolves around a kingside attack, often involving Qf3, "
            "O-O-O, and a pawn storm with g4-g5. Black will counter on the "
            "queenside with …b5, …Bb7, and pressure along the c-file. The "
            "position is dynamically balanced but favours White slightly due "
            "to the space advantage and attacking chances. Key squares to "
            "watch: d5 (outpost), f5 (pawn break), and the a2-g8 diagonal."
        ),
    },

    # ---------------------------------------------------------------
    # 4. Isolated Queen's Pawn (IQP) position
    # ---------------------------------------------------------------
    "r1bq1rk1/pp3ppp/2nbpn2/3p4/3P4/2NBPN2/PP3PPP/R1BQ1RK1 w - - 0 10": {
        "evaluation": 15,
        "best_moves": [
            {"move": "d1e2", "san": "Qe2", "score": 15},
            {"move": "c1g5", "san": "Bg5", "score": 12},
            {"move": "f1e1", "san": "Re1", "score": 10},
        ],
        "pv_lines": [
            "Qe2 Qe7 Rd1 Rd8 Bd2 b6 Rac1 Bb7",
            "Bg5 h6 Bh4 Qe7 Re1 Rd8 Qd2 Bd7",
            "Re1 b6 Qe2 Bb7 Bd2 Rc8 Rac1 Qe7",
        ],
        "nodes": 1_100_000,
        "wdl": [310, 580, 110],
        "coach_summary": (
            "A classic IQP (Isolated Queen's Pawn) structure has arisen. White's "
            "d4-pawn is isolated — it cannot be supported by adjacent pawns — "
            "but it provides dynamic compensation: control of c5 and e5, open "
            "c- and e-files for the rooks, and a potential d4-d5 pawn break "
            "that can blow open the centre. Black's strategy is to blockade "
            "the d4-pawn (ideally with a knight on d5), trade pieces to reach "
            "an endgame where the isolated pawn becomes a weakness, and apply "
            "pressure on d4. White should keep pieces on the board, maintain "
            "piece activity, and look for tactical opportunities around the "
            "d5-break or kingside attack. The position is nearly equal; piece "
            "harmony and timing of the d5 advance are critical."
        ),
    },

    # ---------------------------------------------------------------
    # 5. King and pawn endgame
    # ---------------------------------------------------------------
    "8/5pk1/6p1/4P3/5PP1/8/6K1/8 w - - 0 40": {
        "evaluation": 185,
        "best_moves": [
            {"move": "g4g5", "san": "g5", "score": 185},
            {"move": "g2f3", "san": "Kf3", "score": 150},
            {"move": "f4f5", "san": "f5", "score": 120},
        ],
        "pv_lines": [
            "g5 Kf8 Kf3 Ke7 Ke4 Kd7 Kd4 Ke7 Kc5 Kd7 Kb6",
            "Kf3 Kf8 Ke4 Ke7 Kd5 Kd7 f5 gxf5 Kxf5 Ke7",
            "f5 gxf5 gxf5 Kf8 Kf3 Ke7 Ke4 Kf8 Kd5",
        ],
        "nodes": 620_000,
        "wdl": [720, 230, 50],
        "coach_summary": (
            "This king and pawn endgame is deceptively complex. White is "
            "clearly better (+1.85) thanks to the passed e5-pawn and the "
            "more active king position. The key plan is g5!, fixing Black's "
            "kingside pawns and creating a potential passed pawn on the f-file "
            "after a future f5 break. Black's king is tied to stopping the "
            "e-pawn and cannot venture far. The principles at play: king "
            "activity (centralise!), the power of passed pawns, the concept "
            "of 'two weaknesses' (Black must defend both the kingside and the "
            "e5-pawn advance), and zugzwang possibilities. This is the type "
            "of endgame where precise calculation separates masters from "
            "amateurs."
        ),
    },
}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def get_mock_analysis(fen: str) -> dict:
    """
    Return a mock engine analysis result for a given FEN.

    Looks up the position in the known-positions database. If the
    position is not found, returns a sensible generic fallback.

    Args:
        fen: FEN string of the position to look up.

    Returns:
        dict matching the schema of ``LC0Engine.analyze()``:
        evaluation, best_moves, pv_lines, nodes, wdl.
    """
    # Exact match first
    if fen in MOCK_POSITIONS:
        pos = MOCK_POSITIONS[fen]
        return {
            "evaluation": pos["evaluation"],
            "best_moves": pos["best_moves"],
            "pv_lines": pos["pv_lines"],
            "nodes": pos["nodes"],
            "wdl": pos["wdl"],
        }

    # FEN strings may differ in move counters — try matching just the
    # piece-placement + active-colour + castling + en-passant fields.
    fen_prefix = " ".join(fen.split()[:4])
    for stored_fen, pos in MOCK_POSITIONS.items():
        stored_prefix = " ".join(stored_fen.split()[:4])
        if fen_prefix == stored_prefix:
            return {
                "evaluation": pos["evaluation"],
                "best_moves": pos["best_moves"],
                "pv_lines": pos["pv_lines"],
                "nodes": pos["nodes"],
                "wdl": pos["wdl"],
            }

    # Generic fallback for unknown positions
    return _generic_fallback(fen)


def get_coach_summary(fen: str) -> Optional[str]:
    """
    Return the hand-crafted coach summary for a known position.

    Args:
        fen: FEN string.

    Returns:
        The coach summary string, or None if the position is unknown.
    """
    if fen in MOCK_POSITIONS:
        return MOCK_POSITIONS[fen].get("coach_summary")

    fen_prefix = " ".join(fen.split()[:4])
    for stored_fen, pos in MOCK_POSITIONS.items():
        stored_prefix = " ".join(stored_fen.split()[:4])
        if fen_prefix == stored_prefix:
            return pos.get("coach_summary")

    return None


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _generic_fallback(fen: str) -> dict:
    """
    Generate a plausible generic analysis for an unknown position.

    Uses python-chess to produce basic legal-move information so the
    response is at least structurally valid.
    """
    import chess as _chess

    try:
        board = _chess.Board(fen)
    except ValueError:
        # Invalid FEN — return absolute minimum
        return {
            "evaluation": 0,
            "best_moves": [],
            "pv_lines": [],
            "nodes": 0,
            "wdl": [333, 334, 333],
        }

    legal = list(board.legal_moves)
    best_moves = []
    pv_lines = []

    for move in legal[:3]:
        san = board.san(move)
        best_moves.append({
            "move": move.uci(),
            "san": san,
            "score": 0,
        })
        pv_lines.append(san)

    # Rough material count as a crude evaluation proxy
    material = {
        _chess.PAWN: 100, _chess.KNIGHT: 300, _chess.BISHOP: 325,
        _chess.ROOK: 500, _chess.QUEEN: 900,
    }
    white_mat = sum(
        material.get(p.piece_type, 0)
        for p in board.piece_map().values()
        if p.color == _chess.WHITE
    )
    black_mat = sum(
        material.get(p.piece_type, 0)
        for p in board.piece_map().values()
        if p.color == _chess.BLACK
    )
    eval_cp = white_mat - black_mat

    return {
        "evaluation": eval_cp,
        "best_moves": best_moves,
        "pv_lines": pv_lines,
        "nodes": 0,
        "wdl": [333, 334, 333],
    }
