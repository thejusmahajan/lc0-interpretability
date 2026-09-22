# THEME DEFINITIONS — the theoretical ground truth for tactical themes

> **Purpose.** Every agent and every metric that CLAIMS a position has a tactical theme
> ("sacrifice", "fork", "pin", …) MUST ground that claim in a concrete, checkable board/
> material/line fact — the way Lichess actually defines it — NOT in an eval or "complexity"
> heuristic. This file is the source of truth; `backend/lichess_tagger/cook.py` + `util.py`
> are the reference IMPLEMENTATION (material-based, line-based). Read this before touching any
> theme/sacrifice/steer code or writing any UI copy that names a theme.

## The cardinal rule (why this file exists)
**Complexity / sharpness ≠ a tactical theme.** A move being LC0's "sharpest playable
alternative" (high `complexity`) tells you the position is hard — it does NOT tell you a
sacrifice, fork, or anything else is present. Themes are defined by CONCRETE facts:
- **sacrifice** → material given up over the forced line,
- **fork / pin / skewer / discovered attack** → specific piece geometry,
- **hanging piece / trapped piece** → capturable material.
A theme claim with no such fact behind it is wrong, however "sharp" the position looks.

### The bug this replaces (do not repeat it)
`metrics.py` `had_tal_move` was set purely from `complexity` differential
(`tal_move.complexity - objective_best.complexity >= threshold`) with **no material check**.
It labelled quiet moves (e.g. Qb3 conceding 52cp) as "sacrifices/Tal", and the leader wrongly
concluded "the London is sharp / has 13 sacrifices." **That conclusion was unfounded.** A
correct sacrifice count needs the material-over-line test below.

## SACRIFICE — the authoritative definition (from `cook.py:184` `sacrifice()`)
A move/line is a **sacrifice** iff, over the FORCED solution line, from the sacrificing side's
POV, material drops by **≥ 2 points** relative to the starting position at some node *after*
that side moves — and the drop is not merely a promotion artefact.
- Material values (`util.values`): P=1, N=3, B=3, R=5, Q=9 (king excluded).
- `material_diff(board, pov)` = (pov material) − (opponent material).
- Line-based: you must look at the CONTINUATION (the forced tactical sequence), not one move.
- Threshold ≥2 = a real investment (≥ a minor piece net), not a 1-pawn nuance.
- Exclude promotions (they distort the material count).
- **Compensation is implied by the puzzle being winning/holding** — a sacrifice is only a
  sacrifice if the line is objectively sound (otherwise it's just a blunder). So a real
  sac-training position = down ≥2 material over the line AND the eval stays good for the
  sacrificer.

### Implication for OUR pipeline (what "detecting a sacrifice" actually requires)
The current `steer_findings` have a single `steer` move + eval + complexity — **not enough** to
decide "sacrifice." To label a steer position a real sacrifice we must:
1. Generate the forced continuation line (engine PV, a few plies) after the steer move.
2. Apply the `cook.sacrifice`-style test: `material_diff` from the mover's POV drops ≥2 over
   that line and stays down (not immediately recaptured), while the eval remains good.
Reuse `lichess_tagger` (`material_diff`, `values`) — do NOT re-derive material counting. Until
a position passes THIS test, it must NOT be called a sacrifice (call it "sharp position" if you
must surface complexity, clearly distinct from "sacrifice").

## OTHER THEMES — ground each in `cook.py` (material/geometry, never eval)
Use these as the definition; `cook.py` is the implementation to reuse/mirror:
- **fork** (`cook.fork`): one piece attacks ≥2 enemy pieces of higher combined value / a king.
- **hanging_piece** (`cook.hanging_piece`): a capturable piece is won for free (material_diff up).
- **trapped_piece** (`cook.trapped_piece`): a piece with no safe squares, lost by force.
- **pin / skewer** (`cook.pin_*`, `cook.skewer`): a higher-value piece behind/ahead on a line.
- **discovered_attack / discovered_check / double_check** (`cook.discovered_*`, `double_check`).
- **deflection / attraction / interference / overloading / intermezzo / x_ray / clearance**
  (`cook.*`): each defined by a concrete move-geometry fact over the line.
- **advanced_pawn** (`cook.advanced_pawn`): a pawn pushed to the 6th/7th driving the tactic.
- **exposed_king** (`cook.exposed_king`): king stripped of shelter and attackable.
- **quiet_move / defensive_move / check_escape** (`cook.*`): NON-forcing/defensive resource —
  explicitly the OPPOSITE of a sacrifice; must never be conflated with one.

## Directive for agents & metrics
- Any new theme detector reuses `lichess_tagger` primitives (`material_diff`, `values`,
  `is_capture`, `moved_piece_type`) and mirrors the `cook.py` definition; it does NOT invent an
  eval/complexity proxy for a theme.
- UI copy naming a theme must reflect the real definition (a "sacrifice" card must show material
  actually given up + the winning line — not just "complexity 0.7").
- `complexity`/`steer` may remain as a *sharpness* signal, but must be LABELLED as sharpness,
  never "sacrifice" / "Tal", unless the position passes the material-over-line sacrifice test.
