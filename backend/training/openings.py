import os
import re
import csv
import logging
import chess
from typing import List, Dict, Optional

logger = logging.getLogger("chess_speak_out_loud.openings")

def _get_openings_dir() -> str:
    """Resolve the openings data directory in order of preference:
    1. CSZERO_OPENINGS_DIR environment variable
    2. Package-bundled backend/openings_data directory
    3. Legacy data/openings directory
    """
    env_dir = os.getenv("CSZERO_OPENINGS_DIR")
    if env_dir:
        return env_dir

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled_dir = os.path.join(backend_dir, "openings_data")
    if os.path.exists(bundled_dir) and any(f.endswith(".tsv") for f in os.listdir(bundled_dir)):
        return bundled_dir

    root_dir = os.path.dirname(backend_dir)
    legacy_dir = os.path.join(root_dir, "data", "openings")
    if os.path.exists(legacy_dir) and any(f.endswith(".tsv") for f in os.listdir(legacy_dir)):
        return legacy_dir

    return bundled_dir


OPENINGS_DIR = _get_openings_dir()

_openings_trie = {}  # tuple(uci) -> {"eco": str, "name": str}
_tabiya_fens = {}    # (eco, name) -> fen
_loaded = False


def to_opening_tag(name: str) -> str:
    """e.g. 'Sicilian Defense: Najdorf Variation' -> 'Sicilian_Defense_Najdorf_Variation'"""
    tag = name.replace(":", "").replace(",", "").replace(".", "").replace("'", "")
    tag = tag.replace("-", " ")
    while "  " in tag:
        tag = tag.replace("  ", " ")
    return tag.strip().replace(" ", "_")


def _load_openings():
    global _loaded, OPENINGS_DIR
    if _loaded:
        return

    OPENINGS_DIR = _get_openings_dir()
    if not os.path.exists(OPENINGS_DIR):
        logger.warning(
            "Opening data directory not found at '%s'. Opening classification will return '???'",
            OPENINGS_DIR
        )
        _loaded = True
        return

    loaded_count = 0
    for letter in 'abcde':
        path = os.path.join(OPENINGS_DIR, f"{letter}.tsv")
        if not os.path.exists(path):
            logger.debug("Opening file %s not found in %s", f"{letter}.tsv", OPENINGS_DIR)
            continue

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, None)
            if not header:
                continue

            for line_no, row in enumerate(reader, start=2):
                if len(row) < 3:
                    continue
                eco, name, pgn = row[0], row[1], row[2]

                board = chess.Board()
                uci_moves = []
                try:
                    for san_move in pgn.split():
                        san_move = re.sub(r'^\d+\.*', '', san_move)
                        if not san_move:
                            continue

                        move = board.parse_san(san_move)
                        uci_moves.append(move.uci())
                        board.push(move)

                    if uci_moves:
                        seq = tuple(uci_moves)
                        _openings_trie[seq] = {"eco": eco, "name": name}
                        _tabiya_fens[(eco, name)] = board.fen()
                        loaded_count += 1
                except Exception as e:
                    logger.debug("Error parsing row %d in %s (%s): %s", line_no, path, eco, e)

    if loaded_count == 0:
        logger.warning("No openings were loaded from '%s'. Classification will return '???'", OPENINGS_DIR)
    else:
        logger.info("Successfully loaded %d opening variations from '%s'", loaded_count, OPENINGS_DIR)

    _loaded = True


def classify(uci_moves: List[str]) -> Optional[Dict[str, str]]:
    """Longest prefix match for the given sequence of UCI moves."""
    _load_openings()

    # Try longest prefixes first
    for i in range(len(uci_moves), 0, -1):
        prefix = tuple(uci_moves[:i])
        if prefix in _openings_trie:
            return _openings_trie[prefix]

    return None


def tabiya_fen(eco: str, name: str) -> Optional[str]:
    _load_openings()
    return _tabiya_fens.get((eco, name))


def lines_by_tag() -> Dict[str, Dict]:
    """opening_tag -> {"eco","name","uci_moves","fen"}, keeping the shortest
    (defining) line per tag. Read-only accessor added for C2 repertoire
    selection (leader addition, logged in WORKLOG_TRAINING.md)."""
    _load_openings()
    result: Dict[str, Dict] = {}
    for seq, info in _openings_trie.items():
        tag = to_opening_tag(info["name"])
        current = result.get(tag)
        if current is None or len(seq) < len(current["uci_moves"]):
            board = chess.Board()
            try:
                for uci in seq:
                    board.push_uci(uci)
            except ValueError:
                continue
            result[tag] = {
                "eco": info["eco"],
                "name": info["name"],
                "uci_moves": list(seq),
                "fen": board.fen(),
            }
    return result
