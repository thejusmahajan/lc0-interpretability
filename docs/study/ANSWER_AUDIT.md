# Why the study answers drifted

**Audited:** `STUDY_SESSION_LOG.md` (session of 2026-08-09/10), against the full corpus, 2026-08-11.
**Result:** 8 material errors out of roughly 30 substantive claims. Every one of them is fluent,
plausible, and confidently phrased. **None of them is random.** They cluster into five causes, and
three of the five are defects in *our* corpus, not in the model.

That distinction is the whole point of this document. "The model hallucinated" is not an
actionable finding. "Our reference shelf labels the wrong network as primary" is.

---

## Cause 1 — The cold-start check certifies reading, not staying read

The session opened by passing all five cold-start questions. That felt like a green light. It
wasn't.

`START_HERE_PROMPT.md` prints the expected answers to those five questions in the same file. They
verify **that the files were opened**. Nothing in the session verifies that answer #12 came from the
same place answer #2 did. And the five questions are all *lookups* — a value, a budget, a default
flag. Not one is a mechanism question.

Every error in the session was on a **mechanism** question. The gate was placed where failure was
least likely.

> **Fix:** the cold-start check now has a sixth question that cannot be answered without doing
> arithmetic on the corpus rather than reading a number out of it. See the patch to
> `START_HERE_PROMPT.md`.

---

## Cause 2 — "Conceptual, not numerical" was read as "from concepts, not from files"

This is the biggest single factor and it came from a directive **you** gave, for good reasons.

Your instruction was: *"I don't know the exact number because I am not an engine"* → stop asking
decimal-recall questions. Entirely correct as pedagogy. But look at what happened to the citation
discipline across the two logs:

| | `STUDY_NOTES.md` (earlier session) | `STUDY_SESSION_LOG.md` (this one) |
|---|---|---|
| Questions | mechanism + numbers | conceptual MCQs |
| Answers carrying a source pointer | **11 of 11** | **0 of ~30** |
| Material errors found on audit | 0 | 8 |

Not one line of the newer log carries a citation. Once no answer has to name a file, the rule "you
may not state a number from memory" (`START_HERE_PROMPT.md` §2) has nothing enforcing it — the
citation *was* the enforcement mechanism. And the numbers that then arrived from memory were exactly
the memorable-looking ones: `MinibatchSize = 64/256`, `768 channels`, `b = 31`, `99% of visits`,
`800–2,000 nodes`. Every one is a plausible round number from the AlphaZero literature. None is from
this engine.

> **The lesson is not "go back to numerical questions."** It is that *conceptual* is a property of
> the **question**, and *sourced* is a property of the **answer**, and dropping the second because
> you changed the first is a non-sequitur. A conceptual answer still has to be read out of a file.

---

## Cause 3 — The corpus itself sets the network trap (our defect)

The worst error — "15 Residual/Attention blocks (768 channels)" — is one the corpus practically
dictates.

- `ENGINE_REFERENCE.md` §1 labels **BT3** `Primary Network Weights` and **791556**
  `Diagnostic Network Weights`. For the product that is true. For this study corpus it is
  **backwards**: every measured number in the book and in Guide Parts 0–4 came from 791556.
- Where is that said? `ch01:359` and `ch11:310` — two lines, deep in the book, in prose. Not in
  `KNOWLEDGE_BASE.md`. Not in `CONCEPT_INDEX.md`. Not in `ENGINE_REFERENCE.md`, which is the file
  the prompt sends you to for architecture.
- Meanwhile the guide **draws BT3** in Part 5 (FIG-5.1: "15 transformer encoder layers, 24 heads")
  on the same continuous read as Part 2's 791556 search numbers, with no marker separating them.
- And both nets have **15** of something. 15 SE blocks; 15 encoders. The number that would normally
  catch a conflation matches.

So: authoritative file says BT3 is primary, guide shows BT3's diagram, both nets say 15, and the
correction lives in two prose lines in chapters 1 and 11. **Merging them is the reading the corpus
invites.** A careful human reader would make the same error.

> **Fix:** `guide/kb/ADDENDUM.md` §A, plus a pointer at the top of `KNOWLEDGE_BASE.md`.

---

## Cause 4 — A fabricated citation was already sitting in the reference shelf (our defect)

`GLOSSARY.md`'s **Virtual Loss** entry read:

