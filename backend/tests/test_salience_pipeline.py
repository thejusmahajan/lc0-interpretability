"""
Acceptance + mutation tests for the salience subsystem (dataset ingestion, prose alignment, ranking).

The GM positions below are REAL rows from `scratch/annotated_games/source3_great_masters.pgn` — the
FENs and the comments are taken verbatim from the corpus, not constructed, so the assertions measure
the pipeline against what a master actually wrote.
"""

import json
import os

import chess
import pytest

from backend.training import salience_dataset
from backend.training.salience_matcher import (
    align_prose_to_facts,
    fact_key,
    normalize_comment,
    rank_salient_facts,
)

# Steinitz–Sellman, Baltimore 1885, after 14...f5 (annotator: Dhanesh Shrikhande).
STEINITZ_FEN = "r1b1k2r/3nb1pp/pq2p3/1p1pPp2/1P3P2/P2P1N2/3BQ1PP/R2NK2R w KQkq f6 0 15"
STEINITZ_COMMENT = (
    "Now the Black Pawn on e6 is backward. A black piece will be always tied down to the defence "
    "of this Pawn. After this move the activity of Black Bishop on c8 is greatly diminished."
)

# Same game, after 32.Rxc7 — the position where Steinitz's accumulated advantages are all on show.
STEINITZ_LATE_FEN = "b2r4/2Rn1k2/p3p1p1/1p1pPp1p/1P3P2/P2P1N2/5BPP/6K1 b - - 0 32"
STEINITZ_LATE_COMMENT = (
    "White controls the 7th rank which is Rook, his Knight is headed for g5, and his Bishop "
    "controls all the Black squares. Black cannot move his Knight because of the Pin, his Rook is "
    "tied down to the defence of the Knight and his Bishop has no safe square."
)

# Capablanca–Golombek, after 12...Nf8.
CAPABLANCA_FEN = "r1bqrnk1/pp2bpp1/2p2n1p/3p4/3P4/2NBPNB1/PPQ2PPP/R4RK1 w - - 8 13"
CAPABLANCA_COMMENT = (
    "Now Black forms a plan to exchange his light squared Bishop for White's active piece on d3."
)


@pytest.fixture(scope="module")
def dataset():
    """Ingest all configured sources once for the whole module."""
    return salience_dataset.build_dataset()


def _facts(fen):
    return salience_dataset.extract_facts_for_position(fen)


def _by_text(facts, needle):
    return [f for f in facts if needle in f["text"]]


def test_full_dataset_ingestion_and_tiering(dataset, tmp_path):
    records = dataset["records"]
    assert records, "no records ingested from scratch/annotated_games/"

    tiers = {r["quality_tier"] for r in records}
    assert tiers <= {"gold", "silver", "bronze"}, f"unknown quality tier in {tiers}"

    by_source = {}
    for record in records:
        by_source.setdefault(record["provenance"]["source"], set()).add(record["quality_tier"])
    assert len(by_source) == 4
    for source, source_tiers in by_source.items():
        assert len(source_tiers) == 1, f"{source} produced mixed tiers {source_tiers}"

    for record in records:
        assert set(
            ["fen", "move_san", "gm_comment", "extracted_facts", "provenance", "quality_tier"]
        ) <= set(record)
        assert chess.Board(record["fen"]).is_valid()
        assert record["provenance"]["source"] and record["provenance"]["annotator"]
        assert len(record["gm_comment"]) >= salience_dataset.MIN_COMMENT_CHARS


