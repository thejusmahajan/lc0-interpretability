# Salience Pipeline — build & audit report (P1 + P2)

Worker deliverable for `SALIENCE_PIPELINE_TASK.md`. Implements the corpus + matcher described in
`docs/SALIENCE_PROBLEM.md` and `GM_CURRICULUM_PLAN.md`. **STOP for leader review.**

`metrics.py` and `relational_facts.py` were NOT touched.

## 1. Artifacts

| File | Lines | What it is |
|---|---|---|
| `backend/training/salience_dataset.py` | 325 | Multi-source annotated-PGN ingestion → tiered corpus |
| `backend/training/salience_matcher.py` | 358 | Prose→fact alignment + salience ranking |
| `backend/training/salience_lexicon.json` | 170 | Audited concept lexicon (data, not code) |
| `backend/tests/test_salience_pipeline.py` | 318 | 14 acceptance + mutation tests |
| `scratch/temp/salience_dataset_full.json` | 1.07 MB | The corpus artifact (281 records) |

Key entry points: `salience_dataset.build_dataset` (`salience_dataset.py:227`),
`salience_dataset.write_dataset` (`:262`), `salience_matcher.align_prose_to_facts`
(`salience_matcher.py:210`), `salience_matcher.rank_salient_facts` (`:308`).

## 2. Dataset stats

281 critical positions from 43 games across 3 sources, 8.0 extracted facts per record.

> ### ⚠️ CORRECTION, 2026-07-29 — this corpus contains NO gold records
>
> As first shipped, this table read `gold` / `silver` / `bronze`, and the gold tier was labelled
> *"Public Domain Master Classics: Capablanca, Steinitz, Alekhine"*. **That was wrong.** Those names
> are the **players**. On audit, the `[Annotator]` headers are seven club-level hobbyists (Dhanesh
> Shrikhande, Rashmin Pulekar, Ashish Thatte, Ramkrishna Kashelkar, D. Ravishankar, Sushant Banerji,
> Pankaj Joshi), and source 2 is Tim McGrew, a philosophy professor and chess writer. **Not one of
> the 281 records was annotated by a titled player.**
>
> The error was inherited from the task spec and propagated into `SOURCES`. A world-class *game* is
> not a world-class *annotation*, and the value of a salience label is entirely the authority of
> whoever wrote the prose.
>
> Fixed: tier is now **derived** from a declared `annotator_authority` plus a checkable
> `authority_evidence` string (`salience_dataset.py:52`, `:69`), so the two cannot drift apart again.
> All three sources are `bronze`. The gold tier is empty, which is the honest state.
> `test_tier_is_derived_from_annotator_authority` guards it.

| Source | Tier | Authority | Records | Annotator |
|---|---|---|---|---|
| `source3_great_masters.pgn` | bronze | `unverified` | 125 | seven club-level annotators (per-game header) |
| `source2_electronic_campfire.pgn` | bronze | `unverified` | 153 | Tim McGrew — untitled |
| `source1_lichess_broadcast.pgn` | bronze | `none` | 3 | no `[Annotator]` on any game |

Filling the gold tier is the job of `GEMINI_SALIENCE_CORPUS_EXPANSION_TASK.md`.

The lichess broadcast source yields only 3 records from 24 games **by design**: broadcast comments are almost entirely
`[%eval]`/`[%clk]` payloads and lichess auto-analysis ("Inaccuracy. Qb8 was best."), which the
critical-position filter rejects (`salience_dataset.py:100`, `:107`). That is the filter working, not
a parse failure — all 43 games parsed with zero python-chess errors.

Every record carries `provenance{source, annotator, annotator_authority, authority_evidence,
license, game_ref, url}` and a derived `quality_tier`, per the modular knowledge architecture, so a
future build can filter to gold only — once gold exists.

## 3. Two deliberate deviations from the task spec

Both were forced by the data, and both are what make the acceptance tests honest rather than
decorative.

**(a) Facts are extracted AFTER the annotated move, not before.** The spec's own worked example is
Steinitz's "*Now the Black Pawn on e6 is backward*" (after 14...f5). Before f5, the f7 pawn supports
e6 and the pawn is **not** backward — the extractor correctly emits nothing. Extracting from the
pre-move position makes the annotator's stated point unextractable, so test 2 could only have passed
by faking it. Records keep `fen` (before, matching `move_san`) *and* `fen_after`, and facts come from
`fen_after`.

