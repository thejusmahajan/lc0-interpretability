# REST API Contract

This document acts as the strict contract between the React Frontend and the FastAPI Backend.

## Endpoints

### 1. `GET /api/health`
Health check to ensure the API and LC0 engine are running.
**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### 2. `POST /api/analyze`
Analyzes a specific FEN position using LC0. Generates heatmaps and concept mappings.
**Request Body:**
```json
{
  "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
  "nodes": 5000
}
```
**Response:**
```json
{
  "fen": "...",
  "best_move": "d2d4",
  "score": 1.5,
  "concept_maps": {
    "king_safety": { ... },
    "space": { ... }
  },
  "heatmaps": {
    "activity": "base64_encoded_image..."
  }
}
```

### 3. `POST /api/play-move`
Simulates playing a move from a position and retrieves LC0's PV response.
**Request Body:**
```json
{
  "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
  "move": "e4e5"
}
```

### 4. `POST /api/analyze-pgn`
Performs a deep tactical analysis of a PGN sequence using Lichess Tagger and Gemini.
**Request Body:**
```json
{
  "pgn": "[Event \"Casual Game\"]\n\n1. e4 e5 2. Nf3 Nc6..."
}
```
**Response:**
```json
{
  "tactics_found": ["fork", "pin"],
  "commentary": "Magnus: The tension here on the light squares..."
}
```

### 5. `POST /api/training/diagnose`
Starts a background diagnosis job on a given PGN. One job at a time — returns
409 while a job is running. Errors (e.g. no games matching `player_name`) are
reported on the job object, not here.
**Request Body:** `{"pgn": "...", "player_name": "MyLichessName"}`
**Response:** `{"job_id": "..."}`

### 6. `GET /api/training/jobs/{job_id}`
**Response:** `{"id": "...", "status": "done", "progress": {...}, "error": null}`

### 7. `GET /api/training/profile`
**Response:** `{"games_analyzed": 25, "findings": [...], "aggregates": {...}}`

### 8. `POST /api/training/drills/generate`
**Response:** `{"id": "set-123", "drills": [{..., "reveal": {"swing_cp": 50, "pv_san": ["e4", "e5"], ...}}]}`

### 9. `POST /api/training/drills/attempt`
**Request Body:** `{"set_id": "set-123", "drill_id": "d-abc", "move_uci": "e2e4"}`
**Response:** `{"correct": true, "reveal": {"swing_cp": 50, ...}}`

### 10. `GET /api/training/srs/due`
Spaced-repetition review queue, most critical first (lapses, then overdue).
**Response:** `{"count": 2, "due": [{"set_id", "due", "lapses", "drill": {…no reveal}}]}`

### 11. `GET /api/training/trends`
Longitudinal report: profile history series, per-motif blind trajectories,
training accuracy by motif/source, due/lapse counts, latest regressions.
**Response:** `{"profiles": [...], "motif_blind_series": {...}, "training": {...}, "latest_regressions": [...]}`

Note: `POST /drills/attempt` now records every attempt (timestamped) and
returns `next_due` + `lapses` alongside `correct`/`reveal`.

### 12. `POST /api/training/repertoire`
Returns the stored repertoire (`{}` if none). With `"build": true`, builds and
stores a fresh one from the current profile (404 when no profile exists).
**Request Body:** `{"color": "white" | "black", "build": false}`
**Response:** `{"color": "...", "targets": [...], "recommendations": [{"eco",
"name", "line_pgn", "score", "eval_cp", "draw_pct", "rationale", ...}]}`