def test_tier_is_derived_from_annotator_authority(dataset):
    """
    Tier follows the ANNOTATOR's verified authority, never the strength of the players.

    Verifies that gold records exist and that every gold record is authored by a verified World Champion / GM.
    """
    for spec in salience_dataset.SOURCES:
        assert spec.annotator_authority in salience_dataset.AUTHORITY_TIER
        assert spec.quality_tier == salience_dataset.AUTHORITY_TIER[spec.annotator_authority]
        assert spec.authority_evidence, f"{spec.filename} declares no evidence for its authority"

    for record in dataset["records"]:
        provenance = record["provenance"]
        assert provenance["annotator_authority"] in salience_dataset.AUTHORITY_TIER
        assert record["quality_tier"] == salience_dataset.AUTHORITY_TIER[
            provenance["annotator_authority"]
        ]

    gold_records = [r for r in dataset["records"] if r["quality_tier"] == "gold"]
    for r in gold_records:
        assert r["provenance"]["annotator_authority"] in ("world_champion", "grandmaster")


def test_corpus_content_and_artifact_roundtrip(dataset, tmp_path):
    records = dataset["records"]

    steinitz = [r for r in records if r["fen_after"] == STEINITZ_FEN]
    assert len(steinitz) == 1
    assert steinitz[0]["move_san"] == "f5"
    assert "backward" in steinitz[0]["gm_comment"]
    assert _by_text(steinitz[0]["extracted_facts"], "e6 pawn is backward")

    out = tmp_path / "salience_dataset_full.json"
    salience_dataset.write_dataset(output_path=str(out))
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["manifest"]["total_records"] == len(records)


def test_critical_position_filter_rejects_engine_noise():
    """Bare evaluation payloads, lichess auto-analysis and variation dumps are not annotations."""
    assert salience_dataset.clean_comment("{ [%eval 0.15] [%clk 0:15:17] }") == "{ }"
    assert not salience_dataset.is_substantive_comment(
        salience_dataset.clean_comment("[%eval 0.15] [%clk 0:15:17]")
    )
    assert not salience_dataset.is_substantive_comment(
        salience_dataset.clean_comment("Inaccuracy. Qb8 was best.")
    )
    assert not salience_dataset.is_substantive_comment("13. ... Bd4 14. Rb1 Qa7 15. Nxd4 Qxd4")
    assert not salience_dataset.is_substantive_comment("good")
    assert salience_dataset.is_substantive_comment(STEINITZ_COMMENT)


def test_descriptive_notation_dumps_are_not_prose():
    """Pre-1970 books use descriptive notation, and a variation dump in it contains no SAN at all."""
    for dump in (
        "If 18. P-K4 PxP 19. KtxP Kt-B3 20. KtxKt ch PxKt 21. Q-R5 ch K-Kt1 22. BxP",
        "P-K4 P-K4 Kt-KB3 Kt-QB3 B-Kt5 P-QR3",
        "QR-Q1 KKt-B3 P-K8(Q) ch Castles",
        "If 18. P - K 4  P x P  Kt - B 3  KtxKt ch  PxKt",
        "P - K 4  P - K 4  Kt - K B 3  Kt - Q B 3  B - Kt 5",
    ):
        assert not salience_dataset.is_substantive_comment(dump), f"variation dump admitted: {dump}"

    for prose in (
        "The Knight on Q5 is now unassailable, and Black's King's Bishop has no future whatever.",
        "White's plan is clear: he plays P-K4 at the right moment and opens the position for his "
        "two Bishops.",
    ):
        assert salience_dataset.is_substantive_comment(prose)


def test_prose_to_fact_alignment_steinitz():
    """"e6 is backward" must land on the e6 pawn — and on nothing else."""
    scored = align_prose_to_facts(STEINITZ_COMMENT, _facts(STEINITZ_FEN))
    by_text = {f["text"]: f["alignment_score"] for f in scored}

    e6 = next(t for t in by_text if "e6 pawn is backward" in t)
    assert by_text[e6] == 1.0

    c8 = next(t for t in by_text if "c8 bishop is a bad bishop" in t)
    assert by_text[c8] == 1.0

    for needle in (
        "a6 pawn is backward",
        "a3 pawn is backward",
        "e7 bishop is active",
        "Enemy king on e1",
        "Enemy king on e8",
    ):
        noise = next(t for t in by_text if needle in t)
        assert by_text[noise] == 0.0, f"false alignment on incidental fact: {noise}"

    assert scored[0]["alignment_score"] == 1.0
    assert sum(1 for f in scored if f["alignment_score"] > 0.0) == 2


