# The study folder

Everything needed to study how Leela Chess Zero actually thinks, and nothing else.

## Start here

0. **Revising, not reading?** Open **`HEADSTART.md`** — one page, ten minutes, built from the
   questions you have actually asked.
1. Open **`guide/neural_mcts_visual_guide_v2.pdf`** — 44 pages, the document itself.
2. To ask questions about it, start a fresh agent session and paste
   **`START_HERE_PROMPT.md`**. Run its 6-question cold-start check before trusting anything.
   Questions 1–5 check the files were read; **question 6 checks they are being computed with**,
   and it is the one that catches a session answering from memory.
3. Keep your questions in **`STUDY_NOTES.md`** and **`STUDY_SESSION_LOG.md`**. They have driven
   every improvement to the document so far — what confused you is better evidence than what
   anyone thought was missing.
4. Before trusting a past session's answers, see **`ANSWER_AUDIT.md`**: the 2026-08-09 session got
   about a quarter of its mechanism claims wrong, and three of the five root causes were defects in
   this corpus rather than in the model.

## What is here

```
docs/study/
  HEADSTART.md           one-page revision sheet, organised by your own questions
  START_HERE_PROMPT.md   the study-companion prompt — the only one; paste it verbatim
  STUDY_NOTES.md         your running Q&A log (earlier session, fully cited)
  STUDY_SESSION_LOG.md   your MCQ session — questions preserved, answers re-verified
  STUDY_CROSS_ENTROPY_AND_OPTIMIZATION.md  Cross-Entropy loss in LC0 vs MSE, MLE, and PyTorch
  ANSWER_AUDIT.md        why that session's answers drifted, and what got fixed
  guide/                 the visual guide
    neural_mcts_visual_guide_v2.pdf      <- the document
    kb/                                  <- the reference shelf
      CONCEPT_INDEX.md     routes a question to the file that answers it
      GLOSSARY.md          159 sourced terms and symbols
      ENGINE_REFERENCE.md  91 UCI options + net architecture, measured from lc0.exe
      ADDENDUM.md          gaps + traps found by audit; outranks the rest on conflict
      raw/                 the unedited engine captures those were parsed from
    KNOWLEDGE_BASE.md      the verified facts behind the guide
    parts/ figures/ tools/ tikz/         <- build machinery; not reading material
    VISUAL_PLAN.md LATEX_SPEC.md BUILD_REPORT.md   <- how it was made and audited
  book/                  the long-form treatment the guide distils
    neural_chess_self_tutor.pdf
    chapters/ch01–ch16   read these when the guide is not deep enough
    data/                measured LC0 output + Stockfish ground truth
    tools/               the scripts that produced that data
```

## The rules the material is built on

- **LC0 and Stockfish are the only sources of chess truth.** No language model reasons about
  chess here. A fluent wrong explanation is worse than silence.
- **Every printed number traces to a source** — a JSON path, a chapter line, or a capture from
  the engine binary. The figure generator fails the build rather than emitting an untraceable
  digit.
- **Unverified ideas are visibly marked.** Four confidence tiers: measured, established,
  published research, and this project's hypothesis. The layer-role labels and the
  suppressed-win probe story are hypotheses, and the document says so on the page.

## Rebuilding

Nothing here needs rebuilding to be read. If you change a source:

```bash
cd docs/study/guide
python tools/make_figures.py                       # regenerates figures + provenance; fails on mismatch
TEXINPUTS="./tikz;./;" pdflatex -interaction=nonstopmode neural_mcts_visual_guide_v2.tex   # twice

cd kb && python dump_engine_reference.py           # re-measures the engine; fails on unknown flags
```

`guide/` and `book/` must remain siblings — the preamble and the figure generator both rely on
it. Page renders (`page_*.png`) are throwaway; they are gitignored and safe to delete.

## What is deliberately not here

Historical work orders and superseded drafts live in `archive/` at the repository root. They
describe defects in earlier versions, nearly all since fixed, and reading them will produce
confident and wrong statements about the current document. `START_HERE_PROMPT.md` §1a tells the
agent to stay out of them; that exclusion is load-bearing, not tidiness.
