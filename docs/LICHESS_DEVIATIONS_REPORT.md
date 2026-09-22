# LICHESS DEVIATIONS REPORT — our theme definitions vs Lichess logic

Leader audit (2026-07-27), on the user's instruction to recheck ALL definitions against Lichess
and report deviations. Reference = `backend/lichess_tagger/` (Lichess's real puzzle tagger).
**Verdict: the tactical-theme layer is unreliable.** Two independent "sacrifice" systems, both
broken; the motif tags — though routed through the real `cook()` — are FED INCORRECTLY, so the
outputs (finding `motifs`, `by_motif`, usual-suspects theme clustering, SacDrill, sharp-openings)
cannot be trusted as they stand.

## D1 — `had_tal_move` / "sacrifice" has NO material check  [metrics.py] — SEVERITY: CRITICAL
`metrics.py:509-516`: `had_tal_move = (tal_move.uci != best.uci and tal_move.complexity -
best.complexity >= threshold)`. Pure **complexity** differential; grep shows no `material`/
`is_capture`/`piece_value` anywhere in the steer logic. Quiet moves get labelled "sacrifice/Tal".
Powers: SacDrill, sharp-openings sac counts, "steer" moves. **Not Lichess at all.**
Fix: a sacrifice must be detected by material over a forced line (Lichess `cook.sacrifice`), not
complexity. `complexity`/`steer` may survive ONLY relabelled as a "sharpness" signal.

## D2 — Motif tagging feeds `cook()` the WRONG POV  [tactics.py] — SEVERITY: CRITICAL
`lichess_tagger/model.py:76`: `pov = not game.turn()` — correct for a Lichess puzzle whose game
starts BEFORE the opponent's setup move. But `tactics.py:analyze_pv` builds the game AT the flagged
position, where **our solver IS the side to move**, and adds the PV starting with the solver's move.
So `pov` becomes the **opponent**. Empirical proof (finding `g004-p031`): side-to-move = White, but
`Puzzle.pov = Black`; `material_diff` over the line = `[…,-5,-2,-2,-2,1]` (Black ends down material —
White *won* material) yet it is tagged **"sacrifice."** Every material/king/geometry theme
(sacrifice, exposedKing, hangingPiece, fork, deflection, skewer…) is analyzed from the wrong side ⇒
mis-attributed.

## D3 — Dummy `cp=500` fakes the eval-based themes  [tactics.py] — SEVERITY: HIGH
`tactics.py:33` passes `cp=500`; `cook.py:55-57` uses `puzzle.cp` (`>600` crushing, `>200`
advantage). So **every** position is force-tagged **"advantage"** regardless of the real eval
(this is why every finding carried "advantage"/"veryLong"). The eval-based themes
(advantage/crushing/equality) are meaningless.

## D4 — Mainline structure mismatch (no opponent setup move)  [tactics.py] — SEVERITY: HIGH
Lichess mainline = [pre-setup position, opponent setup move, solver move, …]; `cook` slices it by
that parity (`mainline[1::2]`, `[::2]`). `analyze_pv` builds a mainline that STARTS with the solver's
move (no setup move), so the parity is shifted one ply — cook reads the wrong nodes as the solver's.
Compounds D2.

## D5 — Applying a puzzle-tagger to a non-puzzle PV  [tactics.py] — SEVERITY: MEDIUM
`cook` is designed for curated, forced puzzle mainlines. `analyze_pv` feeds LC0's best-play PV
(not necessarily forced/only-move), so even with D2–D4 fixed the tags are noisier than Lichess's.

## D6 — `complexity` components & positional `concepts` are CUSTOM, not Lichess — SEVERITY: INFO
`metrics.py` complexity (decisiveness/narrowness/policy_trap/attention) and `concept_mapper`
concepts (piece_activity/center_control/…) are OUR heuristics; Lichess has no such themes. They are
legitimate as *sharpness*/coaching signals BUT must never be presented as Lichess tactical themes.

## Downstream impact (what is currently untrustworthy)
- `finding.motifs` and `aggregates.by_motif` — mis-attributed (D2–D4).
- **Usual-Suspects clustering** (Sprint 1) keys on `motifs` ⇒ the "sacrifice 44 games / defensiveMove
  84 games" ranking is built on bad tags — **suspect** (must be re-verified after the fix).
- **SacDrill + Sharp-Openings sac counts** (had_tal) — invalid (D1). Relabel/disable until fixed.
- The leader's earlier "London has 13 sacrifices / is sharp" — **retracted** (D1).

## Fix direction (leader-owned; the next priority before more UI work)
1. **Drive `cook()` correctly in `tactics.py`:** set the game up ONE ply earlier (include the
   opponent's move that reached the flagged position) so `pov = not game.turn()` = our side to move
   AND the mainline parity matches Lichess; pass the REAL eval as `cp` (not 500). Then the material/
   eval/geometry themes become correct. (Alternatively compute themes with an explicit correct pov.)
2. **Replace the `had_tal` "sacrifice"** with a real material-over-line detector per
   `docs/THEME_DEFINITIONS.md` (reuse `lichess_tagger.material_diff`); relabel `complexity`/`steer`
   as "sharpness".
3. **Re-run** the diagnosis (or re-tag the existing PVs) after the fix, then re-verify usual-suspects
   / by_motif / sharpness on corrected tags — no theme claim reinstated until it reconciles here.
