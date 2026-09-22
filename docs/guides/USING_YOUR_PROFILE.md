# Using a diagnosis profile (the `training.zip` you produced)

You ran the Colab A100 pipeline and dropped its `data/training/` into the repo.
Here's how to actually *see and use* it.

## What's in `data/training/`
- `profile.json` — the weakness diagnosis the app serves (findings, blind-rates by
  phase/clock/opening/motif, confirmed mistakes, steer findings).
- `repertoire.json` + `repertoire_weakness_{white,black}.json` +
  `repertoire_sacrificial_{white,black}.json` — the training repertoires.
- `profiles/…json` — timestamped archives. `cache/*.jsonl` — engine caches (leave them).

## View it in the app
1. **Backend** (from the `cszero` env — see `HOW_TO_RUN.md` for the exact command):
   `C:\Users\Admin\miniconda3\envs\cszero\python.exe -m uvicorn backend.app:app`
   (it reads `data/training/profile.json` on the training endpoints).
2. **Frontend**: `cd frontend && npm run dev`, open the local URL.
3. In the UI, the pieces to look at:
   - **"What to Work On"** — the multi-dimension weakness ranking. For this run the
     signal is **middlegame** (blind_rate 0.18 vs opening 0.08 / endgame 0.07) and
     it's roughly flat across the clock → **positional, not time-pressure**.
   - **Repertoire** — the weakness + sacrificial (Tal) lines, both colors.
   - **Puzzles / drills** — critical-node SRS drills from the repertoire trees.
   - **Tactical steering** — the "you could have played the sharper sound move" finds.

## Caveats for THIS particular run (know before you trust a panel)
- **Tactical steering is ~77% complete** (the run hit `steer_search_budget`;
  `steer_budget_exhausted: True`). The steer finds you see are real but partial. A
  re-run with `STEER_SEARCH_BUDGET=50000` (already set in Cell 6) gives full coverage.
- **`by_opening` is empty/`'???'`** — `openings.classify` isn't matching the subset,
  so the per-opening breakdown and repertoire-by-opening render sparse. This is a
  known bug under investigation (`openings.py` SAN parsing); don't read the
  opening-specific panels as final yet.

## Refreshing after a new run
Replace the contents of `data/training/` with the new `training.zip`'s
`data/training/`, then restart the backend. To keep a copy, the run already archived
one under `data/training/profiles/`.

## Wisest use right now
Trust the **weakness ranking, phase/clock blind-rates, confirmed findings, and the
repertoires** — those are complete. Treat **steering** as a strong-but-partial
preview and **openings** as pending the classify fix. The headline to act on:
**middlegame, positional.**
