# How to Run — Chess Speak Out Loud

> **This is the authoritative runbook (Windows dev machine).** If any other doc disagrees with this
> file, this file wins. Last verified: 2026-07-17.
> **Deploying on Debian (no root, conda)?** See [`DEPLOY_DEBIAN.md`](DEPLOY_DEBIAN.md) instead.

The app is **two processes** that must both be running:

| Process | Stack | Command run from | Listens on |
|---------|-------|------------------|------------|
| Backend | Python / FastAPI + LC0 | project root | `http://127.0.0.1:8000` |
| Frontend | Vite / React | `frontend/` | `http://localhost:5173` |

The React frontend calls the backend at a **hardcoded** `http://127.0.0.1:8000` (see `frontend/src/components/PgnViewer.tsx`). So the backend **must** be on port `8000` — do not change the uvicorn port.

---

## Prerequisites (already set up on this machine)

- **Conda env `cszero`** at `C:\Users\Admin\miniconda3\envs\cszero` (Python 3.11). This is the *only* interpreter that can run the backend — it has `torch`, `lczerolens`, `onnx2torch`, `fastapi`, `python-chess`. The system/Store Python on PATH **cannot** install torch; do not use it. (`backend/requirements.txt` lists the pinned dependencies for reference; they are installed in the conda env, not via pip into the system Python.)
- **Engine files in `engine/`** — `lc0.exe` plus two neural nets:
  - `791556.pb.gz` — fast SE-ResNet, powers the **policy arrows** (energy/initiative) via LC0's `VerboseMoveStats`.
  - `bt3.onnx` — BT3 transformer, powers the **attention saliency** heatmap (structure/vision) via `lczerolens`.
  - The backend auto-detects the first `*.pb.gz` in `engine/` for LC0 weights. Both nets are required for the full experience.
- **Node modules** in `frontend/node_modules` (run `npm install` once if missing).

---

## Step 1 — Start the Backend

Open a terminal in the **project root** (`C:\Users\Admin\Documents\chess_speak_out_loud`) and run the `cszero` interpreter directly (no `conda activate` needed):

```powershell
C:\Users\Admin\miniconda3\envs\cszero\python.exe -m uvicorn backend.app:app --reload
```

Leave this terminal open. A healthy start logs:

```
INFO ... Starting Chess Speak Out Loud backend v0.1.0
INFO ... LC0 engine is LIVE.
INFO ... NeuralVision loaded BT3 ONNX in attention mode.
```

## Step 2 — Start the Frontend

Open a **second** terminal in the `frontend/` folder:

```powershell
cd frontend
npm install    # first time only, or if node_modules is missing
npm run dev
```

Leave this terminal open too. Vite prints a `Local: http://localhost:5173/` line when ready.

## Step 3 — Open the App

Navigate to **http://localhost:5173** in your browser. (Not 8000 — that serves the legacy static prototype, not the current React UI.)

---

## Verify it's actually working (not degraded)

1. **Backend health** — in a browser or new terminal:
   ```powershell
   curl http://127.0.0.1:8000/api/health
   ```
   Expect `{"status":"ok","engine_mode":"live","version":"0.1.0"}`. `engine_mode: "mock"` means LC0 didn't start.

2. **Real neural attention** — trigger an analysis in the UI, then check the `/api/analyze` response (or backend logs). `saliency_source` must be `"attention"`. If it says `"policy_fallback"`, the BT3 transformer failed to load — see troubleshooting.

3. **Policy arrows** render on the board and the **evaluation is non-zero** on a non-equal position.

---

## Troubleshooting

- **Eval is 0.00 / no arrows / `engine_mode: mock`** — LC0 didn't start. Most likely the backend was started with the wrong Python (`ModuleNotFoundError`) — use the exact `cszero` command in Step 1, never a bare `uvicorn` or system `python`. Otherwise confirm `engine/lc0.exe` exists and runs. *(Note: a Windows-specific bug where `--reload` forced an asyncio SelectorEventLoop and silently killed the LC0 subprocess — logged as `Failed to start engine:` with an empty message — is fixed: `engine_manager.py` now runs all engine I/O on its own ProactorEventLoop thread.)*
- **Frontend loads but analysis fails / network error in browser console** — the backend isn't running, or isn't on port 8000. Confirm Step 1's terminal is alive and check `curl http://127.0.0.1:8000/api/health`.
- **`Port 8000 already in use`** — a stale backend is still running. Close other backend terminals (or `Get-Process python | Stop-Process`) and restart. Don't move the port; the frontend URL is hardcoded to 8000.
- **`ModuleNotFoundError: torch` (or lczerolens/onnx2torch)** — you're not in the `cszero` env. Use the full `...\cszero\python.exe` path from Step 1.
- **BT3 attention fails to load on startup** — confirm `engine/bt3.onnx` exists. The loader monkey-patches an onnx2torch Windows temp-file bug in `neural_vision.py`; if that regresses, saliency falls back to policy (still usable, just less accurate).

---

## Notes for AI agents working on this repo

- **Do not re-derive the run setup** — it's this file. Backend = `cszero` python + uvicorn on 8000; frontend = vite on 5173.
- The LLM path (`backend/llm_client.py`, Gemini) is **unreachable from any request path**, and that is now enforced by `backend/tests/test_llm_seam.py`, not by a flag. `LLM_ENABLED = False` in `backend/app.py` is a historical sign that nothing ever read — **it did not hold**: until 2026-08-30 two endpoints called `enrich_tree_explanations`, which reached the model with a FEN and an eval and served the result as coaching. The module stays in the tree as scaffolding for the eventual *translator* role — a model handed LC0's search tree, policy prior and relational facts. Anything less is a chess reasoner, and a bad coach does more harm than no coach.
- `.env` holds a `GEMINI_API_KEY` and is gitignored; nothing in the runtime reads it.
- See `ARCHITECTURE.md` for the data-flow / component boundaries.

---

## The Knowledge Trainer and its 24/7 timetable (separate from the chess app)

A second, independent app in `trainer/`: spaced-repetition interview cards **plus** the day
timetable that runs as an alarm clock. It does not touch the backend or the frontend.

```
launch_knowledge_trainer.bat   starts the timetable daemon AND the card server on port 8010
stop_knowledge_trainer.bat     stops both
launch_schedule.bat            the timetable daemon on its own
```

The day plan is **`trainer/content/timetable.json`** — edit it and the daemon reloads by itself.

**The reminder rule:** one reminder per block boundary, five minutes before it. It sounds an
alarm only when the block *starting* at that boundary is not rest or sleep — so a session
*ending* is announced silently (do not break concentration) and a break *ending* sounds
(get back to the desk). The 03:00 wake-up alarm fires at 03:00, not 02:55.

```powershell
python -m trainer.schedule_daemon --check        # the next 8 reminders, then exit
python -m trainer.schedule_daemon --test-alarm   # prove the sound works
python -m pytest trainer/tests -q                # 69 tests
```

For it to be running before 03:00, put a shortcut to `launch_schedule.bat` in `shell:startup`.

Full detail: **`trainer/README.md`**.