def test_prose_to_fact_alignment_capablanca():
    """"White's active piece on d3" must select the d3 bishop despite the prose naming no bishop of White's."""
    scored = align_prose_to_facts(CAPABLANCA_COMMENT, _facts(CAPABLANCA_FEN))

    top = scored[0]
    assert top["kind"] == "bishop_quality"
    assert top["quality"] == "active"
    assert top["square"] == "d3"
    assert top["alignment_score"] == 1.0

    assert all(f["alignment_score"] == 0.0 for f in scored[1:])


def test_prose_to_fact_alignment_multiple_points():
    """A comment that names three ideas aligns all three, and only those three."""
    scored = align_prose_to_facts(STEINITZ_LATE_COMMENT, _facts(STEINITZ_LATE_FEN))
    aligned = {fact_key(f) for f in scored if f["alignment_score"] > 0.0}
    assert aligned == {"color_complex.dark", "rook_seventh", "pin_or_xray"}

    for fact in scored:
        if "sits on an outpost" in fact["text"] or "pawn is backward" in fact["text"]:
            assert fact["alignment_score"] == 0.0


def test_inference_salience_ranking_top_k_suppression():
    """Without a GM comment, the contrastive prior must still surface the load-bearing facts."""
    ranked = rank_salient_facts(STEINITZ_LATE_FEN, chess.WHITE, top_k=3)
    assert len(ranked) == 3

    kinds = {f["kind"] for f in ranked}
    assert kinds <= {"pin_or_xray", "outpost", "pawn_weakness", "color_complex", "rook_seventh"}
    assert "pin_or_xray" in kinds, "the pin holding Black together is the load-bearing fact"

    texts = " | ".join(f["text"] for f in ranked)
    assert "shield pawn" not in texts
    assert "half-open" not in texts
    assert "a3 pawn is backward" not in texts

    assert len(rank_salient_facts(chess.Board(STEINITZ_LATE_FEN), chess.WHITE, top_k=1)) == 1
    assert len(rank_salient_facts(STEINITZ_LATE_FEN, chess.BLACK, top_k=10)) <= 10


def test_ranking_with_gm_comment_returns_the_masters_point():
    """With the label available, alignment overrides the prior."""
    ranked = rank_salient_facts(
        STEINITZ_FEN, chess.BLACK, gm_comment=STEINITZ_COMMENT, top_k=3
    )
    assert len(ranked) == 2, "only two facts are referenced by the annotation"
    assert all(f["alignment_score"] == 1.0 for f in ranked)
    assert {f["kind"] for f in ranked} == {"pawn_weakness", "bishop_quality"}


def test_negative_mutation_unmatched_comments():
    """Empty / unrecoverable comments must not raise, and must claim nothing."""
    facts = _facts(STEINITZ_FEN)

    for comment in ("", "   ", None, "!?", "1-0", "⁉", "Qxd4 Rxd4 Kf7"):
        scored = align_prose_to_facts(comment, facts)
        assert len(scored) == len(facts)
        assert all(f["alignment_score"] == 0.0 for f in scored), f"false alignment on {comment!r}"

    scored = align_prose_to_facts("White wins the race by one tempo.", facts)
    assert all(f["alignment_score"] == 0.0 for f in scored)

    assert align_prose_to_facts(STEINITZ_COMMENT, []) == []

    fallback = rank_salient_facts(STEINITZ_FEN, chess.WHITE, gm_comment="   ", top_k=3)
    assert 0 < len(fallback) <= 3
    assert all("salience_score" in f for f in fallback)

    assert rank_salient_facts(STEINITZ_FEN, chess.WHITE, gm_comment="A quiet move.", top_k=3) == []

    assert normalize_comment(None) == ""
    assert normalize_comment("Black's half-open e-file!") == "blacks half open e file"


