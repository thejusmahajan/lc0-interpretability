"""
Heatmap generators for chess position analysis.

Produces square-by-square numeric data for three types of heatmaps:
  1. Control  — who controls each square (white +1 … black -1)
  2. Activity — how active each piece is (0 = trapped … 1 = very active)
  3. Tension  — how contested each square is (0 = calm … 1 = maximum tension)
"""

import chess

# All 64 square names in standard order (a1, b1, … h8)
ALL_SQUARES = [chess.square_name(sq) for sq in chess.SQUARES]


# ------------------------------------------------------------------
# 1. Control heatmap
# ------------------------------------------------------------------

def generate_control_heatmap(fen: str) -> dict[str, float]:
    """
    Calculate a control value for each square.

    The control value ranges from -1.0 (strong black control) to
    +1.0 (strong white control). It accounts for:
      - Number of white vs. black attackers on each square
      - Piece presence (occupying a square counts as partial control)

    Args:
        fen: FEN string of the position.

    Returns:
        Mapping of square name → control value in [-1.0, 1.0].
    """
    board = chess.Board(fen)
    heatmap: dict[str, float] = {}

    # First pass: collect raw control deltas to find the range for
    # normalisation.
    raw: dict[int, float] = {}
    max_abs = 0.0

    for sq in chess.SQUARES:
        white_attackers = len(board.attackers(chess.WHITE, sq))
        black_attackers = len(board.attackers(chess.BLACK, sq))

        # Base control from attackers
        delta = float(white_attackers - black_attackers)

        # Piece presence bonus: occupying a square is partial control
        piece = board.piece_at(sq)
        if piece is not None:
            presence_bonus = 0.5 if piece.color == chess.WHITE else -0.5
            delta += presence_bonus

        raw[sq] = delta
        if abs(delta) > max_abs:
            max_abs = abs(delta)

    # Normalise to [-1.0, 1.0]
    for sq in chess.SQUARES:
        name = chess.square_name(sq)
        if max_abs > 0:
            heatmap[name] = round(raw[sq] / max_abs, 4)
        else:
            heatmap[name] = 0.0

    return heatmap


# ------------------------------------------------------------------
# 2. Piece activity heatmap
# ------------------------------------------------------------------

def generate_piece_activity_heatmap(fen: str) -> dict[str, float]:
    """
    Measure each piece's mobility (number of legal moves involving it).

    Returns a mapping of square name → normalised activity score:
      - 0.0 = piece is trapped or no piece on the square
      - 1.0 = most active piece on the board

    Squares without pieces are always 0.0.

    Args:
        fen: FEN string of the position.

    Returns:
        Mapping of square name → activity value in [0.0, 1.0].
    """
    board = chess.Board(fen)
    heatmap: dict[str, float] = {chess.square_name(sq): 0.0 for sq in chess.SQUARES}

    # We need to count legal moves for pieces of BOTH colours,
    # so we evaluate each side in turn.
    mobility: dict[int, int] = {}

    for color in [chess.WHITE, chess.BLACK]:
        # Temporarily set the side to move
        temp_board = board.copy()
        temp_board.turn = color
        # Clear en-passant to avoid illegal-state issues when we
        # flip the turn artificially.
        temp_board.ep_square = None

        for move in temp_board.legal_moves:
            from_sq = move.from_square
            piece = temp_board.piece_at(from_sq)
            if piece is not None and piece.color == color:
                mobility[from_sq] = mobility.get(from_sq, 0) + 1

    # Normalise
    max_mobility = max(mobility.values()) if mobility else 1

    for sq, count in mobility.items():
        name = chess.square_name(sq)
        heatmap[name] = round(count / max_mobility, 4) if max_mobility > 0 else 0.0

    return heatmap


# ------------------------------------------------------------------
# 3. Tension heatmap
# ------------------------------------------------------------------

def generate_tension_heatmap(fen: str) -> dict[str, float]:
    """
    Highlight squares where both sides have attackers (contested squares).

    The tension value ranges from 0.0 (no contest) to 1.0 (maximum
    tension). Tension is computed as:
        min(white_attackers, black_attackers) / max_tension

    This emphasises squares where BOTH sides commit forces, rather
    than squares dominated by one side.

    Args:
        fen: FEN string of the position.

    Returns:
        Mapping of square name → tension value in [0.0, 1.0].
    """
    board = chess.Board(fen)
    raw: dict[int, float] = {}
    max_tension = 0.0

    for sq in chess.SQUARES:
        w = len(board.attackers(chess.WHITE, sq))
        b = len(board.attackers(chess.BLACK, sq))
        tension = float(min(w, b))

        # Bonus for squares occupied by a piece attacked by the opponent
        piece = board.piece_at(sq)
        if piece is not None:
            enemy = not piece.color
            enemy_attackers = len(board.attackers(enemy, sq))
            if enemy_attackers > 0:
                tension += 0.5  # extra tension for an attacked piece

        raw[sq] = tension
        if tension > max_tension:
            max_tension = tension

    heatmap: dict[str, float] = {}
    for sq in chess.SQUARES:
        name = chess.square_name(sq)
        if max_tension > 0:
            heatmap[name] = round(raw[sq] / max_tension, 4)
        else:
            heatmap[name] = 0.0

    return heatmap


# ------------------------------------------------------------------
# Convenience wrapper
# ------------------------------------------------------------------

def generate_all_heatmaps(fen: str) -> dict:
    """
    Generate all three heatmaps for a given position.

    Args:
        fen: FEN string of the position.

    Returns:
        Dict with keys ``control``, ``activity``, ``tension``,
        each mapping square names to float values.
    """
    return {
        "control": generate_control_heatmap(fen),
        "activity": generate_piece_activity_heatmap(fen),
        "tension": generate_tension_heatmap(fen),
    }
