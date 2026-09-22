"""
Descriptive Notation Converter — Inverted Generator Engine for Pre-1930 English/German Chess Books.

Implements inverted move matching:
At each ply, enumerates board.legal_moves, renders each legal move into its acceptable
descriptive notation strings, and matches against the input token.
- Exactly 1 legal move matches -> play move.
- 0 or >1 matches -> do not guess; record parse failure.
"""

from typing import List, Set, Tuple, Optional, Dict, Any
import re
import chess
import chess.pgn


FILE_CODES = {
    0: ["QR", "R", "a"],
    1: ["QN", "QKt", "Kt", "N", "b"],
    2: ["QB", "B", "c"],
    3: ["Q", "d"],
    4: ["K", "e"],
    5: ["KB", "B", "f"],
    6: ["KN", "KKt", "Kt", "N", "g"],
    7: ["KR", "R", "h"],
}

PIECE_CODES = {
    chess.PAWN: ["P"],
    chess.KNIGHT: ["N", "Kt"],
    chess.BISHOP: ["B"],
    chess.ROOK: ["R"],
    chess.QUEEN: ["Q"],
    chess.KING: ["K"],
}


def _normalize_token(token: str) -> str:
    """Strip annotation symbols (!, ?, !?), quotes, parens around token, whitespace, and collapse spaced descriptive moves."""
    t = token.strip()
    t = re.sub(r"[!?]+$", "", t)
    t = re.sub(r"^[!?]+", "", t)
    t = re.sub(r"\b([KQ])\s+([RBN]|Kt)\b", r"\1\2", t, flags=re.IGNORECASE)
    t = re.sub(r"([A-Za-z0-9])\s*-\s*([A-Za-z0-9])", r"\1-\2", t)
    t = re.sub(r"([A-Za-z])\s+([0-9])", r"\1\2", t)
    return t.strip()


def to_descriptive(board: chess.Board, move: chess.Move) -> Set[str]:
    """
    Generate all valid descriptive notation renderings for a legal move in the given position.
    """
    renderings: Set[str] = set()
    color = board.turn
    from_sq = move.from_square
    to_sq = move.to_square
    piece = board.piece_at(from_sq)
    if not piece:
        return renderings

    from_file = chess.square_file(from_sq)
    from_rank = chess.square_rank(from_sq)
    to_file = chess.square_file(to_sq)
    to_rank = chess.square_rank(to_sq)

    mover_rank = (to_rank + 1) if color == chess.WHITE else (8 - to_rank)
    from_mover_rank = (from_rank + 1) if color == chess.WHITE else (8 - from_rank)

    # 1. Castling
    if board.is_castling(move):
        if to_file > from_file:
            renderings.update(["O-O", "0-0", "Castles", "Castles KR", "K-Kt sq", "K-N sq"])
        else:
            renderings.update(["O-O-O", "0-0-0", "Castles QR", "Q-R sq", "Castles Q"])
        return renderings

    is_cap = board.is_capture(move)
    if is_cap:
        if board.is_en_passant(move):
            cap_types = [chess.PAWN]
        else:
            cap_piece = board.piece_at(to_sq)
            cap_types = [cap_piece.piece_type] if cap_piece else [chess.PAWN]
    else:
        cap_types = []

    p_letters = PIECE_CODES.get(piece.piece_type, [])
    to_files = FILE_CODES[to_file]

    # Specific piece prefixes for disambiguation (e.g. KKt, QKt, QR, KR, QB, KB)
    from_piece_prefixes = []
    if piece.piece_type == chess.KNIGHT:
        if from_file in (4, 5, 6, 7):
            from_piece_prefixes.extend(["KKt", "KN"])
        if from_file in (0, 1, 2, 3):
            from_piece_prefixes.extend(["QKt", "QN"])
    elif piece.piece_type == chess.ROOK:
        if from_file in (4, 5, 6, 7):
            from_piece_prefixes.extend(["KR"])
        if from_file in (0, 1, 2, 3):
            from_piece_prefixes.extend(["QR"])
    elif piece.piece_type == chess.BISHOP:
        if from_file in (4, 5, 6, 7):
            from_piece_prefixes.extend(["KB"])
        if from_file in (0, 1, 2, 3):
            from_piece_prefixes.extend(["QB"])
    elif piece.piece_type == chess.PAWN:
        if from_file == 0: from_piece_prefixes.extend(["QRP", "RP"])
        elif from_file == 1: from_piece_prefixes.extend(["QNP", "QKtP", "NP", "KtP"])
        elif from_file == 2: from_piece_prefixes.extend(["QBP", "BP"])
        elif from_file == 3: from_piece_prefixes.extend(["QP"])
        elif from_file == 4: from_piece_prefixes.extend(["KP"])
        elif from_file == 5: from_piece_prefixes.extend(["KBP", "BP"])
        elif from_file == 6: from_piece_prefixes.extend(["KNP", "KKtP", "NP", "KtP"])
        elif from_file == 7: from_piece_prefixes.extend(["KRP", "RP"])

    promo_suffixes = []
    if move.promotion:
        for p_code in PIECE_CODES.get(move.promotion, []):
            promo_suffixes.extend([f"({p_code})", f"={p_code}", f"{p_code}"])
    else:
        promo_suffixes = [""]

    for p_str in p_letters:
        for f_code in to_files:
            sq_desc = f"{f_code}{mover_rank}"
            sq_desc_sq = f"{f_code} sq" if mover_rank == 1 else None

            for p_suf in promo_suffixes:
                if not is_cap:
                    # Normal moves
                    renderings.add(f"{p_str}-{sq_desc}{p_suf}")
                    if sq_desc_sq:
                        renderings.add(f"{p_str}-{sq_desc_sq}{p_suf}")

                    for pref in from_piece_prefixes:
                        renderings.add(f"{pref}-{sq_desc}{p_suf}")
                        renderings.add(f"{pref}({from_mover_rank})-{sq_desc}{p_suf}")

                    renderings.add(f"{p_str}({from_mover_rank})-{sq_desc}{p_suf}")
                    renderings.add(f"{p_str}/{from_mover_rank}-{sq_desc}{p_suf}")
                else:
                    # Captures
                    for cap_type in cap_types:
                        for cap_str in PIECE_CODES.get(cap_type, []):
                            renderings.add(f"{p_str}x{cap_str}{p_suf}")
                            renderings.add(f"{p_str}x{sq_desc}{p_suf}")

                            for pref in from_piece_prefixes:
                                renderings.add(f"{pref}x{cap_str}{p_suf}")
                                renderings.add(f"{pref}x{sq_desc}{p_suf}")

                            if board.is_en_passant(move):
                                renderings.add(f"{p_str}x{cap_str} e.p.{p_suf}")
                                renderings.add(f"{p_str}x{cap_str} e.p{p_suf}")
                                renderings.add(f"{p_str}x{cap_str} ep{p_suf}")

    # Case variants and check/mate variations
    final_renderings: Set[str] = set()
    for r in renderings:
        final_renderings.add(r)
        final_renderings.add(r.upper())
        final_renderings.add(r.lower())

        if board.gives_check(move):
            for check_suf in (" ch", "ch", "+", " dbl ch", " dis ch", " mate", "#"):
                final_renderings.add(r + check_suf)
                final_renderings.add(r.lower() + check_suf)

    return final_renderings


