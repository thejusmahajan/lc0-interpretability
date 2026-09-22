"""Second-ply data for the hand-simulation chapter.

For the king-and-pawn root used in chapter 7, collect the network's priors and
raw value V for every child position (and for the main line's grandchildren), so
that the by-hand simulation can be checked at two plies rather than one.
Writes data/children_data.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import chess

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_engine_data import lc0_run, stockfish_verify  # noqa: E402

ROOT_FEN = "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1"
OUT = Path(__file__).resolve().parents[1] / "data" / "children_data.json"


def describe(fen: str, nodes_list: list[int]) -> dict:
    board = chess.Board(fen)
    entry = {
        "fen": fen,
        "side_to_move": "white" if board.turn else "black",
        "n_legal": board.legal_moves.count(),
        "ladder": {},
    }
    for n in nodes_list:
        res = lc0_run(fen, n)
        for rec in res["moves"]:
            try:
                rec["san"] = board.san(chess.Move.from_uci(rec["move"]))
            except Exception:
                rec["san"] = rec["move"]
        entry["ladder"][str(n)] = res
    return entry


def main() -> None:
    root = chess.Board(ROOT_FEN)
    data = {"root_fen": ROOT_FEN, "children": {}, "grandchildren": {}}

    for move in root.legal_moves:
        san = root.san(move)
        board = root.copy()
        board.push(move)
        print("child", san, board.fen(), flush=True)
        entry = describe(board.fen(), [1, 16])
        entry["reached_by"] = san
        entry["stockfish"] = stockfish_verify(board.fen(), depth=26, multipv=3)
        data["children"][san] = entry

    # Grandchildren of the two serious moves: Kd6 and Kf6, following the
    # network's own top reply at 16 nodes.
    for san in ("Kd6", "Kf6"):
        child = data["children"][san]
        top = child["ladder"]["16"]["moves"][0]
        board = chess.Board(child["fen"])
        board.push(chess.Move.from_uci(top["move"]))
        print("grandchild", san, "->", top["san"], board.fen(), flush=True)
        entry = describe(board.fen(), [1])
        entry["reached_by"] = f"{san} {top['san']}"
        entry["stockfish"] = stockfish_verify(board.fen(), depth=26, multipv=2)
        data["grandchildren"][f"{san}_{top['san']}"] = entry

    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
