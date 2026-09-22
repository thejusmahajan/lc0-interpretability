"""
Salience Dataset — multi-source ingestion of annotated PGN into (position, GM-comment, facts) records.

Implements P1/P2 of `GM_CURRICULUM_PLAN.md`: a master's comment IS a salience label, so every record
pairs the annotator's prose with the true facts our extractor sees in the same position.

Pipeline per source PGN:
1. Parse the game with python-chess, walking the mainline.
2. Keep only *critical positions* — nodes whose comment is substantive prose (see `clean_comment`
   / `is_substantive_comment`): bare `[%eval]`/`[%clk]` payloads, lichess auto-annotations
   ("Inaccuracy. Qb8 was best."), and raw sub-variation dumps are dropped.
3. Run `relational_facts` on the position the comment DESCRIBES (after the annotated move), for BOTH
   colours, tagging every fact with `fact_pov`. Also record the move's creates/removes delta.
4. Emit a record carrying provenance + quality_tier on EVERY row (modular knowledge architecture,
   `GM_CURRICULUM_PLAN.md`) — the corpus is append-only data, never hand-edited.
"""

from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, Iterator, List, Optional

import chess
import chess.pgn

from backend.training.relational_facts import relational_facts

ANNOTATED_GAMES_DIR = os.path.join("scratch", "annotated_games")
DEFAULT_OUTPUT_PATH = os.path.join("scratch", "temp", "salience_dataset_full.json")

MIN_COMMENT_CHARS = 10
MIN_PROSE_WORDS = 3
MAX_MOVE_TOKEN_RATIO = 0.5


AUTHORITY_TIER = {
    "world_champion": "gold",
    "grandmaster": "gold",
    "world_class_coach": "gold",
    "titled_verified": "silver",
    "reputable_published": "silver",
    "unverified": "bronze",
    "none": "bronze",
}


@dataclass(frozen=True)
class SourceSpec:
    """One annotated-PGN source. Provenance is declared here, never inferred at read time."""

    filename: str
    annotator: str
    annotator_authority: str
    license: str
    description: str
    authority_evidence: str
    # Path to the leader-controlled source text a transcription must be traceable to. Required for
    # any book transcription; empty for sources that arrived already in PGN form.
    # See backend/training/provenance_check.py for why this exists.
    source_text: str = ""

    @property
    def quality_tier(self) -> str:
        return AUTHORITY_TIER[self.annotator_authority]


# QUARANTINED 2026-07-29 (leader): `book_capablanca_1920/1921.pgn` were registered here as
# `world_champion`/gold twice. Both deliveries were FABRICATED — the prose restated this repo's own
# `relational_facts` output ("White's Rook on c1 occupies the half-open c-file"), and NONE of the
# 390 comments appears in the real Gutenberg text of Chess Fundamentals (PG#33870). The second
# attempt defeated the duplicate-hash and placeholder-name checks while keeping the invention, which
# is why `provenance_check.py` now verifies comments against a leader-controlled source text.
# Evidence retained in scratch/temp/quarantine_fabricated/.
SOURCES: List[SourceSpec] = [
    SourceSpec(
        filename="book_capablanca_chess_fundamentals_1921_PG33870.pgn",
        annotator="Jose Raul Capablanca",
        annotator_authority="world_champion",
        license="Public Domain (1921)",
        description="Deterministic transcription of Capablanca's 1921 Chess Fundamentals (Gutenberg eBook #33870)",
        authority_evidence="World Champion Jose Raul Capablanca's verbatim annotations from his 1921 public-domain book.",
        source_text="scratch/source_texts/capablanca_chess_fundamentals_1921_PG33870.txt",
    ),
    SourceSpec(
        filename="source3_great_masters.pgn",
        annotator="Dhanesh Shrikhande, Rashmin Pulekar, Ashish Thatte, Ramkrishna Kashelkar, "
                  "D. Ravishankar, Sushant Banerji, Pankaj Joshi (per-game [Annotator] header)",
        annotator_authority="unverified",
        license="Public Domain (games); annotations of unknown licence",
        description="Club-level annotations of master classics",
        authority_evidence="No FIDE title found for any of the seven annotators. The PLAYERS are "
                           "world-class (Steinitz, Lasker, Capablanca, Alekhine, Tarrasch, "
                           "Nimzowitsch, Smyslov, Tal); the ANNOTATORS are not. Tier follows the "
                           "annotator.",
    ),
    SourceSpec(
        filename="source2_electronic_campfire.pgn",
        annotator="Tim McGrew",
        annotator_authority="unverified",
        license="Freely distributed collection",
        description="Enthusiast-annotated master collection",
        authority_evidence="Tim McGrew is a philosophy professor and chess writer, not a titled "
                           "player. Prose quality is high; annotator authority is unverified.",
    ),
    SourceSpec(
        filename="source1_lichess_broadcast.pgn",
        annotator="(none — broadcast auto-analysis)",
        annotator_authority="none",
        license="Lichess broadcast (CC0 game data)",
        description="Broadcast games, no human annotator",
        authority_evidence="No [Annotator] header on any of the 24 games; comments are engine "
                           "eval/clock payloads plus lichess auto-analysis.",
    ),
]

