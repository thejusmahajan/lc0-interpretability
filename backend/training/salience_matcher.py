"""
Salience Matcher & Ranker — which of the many TRUE facts is THE point.

The extractor (`relational_facts.py`) is deliberately exhaustive: for any position it emits a large
set of facts that are all true. `docs/SALIENCE_PROBLEM.md` names the remaining problem — most of those
facts are incidental, and a coach that recites them all is worse than no coach. This module selects.

Two modes, one ranker:

- **Training / evaluation** (`gm_comment` given). The annotator's prose IS the salience label
  (`GM_CURRICULUM_PLAN.md`). `align_prose_to_facts` scores each fact by how explicitly the prose
  references it, using a concept lexicon (`SALIENCE_LEXICON`) plus hard grounding gates on the
  squares/files/colours the annotator actually names.

- **Inference / coaching** (`gm_comment=None`). No label available, so the ranker falls back to a
  contrastive prior: load-bearing kinds (defender removals, pins, passers, outposts, pawn weaknesses)
  outrank quiet background facts (king-shield counts, a rook merely standing on a half-open file).

**Precision over recall, deliberately.** A wrong salience call is a bad coach — the motto. A fact only
scores above zero when the prose gives positive evidence for it, and a fact that names a square the
annotator did not name is dropped to 0.0 outright, even when its concept word matches. That rule is
what stops "Black's a6 pawn is backward" riding along on Steinitz's comment about e6.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Union

import chess

from backend.training.relational_facts import relational_facts

LEXICON_PATH = os.path.join(os.path.dirname(__file__), "salience_lexicon.json")

# Score components. strong concept + explicitly named square == 1.0 (an explicit reference).
STRONG_CONCEPT_SCORE = 0.7
WEAK_CONCEPT_SCORE = 0.4
SQUARE_BONUS = 0.3
COLOUR_MISMATCH_FACTOR = 0.5

_SQUARE_RE = re.compile(r"\b([a-h][1-8])\b")
# "the e-file" / "e file" (hyphens are normalized to spaces before this runs).
_FILE_RE = re.compile(r"\b([a-h]) ?file\b")
_COLOUR_RE = re.compile(r"\b(white|black)s?\b")
_APOSTROPHE_RE = re.compile(r"['’]")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_WS_RE = re.compile(r"\s+")

# Contrastive prior for inference mode: how load-bearing a fact KIND typically is.
# Keys are "kind" or "kind.subtype"; the more specific key wins.
INFERENCE_PRIORS: Dict[str, float] = {
    "defender_removed": 1.00,
    "conditional_pin": 0.95,
    "pin_or_xray": 0.90,
    "protected_passed_pawn": 0.90,
    "outpost": 0.80,
    "pawn_weakness.backward": 0.75,
    "pawn_weakness.isolated": 0.70,
    "rook_seventh": 0.70,
    "color_complex.dark": 0.68,
    "color_complex.light": 0.68,
    "attack_on_valuable": 0.65,
    "tied_defender": 0.60,
    "pawn_weakness.doubled": 0.55,
    "bishop_quality.bad": 0.55,
    "file_control.open": 0.45,
    "bishop_quality.active": 0.45,
    "file_control.half-open": 0.35,
    "king_pressure": 0.20,
}
DEFAULT_PRIOR = 0.30


def _load_lexicon() -> Dict[str, Dict[str, Any]]:
    """Load the concept lexicon, normalizing every phrase exactly as comments are normalized."""
    with open(LEXICON_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)

    lexicon: Dict[str, Dict[str, Any]] = {}
    for key, entry in raw.items():
        if key.startswith("_"):
            continue
        normalized_entry = dict(entry)
        for tier in ("strong", "weak", "negative"):
            normalized_entry[tier] = [
                normalize_comment(phrase) for phrase in entry.get(tier, []) if phrase
            ]
        lexicon[key] = normalized_entry
    return lexicon


def fact_key(fact: Dict[str, Any]) -> str:
    """The lexicon/prior key for a fact: "kind" or "kind.subtype" when the kind has sub-types."""
    kind = fact.get("kind", "")
    for field in ("weakness", "quality", "complex_color", "kind_of"):
        value = fact.get(field)
        if value:
            return f"{kind}.{value}"
    return kind


def normalize_comment(gm_comment: Optional[str]) -> str:
    """
    Lowercase; delete apostrophes ("Black's" -> "blacks"); every other punctuation mark and hyphen
    becomes a space ("half-open e-file" -> "half open e file"); collapse whitespace.
    """
    text = (gm_comment or "").lower()
    text = _APOSTROPHE_RE.sub("", text)
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


SALIENCE_LEXICON: Dict[str, Dict[str, Any]] = _load_lexicon()


def _referenced_squares(normalized: str) -> set:
    return set(_SQUARE_RE.findall(normalized))


def _referenced_files(normalized: str) -> set:
    return set(_FILE_RE.findall(normalized))


def _referenced_colours(normalized: str) -> set:
    """Colours the annotator names, including possessives ("White's" normalizes to "whites")."""
    return set(_COLOUR_RE.findall(normalized))


# `controlled_squares` is deliberately EXCLUDED: it is the long incidental list a captured defender
# happened to cover (docs/SALIENCE_PROBLEM.md, "7 true-but-incidental squares"). Letting it into the
# grounding set would make a defender_removed fact match any square the annotator names.
_SQUARE_FIELDS = (
    "square", "pawn", "attacker_square", "target_square", "pinned_square",
    "captured_square", "king_square", "defends",
)
_SQUARE_LIST_FIELDS = ("squares", "holes", "defenders")


def _fact_squares(fact: Dict[str, Any]) -> List[str]:
    """Every board square this fact is grounded on."""
    squares: List[str] = []
    for field in _SQUARE_FIELDS:
        value = fact.get(field)
        if isinstance(value, str) and _SQUARE_RE.fullmatch(value):
            squares.append(value)
    for field in _SQUARE_LIST_FIELDS:
        value = fact.get(field)
        if isinstance(value, list):
            squares.extend(v for v in value if isinstance(v, str) and _SQUARE_RE.fullmatch(v))
    return squares


def _square_hit(fact: Dict[str, Any], squares_named: set, files_named: set) -> bool:
    """True when the annotator named one of this fact's own squares, or its file."""
    if squares_named & set(_fact_squares(fact)):
        return True
    fact_file = fact.get("file")
    return bool(fact_file and fact_file in files_named)


