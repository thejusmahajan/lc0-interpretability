# North Star — Decoding LC0's Language (research note)

**Status:** contemplation, NOT a build order. This maps the terrain for the project's most
important aim (`LEADER_BIBLE.md` §1 — THE FLAG'S MOTTO). We are many steps from the frontier;
this note is honest about the distance and about what is real today. Seed: `research_learned_lookahead.md`.

> *LC0 is the ultimate coach; we just don't yet understand its language. But we will.*

---

## 0. The non-negotiable principle (governs everything below)
- **LC0 is the coach. The LLM is a translator of LC0's thoughts — never a chess reasoner.**
- **Accuracy over fluency. A wrong concept is worse than silence** (a bad coach does more harm
  than no coach). The translator may emit only what LC0's evidence supports; every explanation
  names the REAL objective the variations rest on, or says nothing.
- Same grounding discipline that killed the bogus "sacrifice"/"advantage" tags, raised to the
  project's highest purpose: a claim we cannot ground in LC0's evidence or a verified board fact
  is a claim we do not make.

---

## 1. What "LC0's thinking" actually is — the sources, ranked by readability

### Tier A — Behavioral read (AVAILABLE TODAY, no interpretability)
LC0's outputs already expose "what it is weighing," non-invented. We confirmed the wrapper
`get_policy_distribution` returns, **per candidate move**: `{uci, san, from, to, p, q, n, wdl}` —
- **`p`** = raw 0-node policy prior (its instinct — which moves it even considers),
- **`n`** = MCTS visit count (**how seriously it weighed that plan** — the tree's attention),
- **`q`** = the value it found down that line,
- **`wdl`** = win/draw/loss (the CHARACTER of the fight: sharp / drawish / must-defend).
Plus per-line `pv_lines` (the plan itself) and the eval trajectory along a line (where the
advantage is won or lost = the critical moment).
**This is real evidence of "what it's thinking" — WHAT it prefers and HOW MUCH — not WHY in human
terms.** A translator constrained to it cannot hallucinate the objective; at worst it misreads it
(caught by the human-oracle gate, §2). The MCTS visit tree is the single most underused window we
already own.

### Tier B — Structural read (AVAILABLE TODAY; the near-term unlock)
Overlay LC0's chosen line with **objective board facts** (deterministic, via `lichess_tagger` +
python-chess): material trajectory (temp sac? even? wins material?), king exposure, piece-activity
deltas (pieces reaching more active squares), pawn-structure changes (**weaknesses created or
removed** — e.g. #11's e6), space, development/tempo count, files/diagonals opened.
These are FACTS about the line LC0 chose. Together they ARE the raw objective: *"over this line
Black's pieces gain activity, White's e6 weakness is removed, at the cost of a temporary knight
for two pawns"* — #11's real objective, stated entirely from facts. **LC0 picks the line (its
judgment); we describe the line's objective factually; the translator narrates. No reasoning, no
hallucination.**

### Tier C — Mechanistic read (the FRONTIER; research-grade, far)
Read LC0's *internal* computation via interpretability (we already have `lczerolens` hooks on BT3):
- **Attention** — extracted today but averaged over 15 layers × 24 heads → too diffuse (only 2.82%
  of findings are attention-blind, i.e. it almost always "looks" everywhere). Must be sharpened to
  **causal / head-specific** to mean anything.
- **Learned look-ahead** (`research_learned_lookahead.md`): probe middle layers for the
  **future-board representations** (3–7 plies out) and the "look-ahead heads" that route future
  info into the present move. This is the literal *"look into its thoughts to see the plans it is
  weighing."*
- **Suppressed-win probe:** where its internal layers found a win its output priors distrust — the
  Tal fear, mechanized.
**Honest limits:** architecture-specific (shown on a particular Leela net; must be **re-verified on
our BT3-768x15x24h**), probes must be *trained* on labelled data, and separating "it planned this"
from "it just didn't" is real research. This is where the full vision lives, and where we are many
steps away.

---

## 2. The translator's contract (the safeguard that makes it honest)
The LLM receives a **structured evidence packet** (Tier A+B now, C later) and MUST:
1. Narrate **only** the facts in the packet — the plan (from the visit tree / PV), the objective
   (from the structural deltas), the cost/risk (material + WDL).
2. Introduce **no** chess claim not in the packet. **Never** evaluate or reason about the position
   itself. If the evidence is ambiguous, say **less**, not more.
3. **Cite** its evidence (this line, this square, this material fact) so it is checkable.
Architecture: **constrained / grounded generation** with the evidence packet as the *only* source —
ideally a **schema the LLM fills**, not free prose. The LLM is a rendering layer, not a mind.
**Validation gate:** spot-check every stage against the strong player — a translation that states a
*wrong* objective is a reject, exactly like a bogus tag. Fluent-but-wrong never ships.

---

## 3. What "the objective of the position" concretely decomposes into

**THE KEY REFINEMENT — the objective is CONTRASTIVE (user, 2026-07-28).** Describing the correct
line's facts *in isolation* does NOT capture the objective — proven: a single-line Tier-B prototype
mislabelled #1 `Bc6` a "sacrifice" (it wrongly attributed the *opponent's* exchange sac to the mover)
and missed the real point of #2 (piece development). **The objective of a move is defined by what the
INFERIOR alternatives FAIL to achieve compared to the correct continuation.** A human sees this by
looking at the position; a machine reads it by CONTRAST — compute the facts for the best line AND for
the top alternative(s) (we already have them: `critical_lines` / multipv), and the objective is the
**salient delta**: what the best line achieves that the alternative doesn't (the eval/WDL gap tells the
magnitude and *kind*; the structural diff tells *what* — e.g. "the safe move keeps material but leaves
the king exposed / development lagging"). This also makes the eventual translator's job tractable and
hallucination-resistant: it narrates a concrete factual *difference*, never "explain this position".
Attribution rule (from the #1 bug): a "sacrifice" counts only when the MOVER gives the material, not
when material merely dips because the opponent sacrificed.

**DEEPER (user, 2026-07-28) — the objective lives in the FORCING TREE + a RELATIONAL FACT WEB, and both
are computable (proven on `Bc6`/`cxb3`):**
- *Forcing tree:* a move's meaning is in the branches it forces, invisible in its linear PV. Read from
  LC0's search: **forcedness** = eval spread across the opponent's replies (recaptures ≈ −5, everything
  else ≤ −10 ⇒ forced), **threat** = what the mover plays if the opponent ignores (`…bxc2`, +24). Verified.
- *Relational fact web:* the real objective decomposed into CONCRETE geometric facts — protected passed
  pawn (`c2`, defended by `Ba4`, 1 from queening), pawn-attacks-queen (`c2`→`Qd1`), x-ray/pin
  (`Ba4`→c2→`Qd1`: a `Nxc2` is pinned), defender-removal (`Bxd4` removes the `Nd4` that guarded c2),
  promotion support (`Qb6`). ALL verified computable; a general extractor auto-reproduced the
  passed-pawn / queen-attack / defender-removal facts. So the "final sight" is NOT ineffable intuition —
  it is extractable from board + tree. The mystery moved from "can we see it?" to "which facts are
  SALIENT?" (leader+user judge salience; the forcing tree tells us which line the objective turns on).
- Build: `RELATIONAL_FACTS_TASK.md` (pins via `board.pin`, conditional "what-if recapture" facts, zero
  false positives). Fact-extraction is close; salience + composition remain the hard, human-gated part.

So we know what to extract (and what the translator may assemble):
- **The PLAN** — the recurring idea across LC0's high-visit subtrees (kingside storm, occupy d5,
  trade into a won endgame). Detectable as the common theme in the tree's principal lines.
- **The JUSTIFICATION** — the structural payoff (Tier B facts) the plan achieves = the WHY, factual.
- **The COST / RISK** — material given up + WDL character (how sharp, how forcing).
- **The HUMAN LESSON** — a *named* label (development, initiative, weakness-removal, king-safety,
  temp-sac-for-structure) drawn from a **grounded vocabulary**, applied ONLY when the facts license
  it (ground it like `docs/THEME_DEFINITIONS.md`).
LC0's tree gives the plan; board-facts give the justification/cost; the vocabulary gives the lesson
name; the LLM assembles and invents nothing.

---

## 4. Staged trajectory (honest about distance)
- **S0 — now:** show LC0's *real* continuation (done) + the deterministic structural deltas of the
  line (Tier B). **No LLM.** The user reads the objective from facts. This already embodies the motto.
- **S1:** add the constrained **translator** (LLM as schema-filler over the Tier A+B packet) —
  validated against the user; ships only when it reliably states the *right* objective.
- **S2:** deepen **plan extraction** from the full MCTS visit tree (the recurring idea across
  subtrees, not just the top PV).
- **S3 — frontier:** **mechanistic probes** on BT3 (reproduce/verify learned-look-ahead on *our*
  net; build the suppressed-win detector). A probe enters the translator's evidence *only* once it
  is validated to correlate with a human-usable insight.
Gate at every stage: the strong player confirms the stated objective is correct on a sample.

---

## 5. Open questions / what to go learn
- Can we surface the **full visit tree** (not just top-`n` candidates) and its per-move `q`/PV
  cleanly through the wrapper? (VerboseMoveStats is already on — likely yes.)
- Can a **linear probe read "future move / plan"** from our BT3 mid-layers — i.e. reproduce the
  look-ahead papers on `768x15x24h`? *This is the core research question.*
- What is the **minimal grounded theme vocabulary** that covers the objectives we actually see
  (development, initiative, weakness, king-safety, space, temp-sac…)? Ground it, don't invent it.
- **Prior art to survey** (the translator-not-reasoner pattern): DecodeChess (plan narration), plus
  any mechanistic-interpretability-for-chess tooling. Steal the interface, not the reasoning.

---

## 6. The one line that governs all of it
**LC0 chooses; facts justify; the LLM only translates.** If we cannot ground a claim in LC0's
evidence or a verified board fact, we do not say it. **A silent coach beats a wrong one.**