**(b) Facts are extracted for BOTH colours, not `pov=board.turn`.** The extractor's `pov` selects
whose assets/weaknesses get reported. Capablanca's note "*Black forms a plan to exchange his light
squared Bishop for White's active piece on d3*" sits on a **Black** move but describes a **White**
piece; with `pov=board.turn` that fact is never emitted. Each fact is tagged `fact_pov`
(`salience_dataset.py:141`).

Also note: the FEN in the spec's record-schema example is illustrative, not real — it has Black pawns
already on f5 and h5 with Black to move at move 14 and `move_san: "f5"`. The real corpus FEN is
`r1b1k2r/3nbppp/pq2p3/1p1pP3/1P3P2/P2P1N2/3BQ1PP/R2NK2R b KQkq - 0 14`. Tests use the real one.

## 4. Alignment accuracy — audited, and the number is not flattering

### The three hand-checked golden cases (all verbatim corpus rows)

**Steinitz–Sellman 1885, after 14...f5** — 8 true facts, annotator names 2:

| alignment | fact |
|---|---|
| **1.00** | Black's **e6** pawn is backward |
| **1.00** | Black's **c8** bishop is a bad bishop |
| 0.00 | Black's **a6** pawn is backward ← same motif, wrong instance |
| 0.00 | White's a3 pawn is backward |
| 0.00 | Black's e7 bishop is active |
| 0.00 | ×2 king-shield census, ×1 White's d2 bad bishop |

**Capablanca–Golombek, after 12...Nf8** — 5 true facts, 1 aligned: White's **d3** bishop is active
(1.00); everything else 0.00.

**Steinitz–Sellman, after 32.Rxc7** — 12 true facts, annotator names 3: dark-square complex (1.00),
the d7 pin (0.70), rook on the 7th (0.70). The outpost and all four backward pawns correctly score
0.00 — they are true, but not what Steinitz said in that note.

### Corpus-wide

- **16 of 281 records (5.7%)** produce at least one aligned fact; **19 aligned facts** total.
- Split: all 16 are `bronze` — see the correction in §2; no source clears the GM bar yet.
- Never more than 3 facts labelled for one annotation (asserted in the suite).

**Independent audit of all 19 alignments** (Gemini 3 Flash used strictly as a *language* judge —
"does this sentence refer to this fact?", never as a chess evaluator; prompts and raw verdicts are
reproducible from the corpus):

| verdict | count | |
|---|---|---|
| yes — comment clearly refers to the fact | **14** | 73.7% |
| partial — right concept, wrong side/instance or vague | 4 | 21.1% |
| **no — false alignment** | **1** | **5.3%** |

The single false alignment: `source2_electronic_campfire.pgn:4:17`, where the comment discusses a pin
on White's Nf3 and we labelled a structurally-similar pin on f7.

**This is a 9× precision improvement over the first working version**, which scored 67 alignments
across 41 records with a **48% false-alignment rate** (32 "no" verdicts). The audit is what found it.
Three gates were added in response (`salience_matcher.py:210`–`278`):

1. **Weak-and-ungrounded** — a vague word ("weakness", "hole", "defender") with no square to anchor
   it labels nothing. Killed "there is a weakness" tagging every weak pawn on the board.
2. **Ambiguous-instance** — if a position holds several instances of a motif (positions routinely
   hold 5 trivial pins, and always hold 2 king-shield facts) and the prose names none of their
   squares, we claim nothing. This was the single biggest source of false labels.
