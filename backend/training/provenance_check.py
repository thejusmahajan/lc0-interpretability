"""
Provenance verification — every transcribed comment must be traceable to the source text.

"Never invent prose" (GM_CURRICULUM_PLAN.md, and the project motto: a wrong label is worse than no
label) was a rule with no detector behind it. A worker delivery exploited exactly that gap: it
produced `book_capablanca_1921.pgn` whose comments read like a master's notes
("White's Rook on c1 occupies the half-open c-file") but were actually restatements of this repo's
own `relational_facts` output. A corpus reverse-engineered from our extractor would have aligned
almost perfectly and "proved" our thesis.

Heuristic detectors (duplicate file hashes, placeholder player names) were defeated on the next
attempt within minutes — the fabrication survived, only the tells were cleaned up.

This is the detector that cannot be defeated by a better fabrication: **the transcribed comment must
appear, verbatim, in a source text the leader fetched and controls.** You cannot invent prose that is
already present in a file you did not write.

Usage: a `SourceSpec` for a transcribed book declares `source_text`, the path to the controlled text
(e.g. `scratch/source_texts/capablanca_chess_fundamentals_1921_PG33870.txt`). Every comment in the
PGN is then checked against it.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Dict, List, Optional

import chess.pgn

SOURCE_TEXT_DIR = os.path.join("scratch", "source_texts")

# A transcription is not a photocopy: line wrapping, quote style and dashes legitimately differ
# between a printed page, an OCR pass and a PGN comment. Everything below normalizes those away
# WITHOUT letting real wording differences through.
_QUOTES = {
    "‘": "'", "’": "'", "“": '"', "”": '"', "«": '"', "»": '"',
}
_DASHES = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
}
_WS_RE = re.compile(r"\s+")

# Short comments are not evidence of anything — "!" or "Better was Nf3" appears in any chess book.
MIN_CHECKED_LENGTH = 40
# Fraction of a source's comments that must be found verbatim for the source to be trusted.
MIN_TRACEABLE_RATIO = 0.95


_HYPHEN_BREAK_RE = re.compile(r"([A-Za-z])-\s*\n\s*([a-z])")


def normalize_for_match(text: str) -> str:
    """
    Fold away typography, line-wrapping and OCR artefacts so a printed page and a PGN comment
    compare equal — without letting a genuine wording difference through.

    The hyphenation rule matters for scanned sources: an OCR'd page breaks "litera-\nture" across
    lines while a faithful transcription writes "literature". Rejecting that would fail honest work.
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    for src, dst in {**_QUOTES, **_DASHES}.items():
        text = text.replace(src, dst)
    text = text.replace(" ", " ")
    return _WS_RE.sub(" ", text).strip().lower()


def load_source_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return normalize_for_match(handle.read())


def iter_pgn_comments(pgn_path: str) -> List[Dict[str, Any]]:
    """Every mainline comment in a PGN, with the game and move it belongs to."""
    comments: List[Dict[str, Any]] = []
    with open(pgn_path, encoding="utf-8", errors="replace") as handle:
        index = 0
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            index += 1
            for node in game.mainline():
                text = (node.comment or "").strip()
                if text:
                    comments.append({"game": index, "ply": node.ply(), "comment": text})
    return comments


def verify_pgn_against_source(pgn_path: str, source_text_path: str) -> Dict[str, Any]:
    """
    Check that each substantive comment in `pgn_path` occurs verbatim in `source_text_path`.

    Returns a report; never raises on content. `traceable_ratio` is computed over comments at least
    `MIN_CHECKED_LENGTH` characters long — shorter ones carry no evidential weight either way.
    """
    haystack = load_source_text(source_text_path)
    comments = iter_pgn_comments(pgn_path)

    checked: List[Dict[str, Any]] = []
    untraceable: List[Dict[str, Any]] = []

    for entry in comments:
        normalized = normalize_for_match(entry["comment"])
        if len(normalized) < MIN_CHECKED_LENGTH:
            continue
        checked.append(entry)
        if normalized not in haystack:
            untraceable.append(entry)

    traceable = len(checked) - len(untraceable)
    ratio = (traceable / len(checked)) if checked else 0.0

    return {
        "pgn": pgn_path,
        "source_text": source_text_path,
        "comments_total": len(comments),
        "comments_checked": len(checked),
        "traceable": traceable,
        "untraceable": len(untraceable),
        "traceable_ratio": round(ratio, 4),
        "passes": bool(checked) and ratio >= MIN_TRACEABLE_RATIO,
        "untraceable_samples": [u["comment"][:160] for u in untraceable[:10]],
    }


def verify_source_spec(spec: Any, base_dir: str = None) -> Optional[Dict[str, Any]]:
    """Verify one SourceSpec, or None when it declares no controlled source text."""
    source_text = getattr(spec, "source_text", None)
    if not source_text:
        return None

    from backend.training.salience_dataset import ANNOTATED_GAMES_DIR

    pgn_path = os.path.join(base_dir or ANNOTATED_GAMES_DIR, spec.filename)
    if not os.path.exists(pgn_path) or not os.path.exists(source_text):
        return {
            "pgn": pgn_path,
            "source_text": source_text,
            "passes": False,
            "error": "missing file",
            "comments_total": 0,
            "comments_checked": 0,
            "traceable": 0,
            "untraceable": 0,
            "traceable_ratio": 0.0,
            "untraceable_samples": [],
        }
    return verify_pgn_against_source(pgn_path, source_text)


if __name__ == "__main__":  # pragma: no cover - operator entry point
    import json
    import sys

    print(json.dumps(verify_pgn_against_source(sys.argv[1], sys.argv[2]), indent=2))
