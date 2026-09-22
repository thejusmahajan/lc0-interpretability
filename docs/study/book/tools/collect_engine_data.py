"""Collect REAL engine numbers used in the self-tutor book.

Every table of numbers printed in `neural_chess_self_tutor.pdf` that claims to be
engine output is produced by this script. Nothing is typed by hand. Re-run it to
regenerate `data/engine_data.json`:

    python tools/collect_engine_data.py

Requires: engine/lc0.exe + weights, engine/stockfish/*.exe, python-chess.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import chess
import chess.engine

REPO = Path(__file__).resolve().parents[4]
ENGINE_DIR = REPO / "engine"
LC0 = ENGINE_DIR / "lc0.exe"
NET_SMALL = ENGINE_DIR / "791556.pb.gz"
SF = ENGINE_DIR / "stockfish" / "stockfish-windows-x86-64.exe"  # avx2 build crashes on this CPU
OUT = Path(__file__).resolve().parents[1] / "data" / "engine_data.json"

# --------------------------------------------------------------------------
# Positions used in the book. Keep the keys stable: the .tex files cite them.
# --------------------------------------------------------------------------


def opera_game_fens() -> dict:
    """Replay Morphy--Duke of Brunswick & Count Isouard, Paris 1858 (public domain)."""
    moves = (
        "e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 Qb3 Qe7 Nc3 c6 "
        "Bg5 b5 Nxb5 cxb5 Bxb5+ Nbd7 O-O-O Rd8 Rxd7 Rxd7 Rd1 Qe6 Bxd7+ Nxd7 "
        "Qb8+ Nxb8 Rd8#"
    ).split()
    board = chess.Board()
    fens = {}
    for i, san in enumerate(moves):
        if i == 30:  # position before 16.Qb8+
            fens["before_qb8"] = board.fen()
        if i == 22:  # position before 12.O-O-O
            fens["before_castle"] = board.fen()
        board.push_san(san)
    fens["final"] = board.fen()
    return fens


def build_positions() -> list[dict]:
    opera = opera_game_fens()
    return [
        {
            "key": "startpos",
            "fen": chess.STARTING_FEN,
            "label": "Initial position",
            "node_ladder": [1, 2, 4, 8, 16, 64, 256, 1600],
        },
        {
            "key": "kp_endgame",
            # White Ke6, Pe5, Black Ke8 -- four legal moves, small enough to
            # simulate by hand in chapter 7.
            "fen": "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1",
            "label": "King and pawn: White Ke6, Pe5 vs Black Ke8, White to move",
            "node_ladder": [1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 24, 32, 64, 128, 800],
        },
        {
            "key": "kp_endgame_black_to_move",
            "fen": "4k3/8/4K3/4P3/8/8/8/8 b - - 0 1",
            "label": "Same position, Black to move",
            "node_ladder": [16, 800],
        },
        {
            "key": "opposition_draw",
            # White Ke4, Pe5, Black Ke6: black holds the opposition.
            "fen": "8/8/4k3/4P3/4K3/8/8/8 w - - 0 1",
            "label": "Opposition: White Ke4, Pe5 vs Black Ke6, White to move",
            "node_ladder": [16, 128, 800],
        },
        {
            "key": "opera_before_qb8",
            "fen": opera["before_qb8"],
            "label": "Morphy--Brunswick/Isouard, Paris 1858, before 16.Qb8+",
            "node_ladder": [1, 2, 4, 8, 16, 32, 64, 128, 400, 1600, 6400],
        },
        {
            "key": "opera_before_castle",
            "fen": opera["before_castle"],
            "label": "Same game, before 12.O-O-O",
            "node_ladder": [16, 800],
        },
    ]


# --------------------------------------------------------------------------
# LC0 driver
# --------------------------------------------------------------------------

MOVE_RE = re.compile(r"^info string ([a-h][1-8][a-h][1-8][qrbn]?|node)\s+\(")


def _field(line: str, name: str):
    m = re.search(r"\(" + name + r":\s*(-?[\d.]+)%?", line)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_verbose(lines: list[str]) -> dict:
    """Turn lc0's --verbose-move-stats dump into structured per-move records."""
    moves, root = [], None
    for line in lines:
        if not MOVE_RE.match(line):
            continue
        name = line.split()[2]
        rec = {
            "move": name,
            "N": int(re.search(r"N:\s*(\d+)", line).group(1)),
            "P": _field(line, "P"),
            "WL": _field(line, "WL"),
            "D": _field(line, "D"),
            "M": _field(line, "M"),
            "Q": _field(line, "Q"),
            "U": _field(line, "U"),
            "S": _field(line, "S"),
            "V": _field(line, "V"),
        }
        if name == "node":
            root = rec
        else:
            moves.append(rec)
    moves.sort(key=lambda r: (-r["N"], -(r["P"] or 0)))
    return {"moves": moves, "root": root}


