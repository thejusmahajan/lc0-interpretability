"""
Concept Mapper — translates raw chess data into GM-language explanations.

Analyses a position from multiple angles (king safety, pawn structure,
piece activity, centre control, material) and produces human-readable
observations using vocabulary appropriate for a ~2100 ELO student
receiving coaching from a Grandmaster.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import chess

from backend.tactics import MotifDetector
from backend.training import metrics

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

PIECE_VALUES: dict[int, float] = {
    chess.PAWN: 1.0,
    chess.KNIGHT: 3.0,
    chess.BISHOP: 3.25,
    chess.ROOK: 5.0,
    chess.QUEEN: 9.0,
}

# Centre squares
CENTRE = [chess.D4, chess.D5, chess.E4, chess.E5]
EXTENDED_CENTRE = CENTRE + [chess.C3, chess.C4, chess.C5, chess.C6,
                             chess.D3, chess.D6, chess.E3, chess.E6,
                             chess.F3, chess.F4, chess.F5, chess.F6]

# Pawn-shelter squares relative to common king positions
KING_SHELTER: dict[int, list[int]] = {
    # White king on g1
    chess.G1: [chess.F2, chess.G2, chess.H2],
    chess.H1: [chess.F2, chess.G2, chess.H2],
    # White king on c1 (queenside castling)
    chess.C1: [chess.A2, chess.B2, chess.C2],
    chess.B1: [chess.A2, chess.B2, chess.C2],
    # Black king on g8
    chess.G8: [chess.F7, chess.G7, chess.H7],
    chess.H8: [chess.F7, chess.G7, chess.H7],
    # Black king on c8 (queenside castling)
    chess.C8: [chess.A7, chess.B7, chess.C7],
    chess.B8: [chess.A7, chess.B7, chess.C7],
}


# ------------------------------------------------------------------
# Observation data class
# ------------------------------------------------------------------

@dataclass
class Observation:
    """A single positional observation with GM-language explanation."""
    category: str       # king_safety | pawn_structure | piece_activity | center_control | material
    severity: str       # info | warning | critical
    text: str           # human-readable GM-language explanation
    squares: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "text": self.text,
            "squares": self.squares,
        }


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def analyze_position(
    fen: str,
    engine_analysis: Optional[dict] = None,
    pre_fen: Optional[str] = None,
    setup_uci: Optional[str] = None,
) -> dict:
    """
    Produce a structured, GM-style analysis of a chess position.

    Args:
        fen: FEN string of the position.
        engine_analysis: Optional engine output dict (evaluation,
            best_moves, etc.) to enrich the summary.
        pre_fen: Optional FEN before the setup move.
        setup_uci: Optional UCI move string that reached fen.

    Returns:
        dict with:
            summary      — 1-2 sentence high-level assessment
            observations — list of observation dicts
    """
    board = chess.Board(fen)
    observations: list[Observation] = []

    observations.extend(_assess_material(board))
    observations.extend(_assess_center_control(board))
    observations.extend(_assess_pawn_structure(board))
    observations.extend(_assess_piece_activity(board))
    observations.extend(_assess_king_safety(board))
    
    # Analyze tactical motifs if PVs and pre_fen/setup_uci context are available
    if pre_fen and setup_uci and engine_analysis:
        pv_lines = engine_analysis.get("pv_lines", [])
        if pv_lines and len(pv_lines) > 0:
            top_pv = pv_lines[0]
            if top_pv:
                pv_san_list = top_pv.split() if isinstance(top_pv, str) else top_pv
                if pv_san_list:
                    cp = metrics.eval_cp_number(engine_analysis.get("evaluation")) or 0
                    cp_mover = cp if board.turn == chess.WHITE else -cp
                    motifs = MotifDetector.analyze_pv(pre_fen, setup_uci, pv_san_list, cp_mover)
                    if motifs:
                        # Format motifs nicely (e.g., 'discoveredAttack' -> 'Discovered Attack')
                        formatted_motifs = []
                        for m in motifs:
                            formatted = ''.join(' ' + c if c.isupper() else c for c in m).strip().title()
                            formatted_motifs.append(formatted)
                            
                        obs_text = "LC0's primary forcing line involves tactical motifs: " + ", ".join(formatted_motifs) + "."
                        observations.append(Observation(
                            category="tactical_motifs",
                            severity="warning",
                            text=obs_text
                        ))

    summary = _build_summary(board, observations, engine_analysis)

    return {
        "summary": summary,
        "observations": [obs.to_dict() for obs in observations],
    }


# ------------------------------------------------------------------
# Material
# ------------------------------------------------------------------

def _assess_material(board: chess.Board) -> list[Observation]:
    """Count material and detect imbalances."""
    obs: list[Observation] = []

    white_material = 0.0
    black_material = 0.0
    white_pieces: dict[int, int] = {}
    black_pieces: dict[int, int] = {}

    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None or piece.piece_type == chess.KING:
            continue
        val = PIECE_VALUES.get(piece.piece_type, 0)
        if piece.color == chess.WHITE:
            white_material += val
            white_pieces[piece.piece_type] = white_pieces.get(piece.piece_type, 0) + 1
        else:
            black_material += val
            black_pieces[piece.piece_type] = black_pieces.get(piece.piece_type, 0) + 1

    diff = white_material - black_material

    if abs(diff) >= 3.0:
        side = "White" if diff > 0 else "Black"
        obs.append(Observation(
            "material", "critical",
            f"{side} is up significant material ({abs(diff):.1f} points). "
            f"This is likely a decisive advantage if converted properly.",
        ))
    elif abs(diff) >= 1.0:
        side = "White" if diff > 0 else "Black"
        obs.append(Observation(
            "material", "warning",
            f"{side} is ahead by {abs(diff):.1f} points of material. "
            f"Accurate play is required to convert this edge.",
        ))
    else:
        obs.append(Observation(
            "material", "info",
            "Material is roughly equal.",
        ))

    # Bishop pair
    wb = white_pieces.get(chess.BISHOP, 0)
    bb = black_pieces.get(chess.BISHOP, 0)
    if wb >= 2 and bb < 2:
        obs.append(Observation(
            "material", "info",
            "White has the bishop pair — a meaningful advantage in open "
            "positions where the bishops can sweep across long diagonals.",
        ))
    elif bb >= 2 and wb < 2:
        obs.append(Observation(
            "material", "info",
            "Black has the bishop pair, providing long-range potential, "
            "especially if the position opens up.",
        ))

    # Exchange imbalance (rook vs minor piece)
    wr = white_pieces.get(chess.ROOK, 0)
    br = black_pieces.get(chess.ROOK, 0)
    wm = white_pieces.get(chess.KNIGHT, 0) + wb
    bm = black_pieces.get(chess.KNIGHT, 0) + bb
    if wr > br and bm > wm:
        obs.append(Observation(
            "material", "info",
            "White has the exchange (rook vs. minor piece). Rooks thrive "
            "on open files and in endgames.",
        ))
    elif br > wr and wm > bm:
        obs.append(Observation(
            "material", "info",
            "Black has the exchange. Look for open files and active rook play.",
        ))

    return obs


# ------------------------------------------------------------------
# Centre control
# ------------------------------------------------------------------

def _assess_center_control(board: chess.Board) -> list[Observation]:
    """Evaluate occupation and attack on the d4/d5/e4/e5 complex."""
    obs: list[Observation] = []
    centre_names = [chess.square_name(sq) for sq in CENTRE]

    white_control = 0
    black_control = 0

    for sq in CENTRE:
        piece = board.piece_at(sq)
        if piece is not None:
            if piece.color == chess.WHITE:
                white_control += 2  # occupation counts double
            else:
                black_control += 2

        white_control += len(board.attackers(chess.WHITE, sq))
        black_control += len(board.attackers(chess.BLACK, sq))

    delta = white_control - black_control

    if delta >= 4:
        obs.append(Observation(
            "center_control", "warning",
            "White dominates the centre with both occupation and piece pressure. "
            "This space advantage can translate to a kingside or queenside attack.",
            squares=centre_names,
        ))
    elif delta <= -4:
        obs.append(Observation(
            "center_control", "warning",
            "Black has seized firm control of the centre. White needs to "
            "challenge this with a pawn break or piece regrouping.",
            squares=centre_names,
        ))
    elif abs(delta) <= 1:
        obs.append(Observation(
            "center_control", "info",
            "The centre is evenly contested — both sides share control of the "
            "key d4/d5/e4/e5 squares.",
            squares=centre_names,
        ))
    else:
        better = "White" if delta > 0 else "Black"
        obs.append(Observation(
            "center_control", "info",
            f"{better} enjoys a slight edge in central control. Look for ways "
            f"to consolidate or challenge it with a pawn break.",
            squares=centre_names,
        ))

    # Specific pawn presence on e4/d4 or e5/d5
    for sq in CENTRE:
        piece = board.piece_at(sq)
        if piece is not None and piece.piece_type == chess.PAWN:
            name = chess.square_name(sq)
            color = "White" if piece.color == chess.WHITE else "Black"
            obs.append(Observation(
                "center_control", "info",
                f"{color} has a pawn anchored on {name}, contributing to "
                f"central space advantage.",
                squares=[name],
            ))

    return obs


# ------------------------------------------------------------------
# Pawn structure
# ------------------------------------------------------------------

def _assess_pawn_structure(board: chess.Board) -> list[Observation]:
    """Detect structural features: isolated, doubled, backward, passed pawns, chains."""
    obs: list[Observation] = []

    for color in [chess.WHITE, chess.BLACK]:
        color_name = "White" if color == chess.WHITE else "Black"
        pawns = list(board.pieces(chess.PAWN, color))
        pawn_files = [chess.square_file(sq) for sq in pawns]

        # --- Doubled pawns ---
        file_counts = Counter(pawn_files)
        for f, count in file_counts.items():
            if count >= 2:
                file_letter = chr(ord('a') + f)
                doubled_squares = [
                    chess.square_name(sq) for sq in pawns
                    if chess.square_file(sq) == f
                ]
                obs.append(Observation(
                    "pawn_structure", "warning",
                    f"{color_name} has doubled pawns on the {file_letter}-file. "
                    f"These are typically a static weakness — they cannot protect "
                    f"each other and may become targets in an endgame.",
                    squares=doubled_squares,
                ))

        # --- Isolated pawns ---
        for sq in pawns:
            f = chess.square_file(sq)
            adjacent_files = [af for af in [f - 1, f + 1] if 0 <= af <= 7]
            has_neighbour = any(af in pawn_files for af in adjacent_files)
            if not has_neighbour:
                name = chess.square_name(sq)
                obs.append(Observation(
                    "pawn_structure", "warning",
                    f"{color_name}'s {name}-pawn is isolated — no friendly pawns "
                    f"on adjacent files can support it. It must be defended by "
                    f"pieces, tying them down.",
                    squares=[name],
                ))

        # --- Backward pawns ---
        for sq in pawns:
            f = chess.square_file(sq)
            r = chess.square_rank(sq)
            adjacent_files = [af for af in [f - 1, f + 1] if 0 <= af <= 7]
            # A pawn is backward if no friendly pawn on adjacent files is
            # behind or equal rank, AND the stop square is controlled by enemy pawn
            friendly_ranks = [
                chess.square_rank(p) for p in pawns
                if chess.square_file(p) in adjacent_files
            ]
            if friendly_ranks:
                if color == chess.WHITE and all(fr > r for fr in friendly_ranks):
                    stop_sq = sq + 8  # one rank ahead
                    if stop_sq < 64:
                        enemy_attackers = board.attackers(chess.BLACK, stop_sq)
                        if any(board.piece_at(a) and board.piece_at(a).piece_type == chess.PAWN
                               for a in enemy_attackers):
                            name = chess.square_name(sq)
                            obs.append(Observation(
                                "pawn_structure", "warning",
                                f"{color_name}'s pawn on {name} is backward — it "
                                f"cannot advance safely because the stop square is "
                                f"controlled by an enemy pawn.",
                                squares=[name],
                            ))
                elif color == chess.BLACK and all(fr < r for fr in friendly_ranks):
                    stop_sq = sq - 8
                    if stop_sq >= 0:
                        enemy_attackers = board.attackers(chess.WHITE, stop_sq)
                        if any(board.piece_at(a) and board.piece_at(a).piece_type == chess.PAWN
                               for a in enemy_attackers):
                            name = chess.square_name(sq)
                            obs.append(Observation(
                                "pawn_structure", "warning",
                                f"{color_name}'s pawn on {name} is backward and "
                                f"cannot advance without being captured.",
                                squares=[name],
                            ))

        # --- Passed pawns ---
        for sq in pawns:
            f = chess.square_file(sq)
            r = chess.square_rank(sq)
            files_to_check = [af for af in [f - 1, f, f + 1] if 0 <= af <= 7]
            is_passed = True
            enemy_color = not color
            enemy_pawns = list(board.pieces(chess.PAWN, enemy_color))

            for ep in enemy_pawns:
                ef = chess.square_file(ep)
                er = chess.square_rank(ep)
                if ef in files_to_check:
                    if color == chess.WHITE and er > r:
                        is_passed = False
                        break
                    elif color == chess.BLACK and er < r:
                        is_passed = False
                        break

            if is_passed:
                name = chess.square_name(sq)
                # How advanced is it?
                advance = r if color == chess.WHITE else (7 - r)
                severity = "warning" if advance >= 4 else "info"
                obs.append(Observation(
                    "pawn_structure", severity,
                    f"{color_name} has a passed pawn on {name}! "
                    f"{'It is dangerously advanced and may soon promote.' if advance >= 5 else 'Passed pawns must be pushed — they tie down the opponent.'} ",
                    squares=[name],
                ))

    return obs


# ------------------------------------------------------------------
# Piece activity
# ------------------------------------------------------------------

def _assess_piece_activity(board: chess.Board) -> list[Observation]:
    """Evaluate piece placement: mobility, outposts, open files, fianchetto."""
    obs: list[Observation] = []

    for color in [chess.WHITE, chess.BLACK]:
        color_name = "White" if color == chess.WHITE else "Black"
        enemy = not color

        # --- Mobility per piece ---
        temp_board = board.copy()
        temp_board.turn = color
        temp_board.ep_square = None  # avoid artefacts from turn flip

        mobility: dict[int, int] = {}
        for move in temp_board.legal_moves:
            piece = temp_board.piece_at(move.from_square)
            if piece and piece.color == color and piece.piece_type != chess.KING:
                mobility[move.from_square] = mobility.get(move.from_square, 0) + 1

        # Find pieces on the board that have very low mobility
        for sq in board.pieces(chess.KNIGHT, color) | board.pieces(chess.BISHOP, color):
            moves = mobility.get(sq, 0)
            name = chess.square_name(sq)
            piece = board.piece_at(sq)
            pname = chess.piece_name(piece.piece_type).capitalize()
            if moves <= 1:
                obs.append(Observation(
                    "piece_activity", "warning",
                    f"{color_name}'s {pname} on {name} is nearly trapped "
                    f"with only {moves} legal move{'s' if moves != 1 else ''}. "
                    f"Consider re-routing it to a better square.",
                    squares=[name],
                ))
            elif moves >= 6:
                obs.append(Observation(
                    "piece_activity", "info",
                    f"{color_name}'s {pname} on {name} is very active with "
                    f"{moves} available moves — excellent piece harmony.",
                    squares=[name],
                ))

        # --- Knight outposts ---
        for sq in board.pieces(chess.KNIGHT, color):
            r = chess.square_rank(sq)
            f = chess.square_file(sq)
            name = chess.square_name(sq)
            # Outpost: on enemy half, not attackable by enemy pawns
            in_enemy_half = (r >= 4) if color == chess.WHITE else (r <= 3)
            if in_enemy_half:
                adjacent_files = [af for af in [f - 1, f + 1] if 0 <= af <= 7]
                can_be_attacked = False
                for ep in board.pieces(chess.PAWN, enemy):
                    ef = chess.square_file(ep)
                    er = chess.square_rank(ep)
                    if ef in adjacent_files:
                        # Enemy pawn could potentially advance to attack
                        if color == chess.WHITE and er > r:
                            can_be_attacked = True
                        elif color == chess.BLACK and er < r:
                            can_be_attacked = True
                if not can_be_attacked:
                    obs.append(Observation(
                        "piece_activity", "info",
                        f"{color_name}'s knight on {name} occupies a powerful "
                        f"outpost — no enemy pawns can challenge it. This is "
                        f"a semi-permanent advantage.",
                        squares=[name],
                    ))

        # --- Rooks on open/semi-open files ---
        for sq in board.pieces(chess.ROOK, color):
            f = chess.square_file(sq)
            name = chess.square_name(sq)
            file_letter = chr(ord('a') + f)
            friendly_pawns_on_file = any(
                chess.square_file(p) == f for p in board.pieces(chess.PAWN, color)
            )
            enemy_pawns_on_file = any(
                chess.square_file(p) == f for p in board.pieces(chess.PAWN, enemy)
            )
            if not friendly_pawns_on_file and not enemy_pawns_on_file:
                obs.append(Observation(
                    "piece_activity", "info",
                    f"{color_name}'s rook on {name} sits on the fully open "
                    f"{file_letter}-file — ideal for penetration and pressure.",
                    squares=[name],
                ))
            elif not friendly_pawns_on_file:
                obs.append(Observation(
                    "piece_activity", "info",
                    f"{color_name}'s rook on {name} is on the semi-open "
                    f"{file_letter}-file, putting pressure on the enemy pawn.",
                    squares=[name],
                ))

        # --- Fianchettoed bishops ---
        fianchetto_squares = {
            chess.WHITE: [(chess.G2, chess.BISHOP), (chess.B2, chess.BISHOP)],
            chess.BLACK: [(chess.G7, chess.BISHOP), (chess.B7, chess.BISHOP)],
        }
        for sq, pt in fianchetto_squares[color]:
            piece = board.piece_at(sq)
            if piece and piece.piece_type == pt and piece.color == color:
                name = chess.square_name(sq)
                obs.append(Observation(
                    "piece_activity", "info",
                    f"{color_name} has a fianchettoed bishop on {name}, "
                    f"controlling the long diagonal. This is especially "
                    f"strong when the centre pawns are exchanged.",
                    squares=[name],
                ))

    return obs


# ------------------------------------------------------------------
# King safety
# ------------------------------------------------------------------

def _assess_king_safety(board: chess.Board) -> list[Observation]:
    """Evaluate pawn shelter, open files near king, castling status."""
    obs: list[Observation] = []

    for color in [chess.WHITE, chess.BLACK]:
        color_name = "White" if color == chess.WHITE else "Black"
        enemy = not color
        king_sq = board.king(color)
        if king_sq is None:
            continue

        king_name = chess.square_name(king_sq)
        king_file = chess.square_file(king_sq)

        # --- Castling rights ---
        has_castled = False
        if color == chess.WHITE:
            # If king is on g1/c1, it likely has castled
            has_castled = king_sq in (chess.G1, chess.C1)
            can_castle = board.has_kingside_castling_rights(chess.WHITE) or \
                         board.has_queenside_castling_rights(chess.WHITE)
        else:
            has_castled = king_sq in (chess.G8, chess.C8)
            can_castle = board.has_kingside_castling_rights(chess.BLACK) or \
                         board.has_queenside_castling_rights(chess.BLACK)

        if not has_castled and can_castle:
            obs.append(Observation(
                "king_safety", "info",
                f"{color_name} has not yet castled but retains castling rights. "
                f"Castling should be a priority to connect the rooks and "
                f"shelter the king.",
                squares=[king_name],
            ))
        elif not has_castled and not can_castle:
            # King in the centre without castling rights
            king_rank = chess.square_rank(king_sq)
            is_central = 2 <= king_file <= 5
            back_rank = (king_rank == 0 and color == chess.WHITE) or \
                        (king_rank == 7 and color == chess.BLACK)
            if is_central and back_rank:
                obs.append(Observation(
                    "king_safety", "critical",
                    f"{color_name}'s king is stuck in the centre without castling "
                    f"rights — a serious liability if the position opens up. "
                    f"The opponent should try to open the centre immediately.",
                    squares=[king_name],
                ))

        # --- Pawn shelter ---
        shelter_squares = KING_SHELTER.get(king_sq)
        if shelter_squares:
            missing_shelter = []
            for ssq in shelter_squares:
                piece = board.piece_at(ssq)
                if piece is None or piece.piece_type != chess.PAWN or piece.color != color:
                    missing_shelter.append(chess.square_name(ssq))

            if len(missing_shelter) >= 2:
                obs.append(Observation(
                    "king_safety", "warning",
                    f"{color_name}'s king shelter is compromised — pawns are "
                    f"missing from {', '.join(missing_shelter)}. This weakens "
                    f"the king's protection and invites attacking ideas.",
                    squares=missing_shelter + [king_name],
                ))
            elif len(missing_shelter) == 1:
                obs.append(Observation(
                    "king_safety", "info",
                    f"{color_name} is missing a shelter pawn on "
                    f"{missing_shelter[0]}. While not immediately dangerous, "
                    f"it could become a target for a pawn storm.",
                    squares=missing_shelter + [king_name],
                ))

        # --- Open files near king ---
        nearby_files = [f for f in [king_file - 1, king_file, king_file + 1]
                        if 0 <= f <= 7]
        for f in nearby_files:
            file_letter = chr(ord('a') + f)
            has_any_pawn = any(
                chess.square_file(p) == f
                for p in board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)
            )
            if not has_any_pawn:
                # Check if enemy has a rook or queen that could use this file
                enemy_heavy = board.pieces(chess.ROOK, enemy) | board.pieces(chess.QUEEN, enemy)
                if enemy_heavy:
                    obs.append(Observation(
                        "king_safety", "warning",
                        f"The {file_letter}-file near {color_name}'s king is "
                        f"wide open — the opponent's heavy pieces could "
                        f"infiltrate along this file.",
                        squares=[king_name],
                    ))

    return obs


# ------------------------------------------------------------------
# Summary builder
# ------------------------------------------------------------------

def _build_summary(
    board: chess.Board,
    observations: list[Observation],
    engine_analysis: Optional[dict] = None,
) -> str:
    """
    Combine the most important observations into a 1-2 sentence
    high-level assessment in GM coaching language.
    """
    parts: list[str] = []

    # Engine eval context
    if engine_analysis:
        ev = engine_analysis.get("evaluation", 0)
        if isinstance(ev, str) and ev.startswith("M"):
            mate_in = ev[1:]
            parts.append(f"There is a forced mate in {mate_in}.")
        elif isinstance(ev, (int, float)):
            if ev > 100:
                parts.append("White has a clear advantage.")
            elif ev > 30:
                parts.append("White is slightly better.")
            elif ev < -100:
                parts.append("Black has a clear advantage.")
            elif ev < -30:
                parts.append("Black is slightly better.")
            else:
                parts.append("The position is roughly equal.")

    # Pick most impactful observations
    critical = [o for o in observations if o.severity == "critical"]
    warnings = [o for o in observations if o.severity == "warning"]

    if critical:
        parts.append(critical[0].text.split(".")[0] + ".")

    elif warnings:
        # Pick the two most interesting warnings from different categories
        seen_cats: set[str] = set()
        for w in warnings:
            if w.category not in seen_cats and len(parts) < 3:
                first_sentence = w.text.split(".")[0] + "."
                parts.append(first_sentence)
                seen_cats.add(w.category)

    if not parts:
        # Fallback
        if board.fullmove_number <= 5:
            parts.append(
                "We are still in the opening phase — focus on development, "
                "central control, and king safety."
            )
        else:
            parts.append(
                "The position is balanced with chances for both sides."
            )

    return " ".join(parts)
