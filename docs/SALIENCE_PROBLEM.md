> **STATUS: PARTIALLY SUPERSEDED 2026-08-19.** §1-§5 (what salience *is*, the four shapes, why the
> naive approaches fail) remain current and correct. **§6's strategy — "learn the ranking from
> thousands of GM labels" — is dead**: measured yield is 19 labels over 2,284 facts, zero on gold.
> Do not act on §6 or source trainer cards from it. Current strategy: `PLAN_SALIENCE_CNP.md`.

# The Salience Problem — which of the many true facts is THE objective

> Companion to `NORTH_STAR_decoding_lc0.md`. Extraction is (largely) solved — the relational-fact
> extractor produces true facts about any position. **Salience is the open problem: most of those facts
> are incidental; only a few carry the objective. Picking the right few is the bottleneck between "the
> machine sees true facts" and "the machine understands the point."**

## 1. Definition
For any position, the extractor emits a LARGE set of **true** facts — attacks, pins, passed pawns,
piece-control, king pressure, defender-removals. The **salience problem** is:

> *Which small subset of these true facts constitutes the objective, and which are noise?*

A coach that recites every true fact is useless and overwhelming; a coach that names THE point is
valuable. The difference is salience. And a *wrong* salience call is a **bad coach — worse than none**
(the motto). So salience is where the north star lives or dies.

## 2. Worked example (real data): position #1, `…Bc6`/`…cxb3`
After `…cxb3 … bxc2`, the extractor emitted these — **all true**:

| Fact (all verified true) | Salient? |
|---|---|
| protected passed pawn c2 (defended by Ba4, 1 from queening) | ✅ core |
| `Pc2` attacks the `Qd1` | ✅ core |
| conditional pin: a `Nxc2` would be pinned by `Ba4` to `Qd1` | ✅ core |
| `…Bxd4` removes the knight's control of **c2** | ✅ core |
| `…Bxd4` also removes its control of e2, b3, f3, b5, f5, c6, e6 | ❌ noise (7 true-but-incidental squares) |
| various attacks on major pieces, king-pressure counts | ❌ mostly incidental |

The **objective is a CHAIN of the four core facts**: *remove the c2-defender (`Bxd4`) → advance the
protected passed pawn to c2 → it attacks the queen and can't be captured (the pin) → White is tied down.*
The other facts are true but **not the point.**

**Two lessons this one example teaches:**
- Salience is **selection** — 4 load-bearing facts out of a dozen true ones.
- Salience is **linkage** — the 4 aren't independent; they CHAIN into one idea. Recognizing the chain is
  part of salience, not separate from it.

## 3. Salience has different SHAPES (more examples)
The salient facts look different depending on the kind of objective — which is exactly why no single
rule finds them:

- **Tactical (win material).** Among many facts, the salient one is the fork / pin / hanging piece that
  wins material by force; everything else is scenery.
- **Positional / quiet.** e.g. *"trades off the opponent's only active piece,"* or *"fixes a backward
  pawn as a permanent target."* Salient facts here are subtle and carry a **small eval delta** — real,
  but invisible to anything that ranks by evaluation swing.
- **Defensive (#12, `…Kb7`).** The salient fact is *"the king walks to safety, sidestepping perpetual
  check."* Our naive extractor even looked at the **wrong king**. Defensive salience is a distinct,
  easily-missed shape.
- **Prophylactic / move-order (#11, `…Nb4`).** The point is that a move **removes a defender BEFORE** the
  plan, *enabling* it — the temporary piece-for-pawns that "violates" a principle to remove the e-file
  weakness. Salience here lives in the **chain and the order**, not any static snapshot.

## 4. What makes a fact salient (the dimensions)
1. **Load-bearing** — the objective collapses if you remove it. (The c2 passer, not the f3-square control.)
2. **The delta vs the alternatives** — what the *best* move achieves that the inferior ones don't.
   Facts shared by both the sharp and the safe move are, almost by definition, **not** the point.
3. **On the forcing line** — the fact the threat / forced sequence hinges on (why `cxb3` forces: `…bxc2`
   wins if ignored).
4. **The chain** — several facts often LINK into one objective; salience includes the linkage.
5. **The GM test** — what a strong annotator would actually name as the point. (This is our ground truth.)

## 5. Why the naive approaches all fail
- **"Emit every fact"** → noise; overwhelming; a bad coach.
- **"Rank by eval swing"** → misses positional, defensive, and quiet objectives (small delta, real point).
- **"Only tactical motifs"** → misses prophylaxis, defense, maneuvering, conversion.
- **"Biggest material / most-attacked piece"** → misses every non-material objective.
There is **no local rule.** Salience is a property of the whole plan + the forcing tree + the contrast
with alternatives — not of any fact in isolation.

## 6. How we attack it (the approach)
Three forces, converging:
- **Contrast (best line vs alternatives)** — filters out the incidental facts (shared by both moves) and
  surfaces the *delta*. Cuts the field.
- **The forcing tree** (threats + forcedness, from LC0's search) — tells us which facts the critical line
  actually turns on. Ranks the field.
- **GM annotations (the curriculum, `GM_CURRICULUM_PLAN.md`)** — provide **ground-truth salience labels at
  scale**: a master's comment *is* a statement of what's salient. We LEARN the fact→salience ranking from
  thousands of such labels. This is what the knowledge module is *for*.
- **The user's eye** — validates samples; the ultimate gate until the corpus is trusted.

## 7. What "solved" looks like (and how we'll know)
Given a position, the machine surfaces the **same 1–3 facts a strong annotator would name as the point** —
no more, and none wrong — grounded in the extractor's true facts and ranked by the learned salience.
**Validation:** alignment with *held-out* GM annotations (did we foreground what the master foregrounded?)
plus the user's eye on samples. Until then, salience stays human-gated — never fluent-but-wrong.