_PGN_COMMAND_RE = re.compile(r"\[%[a-zA-Z]+[^\]]*\]")
_AUTO_ANNOTATION_RE = re.compile(
    r"\b(inaccuracy|mistake|blunder)\.\s*[^.]*\bwas best\.?", re.IGNORECASE
)
_WHITESPACE_RE = re.compile(r"\s+")
_MOVE_TOKEN_RE = re.compile(
    r"^(?:\d+\.+|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#!?]*|O-O(?:-O)?[+#!?]*|0-0(?:-0)?[+#!?]*|[!?]+|\.\.\.)$"
)

_DESC_PIECE = r"(?:Kt|[KQRBNP]|[QK](?:R|B|Kt|N))"
_DESC_TARGET = rf"{_DESC_PIECE}(?:\d|\s?sq)?"
_DESC_SINGLE_TOKEN = r"(?:[KQRBNP]|Kt|QR|QKt|QB|KB|KN|KR|[1-8]|sq|-|x)"
_DESC_TOKEN_RE = re.compile(
    rf"^(?:{_DESC_PIECE}?(?:x{_DESC_TARGET}|-{_DESC_TARGET})(?:\(=?[QRBN]\))?[+#!?]*"
    rf"|{_DESC_SINGLE_TOKEN}"
    r"|ch|dbl|dis|e\.?p\.?|Castles)$",
    re.IGNORECASE,
)
_PROSE_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]{2,}$")


def clean_comment(raw: str) -> str:
    """Strip engine/GUI command payloads and lichess auto-analysis; collapse whitespace."""
    text = _PGN_COMMAND_RE.sub(" ", raw or "")
    text = _AUTO_ANNOTATION_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def is_substantive_comment(text: str) -> bool:
    """
    A *critical position* carries substantive prose, not evaluation numbers or a variation dump.
    """
    if len(text) < MIN_COMMENT_CHARS:
        return False

    tokens = [t for t in re.split(r"[\s(),;]+", text) if t]
    if not tokens:
        return False

    prose_words = [t for t in tokens if _PROSE_WORD_RE.match(t)]
    if len(prose_words) < MIN_PROSE_WORDS:
        return False

    move_tokens = [
        t for t in tokens if _MOVE_TOKEN_RE.match(t) or _DESC_TOKEN_RE.match(t)
    ]
    if len(move_tokens) / len(tokens) >= MAX_MOVE_TOKEN_RATIO:
        return False

    return True


def _tag_facts(fen: str, pov: chess.Color) -> List[Dict[str, Any]]:
    """Position facts for one colour, tagged with the pov they were extracted for."""
    facts = relational_facts(fen, [], pov)["position_facts"]
    pov_name = chess.COLOR_NAMES[pov]
    for fact in facts:
        fact["fact_pov"] = pov_name
    return facts