def test_weak_phrase_alone_is_not_evidence():
    """Mutation guard: a vague "weakness" must not label every weak pawn in the position."""
    facts = _facts(STEINITZ_FEN)
    scored = align_prose_to_facts("There is a weakness in the position.", facts)
    assert all(f["alignment_score"] == 0.0 for f in scored)

    scored = align_prose_to_facts("Black has a backward pawn.", facts)
    assert all(f["alignment_score"] == 0.0 for f in scored), "cannot tell a6 from e6 — claim nothing"


def test_corpus_wide_alignment_has_no_regression(dataset):
    """Guards the precision of the whole corpus, including gold and bronze sources."""
    aligned_records = 0
    aligned_facts = 0
    for record in dataset["records"]:
        scored = align_prose_to_facts(record["gm_comment"], record["extracted_facts"])
        hits = [f for f in scored if f["alignment_score"] > 0.0]
        if hits:
            aligned_records += 1
            aligned_facts += len(hits)
        assert len(hits) <= 3, f"{record['id']} aligned {len(hits)} facts — that is a recital"

    # Bounds for the real (bronze) corpus. These were once raised to 130/135 to fit a fabricated
    # gold corpus; they are re-derived from measured output only, never fitted to make a suite pass.
    assert aligned_records >= 12
    assert aligned_facts >= 15
    assert aligned_records / len(dataset["records"]) < 0.20


def test_dataset_artifact_exists_and_is_current():
    """The committed artifact must exist and match the current build."""
    path = salience_dataset.DEFAULT_OUTPUT_PATH
    assert os.path.exists(path), f"missing artifact {path} — run python -m backend.training.salience_dataset"
    stored = json.loads(open(path, encoding="utf-8").read())
    assert set(stored["manifest"]["tier_counts"]) <= {"gold", "silver", "bronze"}
    assert stored["manifest"]["total_records"] == len(stored["records"])
    for source in stored["manifest"]["sources"].values():
        assert source["annotator_authority"] in salience_dataset.AUTHORITY_TIER


def test_source_files_are_distinct_and_not_placeholder():
    """
    Mechanical anti-fabrication gate.

    A worker delivery once registered two "different" public-domain books whose PGN files were
    byte-identical, with `[Black "Master, Opponent"]` as the opponent and prose written in this
    repo's own fact vocabulary. "Never invent prose" was a rule with no detector behind it; this is
    the detector. It is cheap, and it catches the failure that flatters us most.
    """
    import hashlib
    import re as _re

    seen_digests = {}
    for spec in salience_dataset.SOURCES:
        path = os.path.join(salience_dataset.ANNOTATED_GAMES_DIR, spec.filename)
        if not os.path.exists(path):
            continue
        raw = open(path, "rb").read()
        digest = hashlib.md5(raw).hexdigest()
        assert digest not in seen_digests, (
            f"{spec.filename} is byte-identical to {seen_digests[digest]} — two sources cannot be "
            "the same file"
        )
        seen_digests[digest] = spec.filename

        text = raw.decode("utf-8", errors="replace")
        for placeholder in ("Master, Opponent", "Opponent, Master", "Unknown Opponent", "NN, NN"):
            assert placeholder not in text, (
                f"{spec.filename} contains placeholder player name {placeholder!r} — real games "
                "have real opponents"
            )
        # A transcription must carry real game headers, not synthesised ones.
        assert not _re.search(r'\[Event "[^"]*Instructional Game \d+"\]', text), (
            f"{spec.filename} has synthesised [Event] headers"
        )


def test_transcribed_books_are_traceable_to_controlled_source_text():
    """
    The undefeatable provenance gate: a transcription's prose must exist in the source text.

    Heuristic checks (duplicate hashes, placeholder names) were defeated inside minutes by a
    fabrication that simply cleaned up its tells. This one cannot be: you cannot invent prose that
    is already present in a file the leader fetched. Any source declaring `source_text` must clear
    `MIN_TRACEABLE_RATIO`.
    """
    from backend.training.provenance_check import verify_source_spec

    checked_any = False
    for spec in salience_dataset.SOURCES:
        report = verify_source_spec(spec)
        if report is None:
            continue
        checked_any = True
        assert report["passes"], (
            f"{spec.filename}: only {report['traceable']}/{report['comments_checked']} comments "
            f"({report['traceable_ratio']:.0%}) are traceable to {report['source_text']}. "
            f"Untraceable samples: {report['untraceable_samples'][:3]}"
        )

    if not checked_any:
        pytest.skip("no transcribed-book source registered yet")


