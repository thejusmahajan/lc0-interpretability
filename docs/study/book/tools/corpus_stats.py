"""Measure the real branching factor of the user's own games.

The book quotes "about 30 legal moves" everywhere; this measures it on the
9k-game corpus instead of repeating folklore. Writes data/corpus_stats.json.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

import chess
import chess.pgn

REPO = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1] / "data" / "corpus_stats.json"


def find_pgns() -> list[Path]:
    pats = ["games_of_derdiedasdie/*.pgn", "data/*.pgn", "*.pgn"]
    files: list[Path] = []
    for p in pats:
        files.extend(sorted(REPO.glob(p)))
    return [f for f in files if f.stat().st_size > 1000]


def main() -> None:
    files = find_pgns()
    if not files:
        raise SystemExit("no PGN found")

    counts: list[int] = []
    by_movenum: dict[int, list[int]] = {}
    game_lengths: list[int] = []
    games = 0
    phase = {"opening": [], "middlegame": [], "endgame": []}

    for path in files:
        with path.open(encoding="utf-8", errors="replace") as fh:
            while True:
                game = chess.pgn.read_game(fh)
                if game is None:
                    break
                games += 1
                board = game.board()
                plies = 0
                for move in game.mainline_moves():
                    n = board.legal_moves.count()
                    counts.append(n)
                    by_movenum.setdefault(board.fullmove_number, []).append(n)
                    npieces = len(board.piece_map())
                    if board.fullmove_number <= 12:
                        phase["opening"].append(n)
                    elif npieces <= 12:
                        phase["endgame"].append(n)
                    else:
                        phase["middlegame"].append(n)
                    board.push(move)
                    plies += 1
                game_lengths.append(plies)

    hist = Counter(counts)
    out = {
        "files": [str(f.relative_to(REPO)) for f in files],
        "games": games,
        "positions": len(counts),
        "mean_legal_moves": round(statistics.mean(counts), 2),
        "median_legal_moves": statistics.median(counts),
        "max_legal_moves": max(counts),
        "min_legal_moves": min(counts),
        "mean_plies_per_game": round(statistics.mean(game_lengths), 1),
        "phase_means": {k: round(statistics.mean(v), 2) for k, v in phase.items() if v},
        "phase_n": {k: len(v) for k, v in phase.items()},
        "by_movenum_mean": {
            str(k): round(statistics.mean(v), 2)
            for k, v in sorted(by_movenum.items())
            if k <= 60 and len(v) >= 20
        },
        "histogram": {str(k): hist[k] for k in sorted(hist)},
    }
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k, v in out.items():
        if k not in ("histogram", "by_movenum_mean", "files"):
            print(k, "=", v)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
