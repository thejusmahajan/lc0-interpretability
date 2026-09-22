# LATEX SPEC — *Inside LC0's Mind: A Visual Guide* (v2, illustrated)

How to build the document. Companion to `KNOWLEDGE_BASE.md` (what is true) and `VISUAL_PLAN.md`
(what to draw).

**The drawing macros already exist and are compile-tested on this machine.**
`docs/design_session/visual_guide/tikz/mctsviz.sty`. Read it before writing a figure — it is
short and heavily commented. Do not write raw `\node`/`\draw` for tree figures; if a picture
needs something the macros cannot express, **add a macro to the `.sty` and document it there**,
so the next figure gets it too.

---

## 1. File layout

```
docs/design_session/
  visual_guide/
    KNOWLEDGE_BASE.md          <- facts (read-only for the worker)
    VISUAL_PLAN.md             <- storyboard (read-only for the worker)
    LATEX_SPEC.md              <- this file
    neural_mcts_visual_guide_v2.tex     <- the master document (NEW)
    preamble_visual.tex                 <- preamble, wraps the book's + mctsviz
    tikz/
      mctsviz.sty              <- the drawing grammar (EXISTS, tested)
      _probe.tex               <- the compile test for the grammar (EXISTS, passes)
    figures/
      fig_2_0.tex … fig_2_8.tex        <- GENERATED, do not hand-edit
      fig_3_1a.tex …                   <- GENERATED
      fig_1_1a.tex …                   <- hand-written (no numbers on them)
    tools/
      make_figures.py          <- the generator (NEW — see §5)
      figure_data.json         <- GENERATED intermediate, committed for auditability
```

The v1 files (`neural_mcts_visual_guide.tex/.pdf`) **have been deleted** — deliberately, so
nothing can be copied forward from them by accident. `KNOWLEDGE_BASE.md` §0 records what was
wrong with them. v2 is a new document at a new path; it is not an edit of v1.

---

## 2. Preamble

Create `preamble_visual.tex`. It reuses the book's preamble so the two documents are visually the
same family, then adds the tree grammar:

```latex
% preamble_visual.tex
\input{../book/preamble.tex}      % colours, tcolorbox tiers, xskak defaults, boxes
\usepackage{mctsviz}              % the tree-drawing grammar (tikz/ must be on TEXINPUTS)
\usepackage{graphicx}
\usepackage{subcaption}
\captionsetup{font=small,labelfont=bf}
```

Master document:

```latex
\documentclass[11pt,a4paper]{report}
\input{preamble_visual.tex}
\title{...}\author{...}\date{\today}
\begin{document}
\maketitle
\tableofcontents
\include{parts/part0_legend}
\include{parts/part1_partners}
...
\end{document}
```

**`mctsviz.sty` must be findable.** Either build from inside `tikz/`, or set
`TEXINPUTS=.//;` , or simplest and preferred: `\usepackage{tikz/mctsviz}` is *not* reliable —
instead copy the build command in §6, which sets `TEXINPUTS` explicitly.

### 2.1 Honesty tiers — inherited from the book, and mandatory

`../book/preamble.tex` already defines these environments. Every figure sits inside the one that
matches its tier in `VISUAL_PLAN.md`:

| Environment | Frame colour | Use for |
|---|---|---|
| `\begin{realdata}...\end{realdata}` | teal | anything with a measured number on it |
| `\begin{established}...\end{established}` | blue | formulas, architecture, mechanism |
| `\begin{researchfinding}...\end{researchfinding}` | teal | published results (cite them) |
| `\begin{hypothesis}...\end{hypothesis}` | purple | our unverified ideas — PART 5 |
| `\begin{keyidea}` / `\begin{pitfall}` | green / red | the one-line takeaways |

A figure with a number on it that is **not** inside `realdata` is a bug. A figure in PART 5 that
is **not** inside `hypothesis` (or explicitly captioned as a cartoon) is a serious bug.

---

## 3. The drawing grammar — API reference