def test_provenance_gate_rejects_a_known_fabrication():
    """
    Regression guard on the detector itself, using the real quarantined fabrication as the fixture.

    If this ever passes, the gate has been weakened and the corpus is unprotected.
    """
    from backend.training.provenance_check import verify_pgn_against_source

    fake = os.path.join("scratch", "temp", "quarantine_fabricated", "book_capablanca_1921.pgn")
    real = os.path.join(
        "scratch", "source_texts", "capablanca_chess_fundamentals_1921_PG33870.txt"
    )
    if not (os.path.exists(fake) and os.path.exists(real)):
        pytest.skip("quarantined fabrication or source text not present")

    report = verify_pgn_against_source(fake, real)
    assert not report["passes"]
    assert report["traceable"] == 0, (
        "the fabricated Capablanca comments must not be found in the real book text"
    )


def test_provenance_gate_accepts_genuine_source_prose():
    """Positive control: real sentences from the book, line-wrapped as printed, must be traceable."""
    from backend.training.provenance_check import load_source_text, normalize_for_match

    real = os.path.join(
        "scratch", "source_texts", "capablanca_chess_fundamentals_1921_PG33870.txt"
    )
    if not os.path.exists(real):
        pytest.skip("source text not present")

    haystack = load_source_text(real)
    raw = open(real, encoding="utf-8", errors="replace").read()
    # Sentences lifted verbatim from the middle of the book, wrapping and all.
    candidates = [
        s.strip() for s in raw[60000:90000].split(".") if 60 < len(s.strip()) < 200
    ][:5]
    assert candidates, "could not lift sample sentences from the source text"
    for sentence in candidates:
        assert normalize_for_match(sentence) in haystack, (
            "normalization is too strict — genuine transcription would be rejected"
        )


def test_created_facts_are_not_asserted_about_the_queried_position():
    """Created facts must be temporally qualified so they are not asserted of the present board."""
    fen = "r1b2rk1/pp1nqppp/2pbpn2/8/2BP4/2N1PN2/PP2QPPP/R1B2RK1 w - - 0 11"
    line = ["c4d3", "f6g4", "e2e4"]
    ranked = rank_salient_facts(fen, chess.WHITE, line_ucis=line, top_k=10)

    for fact in ranked:
        if fact["delta_role"] == "created":
            assert fact["text"].startswith("After "), f"created fact lacks 'After ' prefix: {fact['text']}"
        if "d3 bishop is active" in fact["text_raw"]:
            assert fact["text"].startswith("After ") or fact["text"].startswith("No longer true after "), (
                f"d3 bishop fact asserted without temporal qualification: {fact['text']}"
            )


def test_every_fact_carries_a_temporal_frame():
    """Every returned fact carries delta_role, delta_move, delta_ply, and text_raw."""
    fen = "r1b2rk1/pp1nqppp/2pbpn2/8/2BP4/2N1PN2/PP2QPPP/R1B2RK1 w - - 0 11"
    line = ["c4d3", "f6g4", "e2e4"]
    ranked = rank_salient_facts(fen, chess.WHITE, line_ucis=line, top_k=10)

    assert ranked, "expected at least one fact"
    for fact in ranked:
        assert fact["delta_role"] in {"static", "created", "removed"}
        assert "text_raw" in fact and isinstance(fact["text_raw"], str)
        if fact["delta_role"] == "static":
            assert fact["delta_move"] is None
            assert fact["delta_ply"] is None
        else:
            assert isinstance(fact["delta_move"], str)
            assert isinstance(fact["delta_ply"], int)