def lc0_run(fen: str, nodes: int, weights: Path = NET_SMALL, timeout: int = 300) -> dict:
    """One search at a fixed node budget; returns per-move N/P/Q/U/V."""
    cmd = [
        str(LC0),
        f"--weights={weights}",
        "--verbose-move-stats",
        "--threads=1",
        "--minibatch-size=1",
        "--max-collision-events=1",
        "--max-collision-visits=1",
        "--out-of-order-eval=false",
        "--task-workers=0",
        "--backend=blas",
    ]
    script = (
        "uci\n"
        "isready\n"
        f"position fen {fen}\n"
        f"go nodes {nodes}\n"
    )
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(ENGINE_DIR),
        bufsize=1,
    )
    assert proc.stdin and proc.stdout
    proc.stdin.write(script)
    proc.stdin.flush()

    lines, deadline, bestmove = [], time.time() + timeout, None
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.rstrip("\n")
        lines.append(line)
        if line.startswith("bestmove"):
            bestmove = line.split()[1]
            break
    try:
        proc.stdin.write("quit\n")
        proc.stdin.flush()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

    out = parse_verbose(lines)
    out["bestmove"] = bestmove
    out["nodes_requested"] = nodes
    return out


def lc0_policy_only(fen: str, weights: Path = NET_SMALL) -> dict:
    """`go nodes 1` expands the root and returns raw priors with no search."""
    return lc0_run(fen, 1, weights)


# --------------------------------------------------------------------------
# Stockfish ground truth (used to VERIFY every chess claim made in the book)
# --------------------------------------------------------------------------


def stockfish_verify(fen: str, depth: int = 30, multipv: int = 4) -> dict:
    board = chess.Board(fen)
    with chess.engine.SimpleEngine.popen_uci(str(SF)) as eng:
        info = eng.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
    out = []
    for entry in info:
        pv = entry.get("pv", [])
        score = entry["score"].pov(board.turn)
        out.append(
            {
                "move": board.san(pv[0]) if pv else None,
                "uci": pv[0].uci() if pv else None,
                "cp": score.score(),
                "mate": score.mate(),
                "pv_san": board.variation_san(pv[:10]) if pv else None,
            }
        )
    return {"depth": depth, "lines": out, "legal_moves": len(list(board.legal_moves))}


# --------------------------------------------------------------------------


def main() -> None:
    for path in (LC0, NET_SMALL, SF):
        if not path.exists():
            sys.exit(f"missing: {path}")

    positions = build_positions()
    data = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "positions": {}}

    for spec in positions:
        key = spec["key"]
        print(f"=== {key}: {spec['label']}", flush=True)
        board = chess.Board(spec["fen"])
        entry = {
            "label": spec["label"],
            "fen": spec["fen"],
            "side_to_move": "white" if board.turn else "black",
            "legal_moves_san": [board.san(m) for m in board.legal_moves],
            "n_legal": board.legal_moves.count(),
            "ladder": {},
        }
        for n in spec["node_ladder"]:
            t0 = time.time()
            res = lc0_run(spec["fen"], n)
            for rec in res["moves"]:
                try:
                    rec["san"] = board.san(chess.Move.from_uci(rec["move"]))
                except Exception:
                    rec["san"] = rec["move"]
            entry["ladder"][str(n)] = res
            print(f"    nodes={n:<5} best={res['bestmove']} ({time.time()-t0:.1f}s)", flush=True)
        print("    stockfish...", flush=True)
        entry["stockfish"] = stockfish_verify(spec["fen"])
        data["positions"][key] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
