"""Puzzle Storm / Racer regime — curate lichess puzzles and drill them on a clock.

The gap this targets: a 2350 untimed puzzle rating with failures in the
1500-2000 band under Storm/Racer time pressure is not a calculation problem,
it is a *retrieval* problem. Untimed, you calculate your way to the answer;
at 10 seconds you either recognise the shape or you don't. So every deck here
is drilled against a shot clock, and the log records time-to-answer, not just
correctness.

Two deck families:

  theme decks   — straight from lichess' own theme tags.
  derived decks — computed here with python-chess, because the thing that
                  actually kills Storm runs has no lichess tag: the solution
                  whose first move is neither a check nor a capture. Under a
                  clock everyone plays the forcing move first; these are the
                  positions that punish it. See DERIVED_DECKS.

Puzzle-position convention (lichess): the CSV `fen` is the position *before*
the opponent's blunder. moves[0] is that blunder; the solver is to move after
it, and plays moves[1], moves[3], ... Getting this wrong shifts every puzzle
by one ply, so it lives in one place: puzzle_position().

Storage, all under data/puzzles/regime/:
  decks/<name>.json  — curated deck (puzzle rows + deck metadata)
  sessions.jsonl     — one record per attempt, append-only, with elapsed time
  srs.json           — SM-2-lite schedule, keyed by lichess puzzle id

Kept deliberately separate from backend/training/attempts.py: that store is
profile-derived and feeds the trends/usual-suspects numbers, and 80k lichess
puzzles would drown those aggregates. The interval ladder is imported from it
so the two systems schedule identically.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import random
import sqlite3
import time
from typing import Any, Iterable, Optional

import chess

from backend.training import store
from backend.training.attempts import LADDER_MINUTES
from backend.training.puzzle_db import DB_PATH

REGIME_DIR = os.path.join(os.path.dirname(DB_PATH), "regime")
DECKS_DIR = os.path.join(REGIME_DIR, "decks")

BAND = (1500, 2000)

# The three families below are not a guess: they come from measuring what
# fraction of each theme's solutions open with a non-forcing move (the
# `quiet%` column in docs/PUZZLE_STORM_REGIME.md, computed over the 74k
# popularity-filtered puzzles in the band). They fail under a clock for
# different reasons, so they get different blocks.

# A — quiet blindness. 50-84% of these open with a move that neither checks
# nor captures. A player scanning for forcing moves first simply never looks
# at the right candidate.
QUIET_MOTIFS = ["trappedPiece", "quietMove", "zugzwang", "defensiveMove",
                "advancedPawn", "promotion"]

# B — forcing but indirect. Only 3-11% open quietly, so the candidate move is
# easy to *find*; the cost is verifying it, two or three ply out, while the
# clock runs. Drilled to make the confirmation instant, not the search.
INDIRECT_MOTIFS = ["deflection", "attraction", "intermezzo", "clearance",
                   "capturingDefender", "discoveredAttack", "interference"]

# C — endgames. 45% of the band, and the quiet rate is high (pawn 74%,
# bishop 64%, knight 54%, rook 38%), so this is where quiet blindness and
# volume compound. Flailing in a rook ending burns the clock the tactics
# needed.
ENDGAME_MOTIFS = ["pawnEndgame", "rookEndgame", "bishopEndgame",
                  "knightEndgame", "queenEndgame"]

DERIVED_DECKS = {
    # first solver move gives no check and takes nothing
    "quiet-first": lambda f: f["quiet_first"],
    # first solver move moves a piece backwards (towards one's own side)
    "retreat-first": lambda f: f["retreat_first"],
    # a capture was available and the solution declined it
    "declined-capture": lambda f: f["declined_capture"],
}


# --------------------------------------------------------------------------
# puzzle mechanics
# --------------------------------------------------------------------------

def puzzle_position(row: dict) -> tuple[chess.Board, list[str]]:
    """(board the solver actually faces, solver's moves in UCI).

    Applies lichess' leading opponent move. Solver moves are the odd indices
    of the move list; the even ones after that are the opponent's replies and
    are applied for the solver automatically during a drill.
    """
    board = chess.Board(row["fen"])
    moves = row["moves"].split()
    board.push_uci(moves[0])
    return board, moves[1:]


def move_flags(row: dict) -> dict[str, bool]:
    """Derived properties of the solution's first move (see DERIVED_DECKS)."""
    board, solution = puzzle_position(row)
    first = chess.Move.from_uci(solution[0])

    is_capture = board.is_capture(first)
    gives_check = board.gives_check(first)
    captures_available = any(board.is_capture(m) for m in board.legal_moves)

    # "backwards" is relative to the side to move
    direction = chess.square_rank(first.to_square) - chess.square_rank(first.from_square)
    if board.turn == chess.BLACK:
        direction = -direction

    return {
        "quiet_first": not is_capture and not gives_check,
        "retreat_first": direction < 0 and not is_capture and not gives_check,
        "declined_capture": captures_available and not is_capture and not gives_check,
    }


# --------------------------------------------------------------------------
# flag cache
# --------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_flag_cache(band: tuple[int, int] = BAND, verbose: bool = True) -> int:
    """Compute move_flags() for every puzzle in the band, once, into a table.

    ~80k board constructions; a few seconds, and it makes deck-building for
    the derived families instant afterwards.
    """
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS puzzle_flags (
                id TEXT PRIMARY KEY,
                quiet_first INT, retreat_first INT, declined_capture INT
            )""")
        rows = conn.execute(
            "SELECT p.id, p.fen, p.moves FROM puzzles p "
            "LEFT JOIN puzzle_flags f ON f.id = p.id "
            "WHERE p.rating BETWEEN ? AND ? AND f.id IS NULL",
            band).fetchall()

        done = 0
        batch = []
        for row in rows:
            try:
                f = move_flags(dict(row))
            except (ValueError, AssertionError, IndexError):
                continue  # malformed row; skip rather than abort the cache
            batch.append((row["id"], int(f["quiet_first"]),
                          int(f["retreat_first"]), int(f["declined_capture"])))
            done += 1
            if len(batch) >= 2000:
                conn.executemany("INSERT OR REPLACE INTO puzzle_flags VALUES (?,?,?,?)", batch)
                batch = []
                if verbose:
                    print(f"  ...{done}/{len(rows)}")
        if batch:
            conn.executemany("INSERT OR REPLACE INTO puzzle_flags VALUES (?,?,?,?)", batch)
        conn.commit()
    return done


# --------------------------------------------------------------------------
# deck building
# --------------------------------------------------------------------------

def _sample(where: str, params: list, n: int, seed: Optional[int]) -> list[dict]:
    """Deterministic-if-seeded sample. Popularity filter keeps out the puzzles
    the community flagged as bad or ambiguous.

    Two phases on purpose: select the matching *ids*, shuffle those, then fetch
    full rows only for the n that were chosen. Materialising every matching row
    to take 30 of them cost 151s and 1.06 GB per deck once the database grew to
    5.5M puzzles. Shuffling the id list with the same seed picks the same
    positions as shuffling the row list would, so seeded results are unchanged.
    """
    # Only join the flags table when the predicate actually references it. The
    # join costs an index lookup per candidate row, which on a 5.5M-row database
    # dominates the query for the theme/rating decks that never look at flags.
    join = " LEFT JOIN puzzle_flags f ON f.id = p.id" if "f." in where else ""
    id_sql = f"SELECT p.id FROM puzzles p{join} WHERE {where}"
    with _connect() as conn:
        ids = [r[0] for r in conn.execute(id_sql, params).fetchall()]
        rng = random.Random(seed)
        rng.shuffle(ids)
        chosen = ids[:n]
        if not chosen:
            return []
        qs = ",".join("?" * len(chosen))
        by_id = {r["id"]: dict(r) for r in conn.execute(
            "SELECT id, fen, moves, rating, popularity, themes "
            f"FROM puzzles WHERE id IN ({qs})", chosen).fetchall()}
    return [by_id[i] for i in chosen if i in by_id]


def build_deck(name: str, n: int = 30, clock: int = 12,
               themes: Optional[Iterable[str]] = None,
               derived: Optional[str] = None,
               band: tuple[int, int] = BAND,
               min_popularity: int = 80,
               seed: Optional[int] = None) -> dict:
    """Curate one deck and write it to decks/<name>.json."""
    where = ["p.rating BETWEEN ? AND ?", "p.popularity >= ?"]
    params: list[Any] = [band[0], band[1], min_popularity]

    if themes:
        themes = list(themes)
        where.append("(" + " OR ".join("p.themes LIKE ?" for _ in themes) + ")")
        params += [f"%{t}%" for t in themes]

    if derived:
        if derived not in DERIVED_DECKS:
            raise ValueError(f"unknown derived family {derived!r}; "
                             f"expected one of {sorted(DERIVED_DECKS)}")
        where.append(f"f.{derived.replace('-', '_')} = 1")

    puzzles = _sample(" AND ".join(where), params, n, seed)
    deck = {
        "name": name,
        "clock_seconds": clock,
        "band": list(band),
        "themes": list(themes) if themes else [],
        "derived": derived,
        "built": datetime.datetime.now().isoformat(timespec="seconds"),
        "puzzles": puzzles,
    }
    os.makedirs(DECKS_DIR, exist_ok=True)
    store._write_json_atomic(os.path.join(DECKS_DIR, f"{name}.json"), deck)
    return deck


def load_deck(name: str) -> dict:
    path = os.path.join(DECKS_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"no deck {name!r}; run `plan` or `deck` first")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_decks() -> list[str]:
    if not os.path.isdir(DECKS_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(DECKS_DIR) if f.endswith(".json"))


# --------------------------------------------------------------------------
# the regime
# --------------------------------------------------------------------------

def build_plan(seed: Optional[int] = 20260814) -> list[dict]:
    """Build every deck the 6-week regime needs. Returns deck summaries."""
    built = []

    def add(name, **kw):
        deck = build_deck(name, seed=seed, **kw)
        built.append({"name": name, "n": len(deck["puzzles"]),
                      "clock": deck["clock_seconds"]})
        print(f"  {name:28s} {len(deck['puzzles']):3d} puzzles  @{deck['clock_seconds']}s")

    print("Phase 0 - diagnostic")
    add("diag-mixed", n=60, clock=20)

    print("Phase 1a - quiet blindness (one block per session)")
    for motif in QUIET_MOTIFS:
        add(f"quiet-{motif}", n=30, clock=15, themes=[motif])

    print("Phase 1b - forcing but indirect (faster clock; finding is easy)")
    for motif in INDIRECT_MOTIFS:
        add(f"indirect-{motif}", n=30, clock=10, themes=[motif])

    print("Phase 2 - the forcing-move trap (derived, no lichess equivalent)")
    for fam in DERIVED_DECKS:
        add(f"trap-{fam}", n=40, clock=15, derived=fam)

    print("Phase 3 - endgame speed")
    add("endgame-speed", n=40, clock=15, themes=ENDGAME_MOTIFS)
    for motif in ENDGAME_MOTIFS:
        add(f"endgame-{motif}", n=30, clock=15, themes=[motif])

    print("Phase 4 - racer simulation")
    for i in (1, 2, 3, 4):
        add(f"racer-{i}", n=50, clock=10)

    return built


# --------------------------------------------------------------------------
# session log + scheduling
# --------------------------------------------------------------------------

def _sessions_path() -> str:
    return os.path.join(REGIME_DIR, "sessions.jsonl")


def _srs_path() -> str:
    return os.path.join(REGIME_DIR, "srs.json")


def load_srs() -> dict:
    if os.path.exists(_srs_path()):
        with open(_srs_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def record(deck_name: str, puzzle: dict, correct: bool, elapsed: float,
           timed_out: bool, now: Optional[datetime.datetime] = None) -> dict:
    """Log one attempt and reschedule the puzzle.

    A timeout counts as a failure even if the eventual answer was right —
    that is the whole point of the regime.
    """
    now = now or datetime.datetime.now()
    os.makedirs(REGIME_DIR, exist_ok=True)
    with open(_sessions_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": now.isoformat(timespec="seconds"),
            "deck": deck_name,
            "puzzle_id": puzzle["id"],
            "rating": puzzle["rating"],
            "themes": puzzle.get("themes", "").split(),
            "correct": bool(correct),
            "timed_out": bool(timed_out),
            "elapsed": round(elapsed, 2),
        }) + "\n")

    passed = correct and not timed_out
    srs = load_srs()
    entry = srs.get(puzzle["id"]) or {"step": 0, "lapses": 0, "reps": 0}
    entry["reps"] += 1
    if passed:
        entry["step"] = min(entry["step"] + 1, len(LADDER_MINUTES) - 1)
    else:
        entry["lapses"] += 1
        entry["step"] = 0
    entry["due"] = (now + datetime.timedelta(minutes=LADDER_MINUTES[entry["step"]])).isoformat()
    entry["themes"] = puzzle.get("themes", "").split()
    srs[puzzle["id"]] = entry
    store._write_json_atomic(_srs_path(), srs)
    return entry


def sessions_log() -> list[dict]:
    if not os.path.exists(_sessions_path()):
        return []
    out = []
    with open(_sessions_path(), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def leeches(min_lapses: int = 2) -> list[dict]:
    """Puzzles failed repeatedly — the actual curriculum, once you have data."""
    out = [dict(e, puzzle_id=pid) for pid, e in load_srs().items()
           if e.get("lapses", 0) >= min_lapses]
    out.sort(key=lambda e: -e["lapses"])
    return out


def build_leech_deck(name: str = "leeches", clock: int = 15,
                     min_lapses: int = 2) -> dict:
    ids = [e["puzzle_id"] for e in leeches(min_lapses)]
    if not ids:
        raise ValueError("no leeches yet - drill some decks first")
    with _connect() as conn:
        qs = ",".join("?" * len(ids))
        rows = [dict(r) for r in conn.execute(
            f"SELECT id, fen, moves, rating, popularity, themes "
            f"FROM puzzles WHERE id IN ({qs})", ids).fetchall()]
    deck = {"name": name, "clock_seconds": clock, "band": list(BAND),
            "themes": [], "derived": None,
            "built": datetime.datetime.now().isoformat(timespec="seconds"),
            "puzzles": rows}
    os.makedirs(DECKS_DIR, exist_ok=True)
    store._write_json_atomic(os.path.join(DECKS_DIR, f"{name}.json"), deck)
    return deck


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def report(by: str = "theme") -> dict:
    """Accuracy and median time-to-answer, sliced by theme or by deck.

    Median time is the number to watch: accuracy can hold steady while the
    clock cost falls, and that fall *is* the Storm improvement.
    """
    log = sessions_log()
    buckets: dict[str, list[dict]] = {}
    for rec in log:
        keys = rec["themes"] if by == "theme" else [rec["deck"]]
        for k in keys:
            buckets.setdefault(k, []).append(rec)

    rows = []
    for key, recs in buckets.items():
        n = len(recs)
        solved = sum(1 for r in recs if r["correct"] and not r["timed_out"])
        rows.append({
            "key": key,
            "n": n,
            "accuracy": round(solved / n, 3),
            "median_seconds": round(_median([r["elapsed"] for r in recs]), 1),
            "timeouts": sum(1 for r in recs if r["timed_out"]),
        })
    rows.sort(key=lambda r: (r["accuracy"], -r["n"]))
    return {"total_attempts": len(log), "rows": rows}


# --------------------------------------------------------------------------
# interactive drill
# --------------------------------------------------------------------------

def _render(board: chess.Board, unicode_pieces: bool) -> str:
    text = board.unicode(borders=False, empty_square=".") if unicode_pieces else str(board)
    lines = text.splitlines()
    if board.turn == chess.BLACK:  # always show it from the solver's side
        lines = [" ".join(reversed(ln.split())) for ln in reversed(lines)]
    ranks = range(8, 0, -1) if board.turn == chess.WHITE else range(1, 9)
    body = "\n".join(f"  {r}  {ln}" for r, ln in zip(ranks, lines))
    files = "a b c d e f g h" if board.turn == chess.WHITE else "h g f e d c b a"
    return f"{body}\n\n     {files}"


def _parse(board: chess.Board, text: str) -> Optional[chess.Move]:
    """Accept SAN ('Nxe5', 'O-O') or UCI ('g1f3'). None if unparseable."""
    text = text.strip()
    for parse in (board.parse_san, board.parse_uci):
        try:
            return parse(text)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError, ValueError):
            continue
    return None


def drill(deck_name: str, limit: Optional[int] = None,
          clock: Optional[int] = None, unicode_pieces: bool = False,
          shuffle: bool = True) -> dict:
    """Run a timed session in the terminal. Enter to give up, 'q' to stop."""
    deck = load_deck(deck_name)
    clock = clock or deck["clock_seconds"]
    puzzles = list(deck["puzzles"])
    if shuffle:
        random.shuffle(puzzles)
    if limit:
        puzzles = puzzles[:limit]

    print(f"\n=== {deck_name} - {len(puzzles)} puzzles @ {clock}s ===")
    print("SAN or UCI. Enter = give up. q = quit.")
    print(f"The clock is not a hard cutoff: answers over {clock}s are logged "
          f"as TIME and count as failures.\n")

    solved = timeouts = 0
    times: list[float] = []

    for i, row in enumerate(puzzles, 1):
        board, solution = puzzle_position(row)
        side = "White" if board.turn == chess.WHITE else "Black"
        print(f"[{i}/{len(puzzles)}] {row['rating']}  ({side} to move)")
        print(_render(board, unicode_pieces))

        ok = True
        t0 = time.monotonic()
        for ply, expected_uci in enumerate(solution):
            if ply % 2:  # opponent's forced reply — play it for the solver
                board.push_uci(expected_uci)
                continue
            try:
                answer = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nstopped.")
                return _summary(deck_name, len(times), solved, timeouts, times)
            if answer.lower() == "q":
                print("\nstopped.")
                return _summary(deck_name, len(times), solved, timeouts, times)
            if not answer:
                ok = False
                break
            move = _parse(board, answer)
            if move is None:
                print("  ? unparseable - counting as a miss")
                ok = False
                break
            expected = chess.Move.from_uci(expected_uci)
            # A mate-in-1 by a different move is still a solve; lichess
            # accepts any mate at the final ply, so mirror that.
            if move != expected:
                probe = board.copy()
                probe.push(move)
                if not (probe.is_checkmate() and ply == len(solution) - 1):
                    ok = False
                    break
            board.push(expected)
            if ply + 1 < len(solution):
                print(_render(board, unicode_pieces))

        elapsed = time.monotonic() - t0
        timed_out = elapsed > clock
        times.append(elapsed)
        if ok and not timed_out:
            solved += 1
            print(f"  OK  {elapsed:.1f}s\n")
        else:
            if timed_out:
                timeouts += 1
            line = chess.Board(row["fen"])
            line.push_uci(row["moves"].split()[0])
            san = line.variation_san([chess.Move.from_uci(m) for m in solution])
            tag = "TIME" if timed_out and ok else "MISS"
            print(f"  {tag}  {elapsed:.1f}s   {san}")
            print(f"        https://lichess.org/training/{row['id']}\n")

        record(deck_name, row, ok, elapsed, timed_out)

    return _summary(deck_name, len(times), solved, timeouts, times)


def _summary(deck_name, n, solved, timeouts, times) -> dict:
    out = {
        "deck": deck_name, "attempted": n, "solved": solved,
        "timeouts": timeouts,
        "accuracy": round(solved / n, 3) if n else 0.0,
        "median_seconds": round(_median(times), 1),
    }
    print(f"--- {solved}/{n} solved, {timeouts} over the clock, "
          f"median {out['median_seconds']}s ---")
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="puzzle_regime", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("cache", help="precompute derived move flags for the band")
    sub.add_parser("plan", help="build every deck in the 6-week regime")
    sub.add_parser("decks", help="list built decks")

    p = sub.add_parser("deck", help="build one custom deck")
    p.add_argument("name")
    p.add_argument("-n", type=int, default=30)
    p.add_argument("--clock", type=int, default=12)
    p.add_argument("--themes", nargs="*")
    p.add_argument("--derived", choices=sorted(DERIVED_DECKS))
    p.add_argument("--min-rating", type=int, default=BAND[0])
    p.add_argument("--max-rating", type=int, default=BAND[1])

    p = sub.add_parser("drill", help="run a timed session")
    p.add_argument("deck")
    p.add_argument("-n", "--limit", type=int)
    p.add_argument("--clock", type=int)
    p.add_argument("--unicode", action="store_true", help="unicode pieces")

    p = sub.add_parser("report", help="accuracy and speed so far")
    p.add_argument("--by", choices=["theme", "deck"], default="theme")

    p = sub.add_parser("leeches", help="repeatedly-failed puzzles")
    p.add_argument("--min-lapses", type=int, default=2)
    p.add_argument("--build", action="store_true", help="also write a leech deck")

    p = sub.add_parser("urls", help="print lichess links for a deck")
    p.add_argument("deck")

    a = ap.parse_args(argv)

    if a.cmd == "cache":
        print(f"cached {build_flag_cache()} puzzles")
    elif a.cmd == "plan":
        build_flag_cache(verbose=False)
        build_plan()
        print(f"\ndecks in {DECKS_DIR}")
    elif a.cmd == "decks":
        for name in list_decks():
            d = load_deck(name)
            print(f"  {name:28s} {len(d['puzzles']):3d} @{d['clock_seconds']}s")
    elif a.cmd == "deck":
        d = build_deck(a.name, n=a.n, clock=a.clock, themes=a.themes,
                       derived=a.derived, band=(a.min_rating, a.max_rating))
        print(f"{a.name}: {len(d['puzzles'])} puzzles @{a.clock}s")
    elif a.cmd == "drill":
        drill(a.deck, limit=a.limit, clock=a.clock, unicode_pieces=a.unicode)
    elif a.cmd == "report":
        rep = report(a.by)
        print(f"{rep['total_attempts']} attempts\n")
        print(f"  {'key':22s} {'n':>4s} {'acc':>6s} {'med s':>7s} {'t/o':>5s}")
        for r in rep["rows"]:
            print(f"  {r['key']:22s} {r['n']:4d} {r['accuracy']:6.2f} "
                  f"{r['median_seconds']:7.1f} {r['timeouts']:5d}")
    elif a.cmd == "leeches":
        for e in leeches(a.min_lapses):
            print(f"  {e['lapses']}x  https://lichess.org/training/{e['puzzle_id']}"
                  f"   {' '.join(e.get('themes', []))}")
        if a.build:
            d = build_leech_deck(min_lapses=a.min_lapses)
            print(f"\nleech deck: {len(d['puzzles'])} puzzles")
    elif a.cmd == "urls":
        for row in load_deck(a.deck)["puzzles"]:
            print(f"https://lichess.org/training/{row['id']}  {row['rating']}  {row['themes']}")


if __name__ == "__main__":
    main()