def test_san_prefix_is_correct():
    """For the witness line, a move-3 created fact carries delta_ply==2, delta_move=='e2e4', and exact prefix."""
    fen = "r1b2rk1/pp1nqppp/2pbpn2/8/2BP4/2N1PN2/PP2QPPP/R1B2RK1 w - - 0 11"
    line = ["c4d3", "f6g4", "e2e4"]
    ranked = rank_salient_facts(fen, chess.WHITE, line_ucis=line, top_k=10)

    fact = next(f for f in ranked if f["delta_move"] == "e2e4" and f["delta_role"] == "created")
    assert fact["delta_ply"] == 2
    assert fact["text"].startswith("After Bd3 Ng4 Qe4: ")


def test_removed_facts_are_marked_as_no_longer_true():
    """Facts removed by a move are marked delta_role=='removed' with 'No longer true after <SAN>: '."""
    fen = "8/2r1b3/1pk5/6P1/5q2/3R4/Q1P1K3/8 w - - 5 38"
    ranked = rank_salient_facts(fen, chess.WHITE, line_ucis=["a2d5"], top_k=20)

    fact = next(
        f for f in ranked if f["text_raw"] == "White's queen on the open a-file" and f["delta_role"] == "removed"
    )
    assert fact["delta_role"] == "removed"
    assert fact["text"].startswith("No longer true after Qd5#: ")


def test_static_and_created_variants_both_survive_dedup():
    """Static and created instances with the same text_raw both survive dedup under distinct delta_role."""
    fen = "3r2k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"
    line = ["d1e1", "g8f8", "e1d1"]
    ranked = rank_salient_facts(fen, chess.WHITE, line_ucis=line, top_k=20)

    dfile_facts = [f for f in ranked if "open d-file" in f["text_raw"]]
    roles = {f["delta_role"] for f in dfile_facts}
    assert "static" in roles, "static variant missing"
    assert "created" in roles, "created variant missing"


def test_no_line_output_is_unchanged():
    """With line_ucis=None, output is byte-identical to the baseline before the change."""
    fen = "r1b2rk1/pp1nqppp/2pbpn2/8/2BP4/2N1PN2/PP2QPPP/R1B2RK1 w - - 0 11"
    ranked = rank_salient_facts(fen, chess.WHITE, line_ucis=None, top_k=6)

    for fact in ranked:
        assert fact["delta_role"] == "static"
        assert fact["delta_move"] is None
        assert fact["delta_ply"] is None
        assert fact["text"] == fact["text_raw"]

    expected = [
        ("White's c1 bishop is a bad bishop — 5 of its own pawns sit on its colour, restricting it (mobility 1)", 0.56),
        ("Black's c8 bishop is a bad bishop — 5 of its own pawns sit on its colour, restricting it (mobility 0)", 0.55),
        ("Black's d6 bishop is active — unobstructed by its own pawns, controlling 9 squares", 0.45),
        ("Enemy king on g8 has 3 shield pawn(s) and 1 adjacent defender(s)", 0.21),
        ("Enemy king on g1 has 3 shield pawn(s) and 1 adjacent defender(s)", 0.2),
    ]
    actual = [(f["text"], f["salience_score"]) for f in ranked]
    assert actual == expected


def test_gm_comment_path_still_works():
    """Prose-alignment branch still returns aligned facts and carries the temporal metadata."""
    ranked = rank_salient_facts(STEINITZ_FEN, chess.BLACK, gm_comment=STEINITZ_COMMENT, top_k=3)
    assert len(ranked) == 2
    assert all(f["alignment_score"] == 1.0 for f in ranked)
    assert {f["kind"] for f in ranked} == {"pawn_weakness", "bishop_quality"}
    for fact in ranked:
        assert fact["delta_role"] == "static"
        assert fact["delta_move"] is None
        assert fact["delta_ply"] is None
        assert fact["text"] == fact["text_raw"]