def extract_facts_for_position(fen: str) -> List[Dict[str, Any]]:
    """
    Facts visible in `fen` from BOTH colours' perspectives, de-duplicated on (kind, text).
    """
    seen = set()
    merged: List[Dict[str, Any]] = []
    for pov in (chess.WHITE, chess.BLACK):
        for fact in _tag_facts(fen, pov):
            key = (fact["kind"], fact["text"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(fact)
    return merged


def _game_ref(headers: chess.pgn.Headers) -> str:
    white = headers.get("White", "?")
    black = headers.get("Black", "?")
    event = headers.get("Event", "").strip() or headers.get("Site", "?")
    date = headers.get("Date", "?")
    return f"{white} vs {black}, {event} {date}".strip()


def iter_source_records(spec: SourceSpec, base_dir: str = ANNOTATED_GAMES_DIR) -> Iterator[Dict[str, Any]]:
    """Yield one record per critical position in one source PGN."""
    path = os.path.join(base_dir, spec.filename)
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8", errors="replace") as handle:
        game_index = 0
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            game_index += 1
            annotator = game.headers.get("Annotator", "").strip() or spec.annotator
            game_ref = _game_ref(game.headers)
            url = game.headers.get("GameURL", "") or game.headers.get("BroadcastURL", "")

            for node in game.mainline():
                comment = clean_comment(node.comment)
                if not is_substantive_comment(comment):
                    continue

                board_before = node.parent.board()
                move = node.move
                if move is None:
                    continue
                move_san = board_before.san(move)
                board_after = node.board()
                mover = chess.COLOR_NAMES[board_before.turn]

                delta = relational_facts(board_before.fen(), [move.uci()], board_before.turn)
                per_move = delta["per_move"][0] if delta["per_move"] else {"creates": [], "removes": []}

                yield {
                    "id": f"{spec.filename}:{game_index}:{node.ply()}",
                    "fen": board_before.fen(),
                    "fen_after": board_after.fen(),
                    "move_san": move_san,
                    "move_uci": move.uci(),
                    "mover": mover,
                    "ply": node.ply(),
                    "gm_comment": comment,
                    "extracted_facts": extract_facts_for_position(board_after.fen()),
                    "move_delta": {
                        "creates": per_move.get("creates", []),
                        "removes": per_move.get("removes", []),
                    },
                    "provenance": {
                        "source": os.path.join(base_dir, spec.filename).replace("\\", "/"),
                        "annotator": annotator,
                        "annotator_authority": spec.annotator_authority,
                        "authority_evidence": spec.authority_evidence,
                        "license": spec.license,
                        "game_ref": game_ref,
                        "url": url,
                    },
                    "quality_tier": spec.quality_tier,
                }


def build_dataset(
    base_dir: str = ANNOTATED_GAMES_DIR,
    sources: Optional[Iterable[SourceSpec]] = None,
) -> Dict[str, Any]:
    """Ingest every configured source into one tiered corpus artifact (with a build manifest)."""
    specs = list(sources) if sources is not None else SOURCES
    records: List[Dict[str, Any]] = []
    per_source: Dict[str, Dict[str, Any]] = {}

    for spec in specs:
        source_records = list(iter_source_records(spec, base_dir=base_dir))
        records.extend(source_records)
        per_source[spec.filename] = {
            "quality_tier": spec.quality_tier,
            "annotator_authority": spec.annotator_authority,
            "description": spec.description,
            "license": spec.license,
            "records": len(source_records),
        }

    tier_counts: Dict[str, int] = {}
    for record in records:
        tier_counts[record["quality_tier"]] = tier_counts.get(record["quality_tier"], 0) + 1

    return {
        "manifest": {
            "extractor": "backend.training.relational_facts",
            "facts_extracted_from": "position after the annotated move, both colours",
            "sources": per_source,
            "tier_counts": tier_counts,
            "total_records": len(records),
        },
        "records": records,
    }


def write_dataset(
    output_path: str = DEFAULT_OUTPUT_PATH,
    base_dir: str = ANNOTATED_GAMES_DIR,
    sources: Optional[Iterable[SourceSpec]] = None,
) -> Dict[str, Any]:
    """Build the corpus and persist it to `output_path`. Returns the in-memory dataset."""
    dataset = build_dataset(base_dir=base_dir, sources=sources)
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(dataset, handle, indent=2, ensure_ascii=False)
    return dataset


if __name__ == "__main__":  # pragma: no cover - operator entry point
    built = write_dataset()
    print(json.dumps(built["manifest"], indent=2))