3. **Colour-mismatch** — when the annotator names exactly one side and the fact explicitly belongs to
   the other ("White is saddled with doubled pawns" ↛ Black's doubled c-pawns), score 0. Applied only
   to facts with a real ownership field, never to `fact_pov`, which merely records extraction order.

### The honest read on 5.7% coverage

Low coverage is the **correct** current result, not a bug, and the leader should read it as a finding:

- Our 13 fact kinds are static-positional. The bulk of master prose is about **plans, move-order,
  history, psychology and concrete variations** ("Najdorf, imperturbably confident, continues to bring
  out his pieces") — there is no fact to align, and inventing one would be exactly the fluent-but-wrong
  coach the motto forbids.
- Where the annotator does name a static feature, we usually catch it. The failures that remain are
  **recall** failures (e.g. "his Rook is tied down to the defence of the **Knight**" — our
  `tied_defender` only models pieces tied to weak *pawns*), not false claims.
- The suite pins coverage **below 20%** (`test_corpus_wide_alignment_has_no_regression`): a sudden
  jump means the lexicon has started firing on prose it does not understand.

## 5. Inference-mode ranking (no GM comment)

`rank_salient_facts` falls back to a contrastive prior over fact kinds (`salience_matcher.py:54`) plus
situational modifiers: a weak pawn under attack outranks one nobody attacks; a passer within 3 squares
of queening outranks a distant one; a naked king outranks a sheltered one; central pawn weaknesses
break ties over rook-pawn ones. Top-3 on the Steinitz `Rxc7` position, with no comment:

1. `0.91` N on d7 is pinned by c7 to K on f7
2. `0.80` The enemy R on c7 sits on an outpost
3. `0.80` Black's e6 pawn is backward

Those are three of the four things Steinitz actually wrote about, chosen out of 12 true facts, with
the king-shield census and the half-open files suppressed.

**Caveat the leader should weigh:** this prior is a hand-tuned ordering of fact *kinds*. It is a
placeholder for the learned ranking `GM_CURRICULUM_PLAN.md` calls for, and `docs/SALIENCE_PROBLEM.md`
§5 explicitly warns there is **no local rule** — a per-kind prior cannot see the chain, the contrast
with alternatives, or the forcing tree. It is useful as a floor, and should not be mistaken for the
solved problem.

## 6. Test suite

`python -m pytest backend/tests/test_salience_pipeline.py -o pythonpath=.` → **14 passed**.
Full backend suite (conda env `cszero`): **254 passed, 5 skipped**.

| Test | `test_salience_pipeline.py:` | Covers |
|---|---|---|
| `test_full_dataset_ingestion_and_tiering` | 59 | 3 sources, known tiers, schema + provenance on every row |
| `test_tier_is_derived_from_annotator_authority` | 86 | tier follows the ANNOTATOR, not the players; no unevidenced gold |
| `test_descriptive_notation_dumps_are_not_prose` | 130 | `P-K4 PxP KtxP` dumps rejected; prose naming a descriptive move kept |
| `test_critical_position_filter_rejects_engine_noise` | 102 | `[%eval]`/`[%clk]`, auto-analysis, variation dumps, sub-10-char |
| `test_prose_to_fact_alignment_steinitz` | 116 | e6-backward = 1.0; a6/a3/e7/king-shield = 0.0 |
| `test_prose_to_fact_alignment_capablanca` | 144 | d3 active bishop tops at 1.0, rest 0.0 |
| `test_prose_to_fact_alignment_multiple_points` | 158 | exactly the 3 motifs named, no more |
| `test_inference_salience_ranking_top_k_suppression` | 170 | ≤ top_k, load-bearing over noise, Board or FEN |
| `test_ranking_with_gm_comment_returns_the_masters_point` | 191 | alignment overrides prior |
| `test_negative_mutation_unmatched_comments` | 201 | empty/None/emoji/SAN-only → no error, 0.0 |
| `test_weak_phrase_alone_is_not_evidence` | 230 | mutation guard on both precision gates |
| `test_corpus_wide_alignment_has_no_regression` | 241 | corpus-level precision + coverage ceiling |
| `test_dataset_artifact_exists_and_is_current` | 261 | committed artifact matches the build |

## 7. Lexicon provenance (and why it is data, not code)

`salience_lexicon.json` holds 18 concept keys covering all 13 fact kinds and every sub-type. Candidate
phrases came from two Gemini passes — a generation pass over the fact schema, and a **mining pass over
the 281 real corpus comments** (which is where "active piece", "tied down to the defence", "controls
all the black squares" and bare "backward" came from; a schema-only lexicon missed all four).

Both passes were then **audited by hand and cut**. Rejected as false-alignment generators: bare nouns
`bishop`, `file`, `square`, `rook`, `line`, `pressure`, `position`; and `light squared bishop` /
`dark squared bishop`, which name a piece, not a colour-complex weakness. The rationale is recorded in
the file's `_meta` block. It is a data artifact so a better corpus can replace it without touching code.

## 8. Open items for the leader

1. **Recall, not precision, is now the frontier.** The gates are tight; the misses are extractor gaps
   (`tied_defender` only covers pawns; no fact kind for "trades off the active piece", king walks, or
   prophylaxis). Widening the extractor is a `relational_facts.py` change — leader-owned decision.
2. **The chain is not modelled.** `SALIENCE_PROBLEM.md` §2 says salience is selection *and linkage*.
   We select; we do not yet link. `move_delta.creates/removes` is stored on every record and is the
   natural input for that, unused so far.
3. **Corpus scale.** 19 labels is a pilot, not a training set. The ingestion path is source-agnostic
   (`SOURCES`, `salience_dataset.py:62`) — more gold PGN in, more labels out, no code change.
4. **The forcing tree is absent.** No LC0 read is wired in yet; ranking is static-position only.