All of the following are defined and compile-tested in `tikz/mctsviz.sty`.

### 3.1 Node styles

| Style | Meaning — this is fixed and may not be reused for anything else |
|---|---|
| `vgroot` | the root position |
| `vgnode` | an expanded node (the network has evaluated it) |
| `vgunvisited` | **dashed grey** — never visited; its `Q` is a *guess* (FPU), not a measurement |
| `vgnew` | **thick green** — created on this iteration |
| `vgrefuted` | **red** — visited, and `Q` collapsed |
| `vgghost` | faint dashed — how it stood one frame ago |

The dashed/solid distinction (guess vs. measurement) is the most important line in the grammar.
Never draw an unvisited node solid.

### 3.2 Visit heat and edge weight

```latex
\vgheat{<n>}{<nmax>}        % sets colour `vgfill'
\node[vgnode, fill=vgfill] (kd6) at (-4.2,-2.2) {Kd6\\ \tiny $n{=}4$\ \ $Q{=}0.98394$};

\vgedgewidth{<n>}{<nmax>}   % sets \vgEW (a number, in pt)
\draw[vgedge, line width=\vgEW pt] (root) -- (kd6);
```

`nmax` is the largest visit count **in that frame** — pass the same `nmax` to every call in a
frame or the heat scale lies.

### 3.3 The S-bar strip — the figure that makes PUCT visible

```latex
\vgsbaraxis{<xmin>}{<xmax>}{<gridline value>}
\vgsbarS{<x>}{<Q>}{<U>}{<label>}{<state>}     % state: sel | meas | fpu | dead
```

Solid segment = `Q` (earned by measurement); pale segment stacked on top = `U` (the curiosity
bonus, borrowed not earned); total height = `S`. **The tallest bar is the move the search picks.**
That one sentence is the whole of PUCT, and the reader sees it instead of being told it.

- `sel` — gold: the bar that won this iteration
- `meas` — blue: measured, but not selected
- `fpu` — grey: `Q` is a guess
- `dead` — red: measured and refuted

The four bar columns **must** be in the same left-to-right order as the four child nodes above
them, so the reader can drop a vertical line from node to bar.

### 3.4 Step annotations

```latex
\vgselectmark{<node>}                    % gold ring: chosen this iteration
\vgnewmark{<node>}                       % green burst: did not exist one frame ago
\vgbackup[<bend>]{<from>}{<to>}{<text>}  % curved return; SHORT HOPS ONLY (see below)
\vglane{<from>}{<to>}{<lane x>}{<lane y>}{<text>}   % orthogonal return; use for everything else
\vgdeltaup{<node>}{<text>}               % green tag under a node
\vgdeltadown{<node>}{<text>}             % red tag under a node
\vglegend                                % the full legend block (print once, FIG-0.1)
```

**Backprop routing rule.** A returning value must never cross a node it does not connect.

- `\vglane` routes down from the source, along a floor below the tree, up the outer margin, and
  into the target — using **real waypoints**, so the path provably clears every node, and placing
  the label **at the lane** rather than along the path. Use it for any return from depth 2 or
  deeper. Choose the side opposite the walked path: right lane (`x = 6.5`) when the walked path
  is on the left, left lane (`x = -7.2`) when it is on the right.
- `\vgbackup` is a curve and only safe for a short hop that clears everything anyway (e.g. a
  depth-1 child back to the root).

> **Why `\vgbackup` cannot be steered around a node.** Its label is placed at `pos=0.88` *along
> the path*, so changing the curve moves the label somewhere unpredictable. And `to[out=…,in=…]`
> control points are **not waypoints** — a cubic Bézier is pulled toward them but never reaches
> them. Setting a control point at `x = 6.5` left the actual arc peaking near `x = 4.2`, straight
> through the node sitting there. Both of these were hit for real. Use `\vglane`.

### 3.5 Boards

```latex
\vgboardnode{<name>}{<coord WITH parens>}{<fen>}{<boardfontsize>}
\vgboardnodex{<name>}{<coord>}{<fen>}{<size>}{<extra chessboard keys>}
```

Note the coordinate carries its own parentheses: `\vgboardnode{b1}{(0,0)}{4k3/8/...}{11pt}`.

**Minimum sizes:** 11pt inside a tree node, 15–19pt standalone. Below 11pt the hatched dark
squares turn to mush.

**Safe highlight idioms — copy verbatim:**

```latex
% outline a square (does NOT hide the piece standing on it)
pgfstyle=border, color=PitfallRed, linewidth=0.3ex, markfields={d7,e7,f7}

