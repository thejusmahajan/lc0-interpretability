"""Position encoder/decoder for configuration steering.

Encodes a chess.Board into 18 uint64 bitboards from the perspective of the side to move.
Plane order:
  0-5   our   P N B R Q K
  6-11  their P N B R Q K
  12-15 castling: our K-side, our Q-side, their K-side, their Q-side (all-ones or all-zeros)
  16    en-passant target square (single bit, or empty)
  17    all ones (bias/padding plane)

When black is to move, the board is mirrored vertically AND colours swapped (via chess.Board.mirror()),
so that 'our' pieces always advance up the board.
"""

from __future__ import annotations

import chess
import numpy as np

ALL_ONES: np.uint64 = np.uint64(0xFFFFFFFFFFFFFFFF)
ALL_ZEROS: np.uint64 = np.uint64(0)

PIECE_TYPES = [
    chess.PAWN,
    chess.KNIGHT,
    chess.BISHOP,
    chess.ROOK,
    chess.QUEEN,
    chess.KING,
]


def encode(board: chess.Board) -> np.ndarray:
    """Encode a chess.Board into 18 uint64 bitboards (shape (18,), dtype uint64).

    Always from the side-to-move's perspective (mirrored vertically and color-swapped
    if black is to move).
    """
    b = board.mirror() if board.turn == chess.BLACK else board

    bb = np.zeros(18, dtype=np.uint64)

    # Planes 0-5: our P N B R Q K (White on canonical board b)
    for i, pt in enumerate(PIECE_TYPES):
        bb[i] = np.uint64(b.pieces_mask(pt, chess.WHITE))

    # Planes 6-11: their P N B R Q K (Black on canonical board b)
    for i, pt in enumerate(PIECE_TYPES):
        bb[6 + i] = np.uint64(b.pieces_mask(pt, chess.BLACK))

    # Planes 12-15: castling rights (our K, our Q, their K, their Q)
    bb[12] = ALL_ONES if b.has_kingside_castling_rights(chess.WHITE) else ALL_ZEROS
    bb[13] = ALL_ONES if b.has_queenside_castling_rights(chess.WHITE) else ALL_ZEROS
    bb[14] = ALL_ONES if b.has_kingside_castling_rights(chess.BLACK) else ALL_ZEROS
    bb[15] = ALL_ONES if b.has_queenside_castling_rights(chess.BLACK) else ALL_ZEROS

    # Plane 16: en-passant target square
    if b.ep_square is not None:
        bb[16] = np.uint64(1 << b.ep_square)
    else:
        bb[16] = ALL_ZEROS

    # Plane 17: bias / all ones
    bb[17] = ALL_ONES

    return bb


def decode(bb: np.ndarray) -> chess.Board:
    """Decode 18 uint64 bitboards back to a canonical chess.Board (White to move).

    Restores piece placement, canonical turn (chess.WHITE), castling rights, and ep target.
    """
    board = chess.Board(None)
    board.turn = chess.WHITE

    # Restore pieces
    for i, pt in enumerate(PIECE_TYPES):
        mask_our = int(bb[i])
        for sq in chess.scan_forward(mask_our):
            board.set_piece_at(sq, chess.Piece(pt, chess.WHITE))

        mask_their = int(bb[6 + i])
        for sq in chess.scan_forward(mask_their):
            board.set_piece_at(sq, chess.Piece(pt, chess.BLACK))

    # Restore castling rights
    castling_fen = ""
    if bb[12] != 0:
        castling_fen += "K"
    if bb[13] != 0:
        castling_fen += "Q"
    if bb[14] != 0:
        castling_fen += "k"
    if bb[15] != 0:
        castling_fen += "q"
    board.set_castling_fen(castling_fen if castling_fen else "-")

    # Restore ep square
    if bb[16] != 0:
        board.ep_square = int(bb[16]).bit_length() - 1
    else:
        board.ep_square = None

    return board


def unpack(bb: np.ndarray) -> np.ndarray:
    """Unpack 18 uint64 bitboards into float32 planes of shape (18, 8, 8).

    Index convention: [plane, rank, file], where rank 0 is rank 1, file 0 is file a.
    """
    arr = np.zeros((18, 8, 8), dtype=np.float32)
    for p in range(18):
        val = int(bb[p])
        if val == 0:
            continue
        for sq in range(64):
            if (val >> sq) & 1:
                rank = sq // 8
                file = sq % 8
                arr[p, rank, file] = 1.0
    return arr