> **Action Location**: `ENGINE_REFERENCE.md` (`--virtual-loss`).

There is no `--virtual-loss` flag. The word "virtual" does not occur **once** in the 91-option dump
(`grep -c virtual raw/lc0_help.txt` → `0`). The same entry's `ch08:L125` pointer also missed — L125
is tree reuse; virtual loss is L35–64.

This matters more than one bad line, because of what the corpus asks a reader to do. The rule is
"every claim carries a pointer." A reader who honours that rule and follows this pointer arrives at
a flag that does not exist — and the citation format made the claim *more* trustworthy, not less.

> **A citation is a claim too, and ours were not all audited.** `ADDENDUM.md` §F, and the glossary
> entry is fixed.

---

## Cause 5 — Reasoning forward from the formula instead of reading the table

The Qb8 answer is the most interesting failure, because it is *good reasoning* producing the wrong
mechanism.

The chain is impeccable: `S = Q + U`; a refuted-looking move gets one visit; it returns `Q = 0.98`;
`0.98` now dominates every rival's `Q`; therefore later visits pour into it. That is a correct
derivation from the selection rule. It is also, in this position, false.

The measured table (`engine_data.json → positions.opera_before_qb8.ladder`) says Qb8+ sits at
**3 visits** at 1600 nodes and **still 3 visits** at 6400 — four times the compute, *zero* change to
any number in the table — and gets played anyway, beating a move examined 172 times. The real
mechanism is that `Q = 1.0` is a **proof** of forced mate, tracked separately, outranking sampling,
and search halts rather than re-sampling a solved subtree. `KNOWLEDGE_BASE.md` §3 states this
outright, bolded, as one of "three things this single table proves."

**The engine has behaviours that do not follow from `S = Q + U`.** Proven wins, terminal nodes,
smart pruning, tree reuse. Deriving forward from the one formula everybody remembers will get them
wrong every time, confidently, and with a valid-looking argument attached. When a claim is about
*what the engine did*, the table is the authority — not the formula, even when the formula is
correctly applied.

---

## The pattern, in one line

**Seven of the eight errors are recall of the AlphaZero-family literature standing in for
measurement of this engine.** `768` channels, minibatch `256`, `b = 31`, the cpuct formula without
its `+1`, `N(parent) = Σ children`, `--policy-temperature`, `puct_utility.h`, "high Q floods the
subtree". Each is the *textbook* version. Each is the version you would get from a paper rather than
from `lc0.exe` v0.32.1 with `791556.pb.gz` on this machine.

That is precisely the failure mode `START_HERE_PROMPT.md` §2 exists to prevent — and it did prevent
it in the earlier session, where citations were enforced. It failed here because the enforcement was
procedural (cite everything), the procedure lapsed quietly, and nothing detected the lapse.

**The guardrail that works is not "be accurate." It is "name the file."** An answer that cannot name
a file is not a well-remembered answer; it is an unsourced one, and in this corpus those have run
about 25% wrong.

---

## What changed as a result

| Change | File |
|---|---|
| 8 corrections applied, questions preserved, correction ledger added | `STUDY_SESSION_LOG.md` §7 |
| New verified material: net attribution, `N = 1 + Σn`, exact cpuct, run configuration, policy temperature, virtual loss vs. flags, proof-beats-sampling, declared gaps | `guide/kb/ADDENDUM.md` |
| Fabricated `--virtual-loss` citation removed; collision citation line-range fixed | `guide/kb/GLOSSARY.md` |
| Addendum added to the corpus list; four new declared gaps; citation rule tightened; 6th cold-start question | `START_HERE_PROMPT.md` |
| One-page revision sheet built from your own questions | `HEADSTART.md` |

## What is still unaudited

Honest statement of scope. This audit covered `STUDY_SESSION_LOG.md` only.

- `STUDY_NOTES.md` (the earlier session) was spot-checked — its numbers verify, but its citation
  **paths** are stale (`docs/design_session/...`, from before the reorganisation into `docs/study/`).
  The pointers are correct in content and broken as links.
- `KNOWLEDGE_BASE.md` also still carries `docs/design_session/` paths throughout §7.
- `GLOSSARY.md` has ~159 entries. **One** was audited end-to-end, because a session answer happened
  to lean on it, and it was wrong. That is a sample of one; it is not evidence the other 158 are
  fine, and it is not evidence they are broken. It is a reason to check.