def match_descriptive_move(board: chess.Board, token: str) -> Tuple[Optional[chess.Move], List[chess.Move]]:
    """
    Match descriptive token against all legal moves on board.
    Returns (matched_move, list_of_all_matching_legal_moves).
    """
    norm_token = _normalize_token(token)
    clean_token = re.sub(r"\s*(?:ch|dbl ch|dis ch|mate|\+|\#)$", "", norm_token, flags=re.IGNORECASE).strip()
    has_check_mark = norm_token != clean_token

    # 1. First pass: exact norm_token match
    exact_matches = []
    for move in board.legal_moves:
        renderings = to_descriptive(board, move)
        if norm_token in renderings or norm_token.lower() in renderings:
            exact_matches.append(move)

    if len(exact_matches) == 1:
        return exact_matches[0], exact_matches
    elif len(exact_matches) > 1:
        return None, exact_matches

    # 2. Second pass: clean_token / condensed match
    condensed_matches = []
    condensed_token = norm_token.replace("-", "").replace(" ", "").lower()
    condensed_clean = clean_token.replace("-", "").replace(" ", "").lower()

    for move in board.legal_moves:
        renderings = to_descriptive(board, move)
        matched = False
        if not has_check_mark and (clean_token in renderings or clean_token.lower() in renderings):
            matched = True
        else:
            for r in renderings:
                r_condensed = r.replace("-", "").replace(" ", "").lower()
                if condensed_token == r_condensed or (not has_check_mark and condensed_clean == r_condensed):
                    matched = True
                    break
        if matched:
            condensed_matches.append(move)

    if len(condensed_matches) == 1:
        return condensed_matches[0], condensed_matches

    return None, condensed_matches


def parse_descriptive_game(tokens: List[str], headers: Optional[Dict[str, str]] = None) -> Tuple[Optional[chess.pgn.Game], List[Dict[str, Any]]]:
    """
    Parse a list of descriptive move tokens into a python-chess Game.
    Returns (game, list_of_failures).
    """
    board = chess.Board()
    game = chess.pgn.Game()
    if headers:
        for k, v in headers.items():
            game.headers[k] = v

    node = game
    failures = []

    for ply_idx, raw_token in enumerate(tokens):
        token = raw_token.strip()
        if not token:
            continue

        move, matches = match_descriptive_move(board, token)

        if move is None:
            failures.append({
                "ply": ply_idx + 1,
                "move_number": (ply_idx // 2) + 1,
                "color": "white" if board.turn == chess.WHITE else "black",
                "token": raw_token,
                "matches_count": len(matches),
                "matching_moves": [board.san(m) for m in matches],
                "fen": board.fen(),
            })
            return None, failures

        board.push(move)
        node = node.add_variation(move)

    return game, failures