% a move arrow
pgfstyle=straightmove, color=GoldPath, arrow=to, markmoves={e6-f6}
```

> ### ⚠ Never fill a square
> `pgfstyle=color` + `markfields` paints an **opaque** patch over the field and **silently
> deletes the piece standing on it**. This was verified while writing these macros: tinting the
> dark squares of the K+P position made the **e5 pawn vanish** — no error, no warning, just a
> different position on the page from the one all the numbers describe. Outline squares. Never
> fill them. If you think you need a filled square, you need a `border` mark.

### 3.6 Two TeX traps already paid for

1. `\chessboard` inside a TikZ node fails with *"A node must have a (possibly empty) label text"*
   unless the FEN is brace-wrapped (`setfen={<fen>}`) **and** the board is in an `\mbox`.
   `\vgboardnode` does both; that is why it exists.
2. A macro written as `\node at (#1)` and called with `\x{(0,0)}` produces `at ((0,0))` and the
   *same* misleading error. Macros here take coordinates with their own parentheses.

---

## 4. Canvas coordinates — fixed for the whole of PART 2

Hard-code these. They are the reason consecutive frames are comparable.

**These are the as-built values, verified identical across `figures/fig_2_0.tex` … `fig_2_8.tex`.**
The first draft used a 2.8 cm column pitch; it was widened to 3.0 cm because at 20 mm node width
the depth-2 row collided (Kf7 and Kf8 overlapped by 4 mm). Do not "restore" the narrower values.

| Element | Coordinate |
|---|---|
| root | `(0,0)` |
| child `Kd6` | `(-4.5,-1.8)` |
| child `Kf6` | `(-1.5,-1.8)` |
| child `Kf5` | `(1.5,-1.8)` |
| child `Kd5` | `(4.5,-1.8)` |
| depth-2 `Kd8` / `Kf7` (under Kd6) | `(-5.8,-3.6)` / `(-3.4,-3.6)` |
| depth-2 `Kf8` (under Kf6) | `(-1.0,-3.6)` |
| depth-3 row | `y = -5.4`, aligned with its parent's `x` |
| S-bar columns | same `x` as the child columns |
| backprop lane | `x = 6.5` (right) or `x = -7.2` (left), floor at `y = -4.5` |

**Clearance rule.** Node width is 20 mm, so every node spans its centre `±1.0`. Before fixing any
row, write out each node's x-extent and show the gaps are ≥ 4 mm — including against the node
diagonally beside it, which is the check that was missed the first time. The same arithmetic
applies to labels: a backprop label is ~1.2 cm wide and must clear the nearest node's border.

Route every backprop path that would otherwise cross a node row with `\vglane` (§3.4), never with
a curved `\vgbackup` — a Bézier does **not** pass through its control points, so "put the control
point at `x=6.5`" does not keep the curve out of a node sitting at `x=4.5`.

**Do not use an automatic tree layout package** (`forest`, `tikz-qtree`). They re-flow when a
node is added — which is exactly the thing this document must never do.

---

## 5. Figures are generated, not typed

Every figure carrying a number is emitted by a script. This is not a preference: it is the
control that makes it *impossible* for a transcription slip or an invented digit to reach the
page.

### 5.1 `tools/make_figures.py`

**Inputs (read-only):**
- `../book/data/engine_data.json`
- `../book/data/children_data.json`
- `../book/tools/simulate_search.py` — import `simulate()` from it; **do not reimplement PUCT.**

**Outputs:**
- `figures/fig_*.tex` — one standalone `tikzpicture` per frame
- `tools/figure_data.json` — every number the figures use, with the JSON path it came from
- stdout: a provenance report, one line per printed number

**Required behaviour:**

1. `simulate_search.simulate()` returns per-iteration `N`, `Q`, `U`, `S` for all four moves plus
   the selection. The FIG-2.x frames are a direct rendering of that structure.
2. **Self-check before writing anything.** Re-run the simulator's own cross-check against
   `engine_data.json` at `nodes=8`. If any visit count or `Q` mismatches, **print the mismatch
   and exit non-zero without writing a single file.** The chapter must not be able to drift from
   the engine.
3. Every number printed into a figure is formatted from the JSON value — never a literal in the
   Python source. If a literal number appears in `make_figures.py` outside of layout constants
   (coordinates, sizes, colours), that is a bug.
4. Rounding is declared once, at the top, and applied uniformly: `Q`, `U`, `S`, `V` to **5
   decimals**; priors as percentages to **2 decimals**; visit counts as integers.
5. Generated files carry a header comment: `% GENERATED by tools/make_figures.py — do not edit.
   Source: engine_data.json -> positions.kp_endgame.ladder.128`.

### 5.2 The build order

```
python tools/make_figures.py        # regenerates figures/ and figure_data.json
pdflatex ... (twice)                # TOC and \ref
```

If `make_figures.py` exits non-zero, the document does not get built. That is the gate.

---

## 6. Build commands (verified on this machine)

TeX Live 2019, `pdflatex` at `C:/texlive/2019/bin/win32/pdflatex`. Run from
`docs/design_session/visual_guide/`:

```bash
# Bash tool (Git Bash):
TEXINPUTS="./tikz;./;" pdflatex -interaction=nonstopmode neural_mcts_visual_guide_v2.tex
TEXINPUTS="./tikz;./;" pdflatex -interaction=nonstopmode neural_mcts_visual_guide_v2.tex
```

```powershell
# PowerShell:
$env:TEXINPUTS = ".\tikz;.\;"
pdflatex -interaction=nonstopmode neural_mcts_visual_guide_v2.tex
pdflatex -interaction=nonstopmode neural_mcts_visual_guide_v2.tex
```

Check the macro grammar still works at any time:

```bash
cd tikz && pdflatex -interaction=nonstopmode _probe.tex     # must exit 0
```

**Look at what you built.** `pdftoppm` is installed:

```bash
pdftoppm -r 110 -png neural_mcts_visual_guide_v2.pdf page
```

Then open the PNGs. A figure that compiles is not a figure that reads. Overlapping labels,
collided arrows and clipped boards all compile perfectly happily.

---

## 7. Acceptance checks

A frame is done when all of these hold:

- [ ] `pdflatex` exits 0 with no `Overfull \hbox` over 10pt on the figure's page.
- [ ] The page has been **rendered to PNG and looked at**. No label sits on a node, no arrow
      crosses a node it does not connect, no board is clipped.
- [ ] Every printed digit traces to a JSON path recorded in `figure_data.json`.
- [ ] Coordinates are **byte-identical** to the previous frame in the family for every element
      that both frames share. (`diff fig_2_3.tex fig_2_4.tex` should show only the intended
      changes — this is a real, runnable check and you should run it.)
- [ ] At most two things changed since the previous frame.
- [ ] The figure is inside the tcolorbox tier that matches `VISUAL_PLAN.md`.
- [ ] The "what changed" line names the change, not the step number.
- [ ] No colour appears that is not in the `\vglegend`.

The whole document is done when, additionally:

- [ ] `python tools/make_figures.py` exits 0 and its self-check against the engine passes.
- [ ] No sentence asserts a chess fact that is not in `KNOWLEDGE_BASE.md`.
- [ ] Nothing from v1's `e6+` narrative survives anywhere, including in captions.
- [ ] Every PART 5 figure is visibly marked as hypothesis or cartoon.