def _fact_colour(fact: Dict[str, Any]) -> tuple:
    """
    The colour the fact is ABOUT, plus whether that is an explicit ownership claim.

    `color`/`defender_color` are stated by the extractor ("Black's e6 pawn"), so they can be trusted
    to gate. `fact_pov` only records which side we ran the extractor for — a pin extracted for White
    is still a fact *about* a Black piece — so it may soften a score but must never zero one.
    """
    for field in ("color", "defender_color"):
        value = fact.get(field)
        if isinstance(value, str) and value.lower() in ("white", "black"):
            return value.lower(), True
    pov = fact.get("fact_pov")
    if isinstance(pov, str) and pov.lower() in ("white", "black"):
        return pov.lower(), False
    return None, False


def _phrase_present(normalized: str, phrase: str) -> bool:
    """Whole-phrase containment — "active" must not match inside "inactive"."""
    if not phrase:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", normalized) is not None


def _concept_score(normalized: str, key: str) -> float:
    """Concept-level evidence that the prose is talking about this fact kind."""
    entry = SALIENCE_LEXICON.get(key)
    if not entry:
        return 0.0

    for phrase in entry.get("negative", []):
        if _phrase_present(normalized, phrase):
            return 0.0

    for phrase in entry.get("strong", []):
        if _phrase_present(normalized, phrase):
            return STRONG_CONCEPT_SCORE

    for phrase in entry.get("weak", []):
        if _phrase_present(normalized, phrase):
            return WEAK_CONCEPT_SCORE

    return 0.0


def align_prose_to_facts(
    gm_comment: str,
    extracted_facts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Score every extracted fact by how explicitly `gm_comment` references it.

    Returns copies of the facts with `alignment_score` (and `alignment_evidence`) added, sorted by
    score descending. 1.0 == explicitly referenced (concept named AND the fact's own square named);
    0.0 == incidental noise the annotator did not mention.

    An empty or unparseable comment scores every fact 0.0 rather than raising.
    """
    normalized = normalize_comment(gm_comment)
    squares_named = _referenced_squares(normalized)
    files_named = _referenced_files(normalized)
    colours_named = _referenced_colours(normalized)

    # How many instances of each motif the position contains. A position routinely holds five
    # trivial "pins" and always holds two king-shield censuses; one word of prose cannot pick
    # between them, so an ungrounded concept match there is a coin flip, not a label.
    instance_counts: Dict[str, int] = {}
    for fact in extracted_facts:
        key = fact_key(fact)
        instance_counts[key] = instance_counts.get(key, 0) + 1

    scored: List[Dict[str, Any]] = []
    for fact in extracted_facts:
        result = dict(fact)
        key = fact_key(fact)
        concept = _concept_score(normalized, key) if normalized else 0.0
        evidence: Dict[str, Any] = {"key": key, "concept": concept}

        score = concept
        square_hit = _square_hit(fact, squares_named, files_named)

        if score > 0.0 and not square_hit:
            if concept <= WEAK_CONCEPT_SCORE:
                # Weak phrases ("weakness", "hole", "defender") are suggestive at best. On their own,
                # with nothing on the board to anchor them to, they are not evidence.
                score = 0.0
                evidence["gated_by"] = "weak_and_ungrounded"
            elif instance_counts.get(key, 0) > 1:
                # The annotator named the motif but not WHICH one — unresolvable, so claim nothing.
                score = 0.0
                evidence["gated_by"] = "ambiguous_instance"

        if score > 0.0 and square_hit:
            score += SQUARE_BONUS
            evidence["square_hit"] = True

        fact_colour, colour_is_owned = _fact_colour(fact)
        if score > 0.0 and fact_colour and colours_named and fact_colour not in colours_named:
            if colour_is_owned and len(colours_named) == 1:
                # The annotator talks about exactly one side, and the fact belongs to the other:
                # "White is saddled with doubled pawns" is not a label for Black's doubled c-pawns.
                score = 0.0
                evidence["gated_by"] = "colour_mismatch"
            else:
                score *= COLOUR_MISMATCH_FACTOR
                evidence["colour_mismatch"] = True

        result["alignment_score"] = round(min(score, 1.0), 4)
        result["alignment_evidence"] = evidence
        scored.append(result)

    scored.sort(key=lambda f: (-f["alignment_score"], f.get("kind", "")))
    return scored


def _inference_prior(fact: Dict[str, Any]) -> float:
    """Contrastive prior with situational modifiers, used when no GM comment is available."""
    key = fact_key(fact)
    prior = INFERENCE_PRIORS.get(key)
    if prior is None:
        prior = INFERENCE_PRIORS.get(fact.get("kind", ""), DEFAULT_PRIOR)

    # A weakness nobody attacks is scenery; one under fire is the point.
    if fact.get("kind") == "pawn_weakness":
        if fact.get("attacked"):
            prior += 0.15
        # Coarse tie-break only: a central weakness is reachable by more pieces than a rook-pawn one.
        # This is a heuristic, not a claim — with a GM comment available, alignment overrides it.
        square = fact.get("square")
        if isinstance(square, str) and square[:1] in ("c", "d", "e", "f"):
            prior += 0.05
    if fact.get("kind") == "protected_passed_pawn":
        distance = fact.get("distance")
        if isinstance(distance, int) and distance <= 3:
            prior += 0.10
    if fact.get("kind") == "color_complex":
        prior += 0.02 * max(0, len(fact.get("holes", [])) - 3)
    if fact.get("kind") == "king_pressure" and fact.get("shield_pawns") == 0:
        prior += 0.30

    return min(prior, 1.0)


def rank_salient_facts(
    board_or_fen: Union[chess.Board, str],
    pov: chess.Color,
    gm_comment: Optional[str] = None,
    top_k: int = 3,
    line_ucis: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract the position's facts and return at most `top_k` salient ones, noise filtered out.

    With `gm_comment`: ranked by prose alignment (training/evaluation — is our top-1 what the master
    named?). Without: ranked by the contrastive prior (inference/coaching).

    Facts are extracted for BOTH colours, tagged `fact_pov`, because the point of a position is as
    often the opponent's weakness as our own asset; `pov` breaks ties toward the side we coach.
    """
    fen = board_or_fen.fen() if isinstance(board_or_fen, chess.Board) else board_or_fen
    line = list(line_ucis or [])

    san_prefixes: List[str] = []
    if line:
        b_sim = chess.Board(fen)
        san_history: List[str] = []
        for move_uci in line:
            move_obj = chess.Move.from_uci(move_uci)
            san_history.append(b_sim.san(move_obj))
            b_sim.push(move_obj)
            san_prefixes.append(" ".join(san_history))

    facts: List[Dict[str, Any]] = []
    seen = set()
    for colour in (chess.WHITE, chess.BLACK):
        extracted = relational_facts(fen, line, colour)
        for f in extracted["position_facts"]:
            raw_text = f["text"]
            tagged = dict(f)
            tagged["fact_pov"] = chess.COLOR_NAMES[colour]
            tagged["delta_role"] = "static"
            tagged["delta_move"] = None
            tagged["delta_ply"] = None
            tagged["text_raw"] = raw_text
            tagged["text"] = raw_text

            key = (tagged["kind"], tagged["text_raw"], tagged["delta_role"], tagged["delta_move"])
            if key not in seen:
                seen.add(key)
                facts.append(tagged)

        for ply_idx, per_move in enumerate(extracted["per_move"]):
            move_uci = per_move.get("move", line[ply_idx] if ply_idx < len(line) else None)
            prefix = san_prefixes[ply_idx] if ply_idx < len(san_prefixes) else ""

            for f in per_move.get("creates", []):
                raw_text = f["text"]
                tagged = dict(f)
                tagged["fact_pov"] = chess.COLOR_NAMES[colour]
                tagged["delta_role"] = "created"
                tagged["delta_move"] = move_uci
                tagged["delta_ply"] = ply_idx
                tagged["text_raw"] = raw_text
                tagged["text"] = f"After {prefix}: {raw_text}"

                key = (tagged["kind"], tagged["text_raw"], tagged["delta_role"], tagged["delta_move"])
                if key not in seen:
                    seen.add(key)
                    facts.append(tagged)

            for f in per_move.get("removes", []):
                raw_text = f["text"]
                tagged = dict(f)
                tagged["fact_pov"] = chess.COLOR_NAMES[colour]
                tagged["delta_role"] = "removed"
                tagged["delta_move"] = move_uci
                tagged["delta_ply"] = ply_idx
                tagged["text_raw"] = raw_text
                tagged["text"] = f"No longer true after {prefix}: {raw_text}"

                key = (tagged["kind"], tagged["text_raw"], tagged["delta_role"], tagged["delta_move"])
                if key not in seen:
                    seen.add(key)
                    facts.append(tagged)

    if gm_comment and gm_comment.strip():
        scored = align_prose_to_facts(gm_comment, facts)
        salient = [f for f in scored if f["alignment_score"] > 0.0]
        return salient[:top_k]

    pov_name = chess.COLOR_NAMES[pov]
    for fact in facts:
        fact["salience_score"] = round(_inference_prior(fact), 4)
        # Tie-break toward the side being coached without letting perspective outrank substance.
        fact["salience_score"] = round(
            fact["salience_score"] + (0.01 if fact.get("fact_pov") == pov_name else 0.0), 4
        )

    facts.sort(key=lambda f: (-f["salience_score"], f.get("kind", ""), f.get("text", "")))
    return facts[:top_k]
