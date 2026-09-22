"""
Chess Speak Out Loud — FastAPI Application.

Serves the frontend static files and provides REST API endpoints for:
  - Position analysis (engine + heatmaps + concept mapping)
  - PGN analysis (per-move breakdown)
  - Health check
"""

import os
import asyncio
import dataclasses
import io
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import chess
import chess.pgn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotenv import load_dotenv
load_dotenv()

import chess
from backend.engine_manager import LC0Engine
from backend.neural_vision import NeuralVision
from backend.heatmap import generate_all_heatmaps
from backend.concept_mapper import analyze_position
from backend.mock_data import get_coach_summary

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

VERSION = "0.1.0"
LLM_ENABLED = False  # Historical flag. NOTHING READS IT and it never did -- see
# backend/tests/test_llm_seam.py, which is the actual interlock: no non-test module under
# backend/ may import llm_client, so no request path can reach a language model. The motto
# is that the LLM translates LC0's thinking and is never itself a chess reasoner.

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
ENGINE_DIR = PROJECT_DIR / "engine"


def _corpus_pgn() -> Path:
    """The user's games corpus: the NEWEST .pgn in games_of_derdiedasdie/
    (so replacing it with a bigger export just works — no hardcoded filename)."""
    d = PROJECT_DIR / "games_of_derdiedasdie"
    pgns = sorted(d.glob("*.pgn"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pgns[0] if pgns else d / "lichess_derdiedasdie.pgn"

logger = logging.getLogger("chess_speak_out_loud")
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------------
# Engine singleton
# ------------------------------------------------------------------

lc0_engine = LC0Engine(
    engine_path=str(ENGINE_DIR / "lc0.exe"),
)
neural_vision = NeuralVision(onnx_path=str(ENGINE_DIR / "bt3.onnx"))


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for the FastAPI app."""
    logger.info("Starting Chess Speak Out Loud backend v%s", VERSION)
    await lc0_engine.start()
    if lc0_engine.is_available():
        logger.info("LC0 engine is LIVE.")
    else:
        logger.info("LC0 engine not found — running in MOCK mode.")
    _sweep_orphaned_training_jobs()
    yield
    # Shutdown
    await lc0_engine.stop()
    logger.info("Backend shut down.")


# ------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------

app = FastAPI(
    title="Chess Speak Out Loud",
    version=VERSION,
    description="A chess training tool that teaches you to think out loud like a GM.",
    lifespan=lifespan,
)

# CORS — allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static directories
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    app.mount("/lib", StaticFiles(directory=str(FRONTEND_DIR / "lib")), name="lib")
else:
    logger.warning("Frontend directory not found at %s", FRONTEND_DIR)


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

from typing import Optional, List
class AnalyzeRequest(BaseModel):
    """Request body for single-position analysis."""
    fen: str
    depth: Optional[int] = Field(default=None, ge=1, le=100)
    multipv: int = Field(default=3, ge=1, le=10)
    time_limit: float = Field(default=2.0, ge=0.1, le=300.0)
    # llm_model: Optional[str] = "gemini-3.5-flash"  # Disabled


class PGNRequest(BaseModel):
    """Request body for PGN analysis."""
    pgn: str


class IntuitionSessionRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)


class IntuitionGuessRequest(BaseModel):
    epd: str
    uci: str


class SacSessionRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)
    eco: Optional[str] = None


class SacGuessRequest(BaseModel):
    finding_id: str
    uci: str


class SacPlayoutStartRequest(BaseModel):
    finding_id: str


class SacPlayoutMoveRequest(BaseModel):
    finding_id: str
    line: List[str]
    user_uci: str
    history: Optional[List[str]] = None


class CriticalPointsRequest(BaseModel):
    min_swing: int = Field(default=200, ge=0)


class CriticalLinesRequest(BaseModel):
    finding_id: str
    force: bool = False


class CreatePuzzleSetRequest(BaseModel):
    name: str
    min_rating: int = Field(default=1500, ge=0, le=4000)
    max_rating: int = Field(default=2000, ge=0, le=4000)
    themes: Optional[List[str]] = None
    size: int = Field(default=200, ge=1, le=10000)


class StartPuzzleSessionRequest(BaseModel):
    set_id: str
    seed: Optional[int] = None
    # Draw this many puzzles fresh from the pool for the session. Omit to use
    # the set's own stored puzzles.
    session_size: Optional[int] = None


class SubmitPuzzleMoveRequest(BaseModel):
    uci: str



# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def serve_index():
    """Serve the frontend index.html."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    raise HTTPException(
        status_code=404,
        detail="Frontend not found. Place index.html in the frontend/ directory.",
    )


@app.get("/api/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        status: "ok"
        engine_mode: "live" or "mock"
        version: application version string
    """
    return {
        "status": "ok",
        "engine_mode": "live" if lc0_engine.is_available() else "mock",
        "version": VERSION,
    }


def compute_steering_analysis(board: chess.Board, best_moves: list[dict], pv_lines: list[str]) -> dict:
    """Score candidate moves from the engine using PhiScorer to surface tactical steering lines."""
    try:
        from backend.training.config_steering.scorer import PhiScorer
        scorer = PhiScorer.get_instance()
    except Exception as exc:
        logger.warning("PhiScorer not available: %s", exc)
        return {}

    is_white = (board.turn == chess.WHITE)
    candidates = []
    for i, m in enumerate(best_moves):
        try:
            move_uci = m.get("move")
            if not move_uci:
                continue
            move_obj = chess.Move.from_uci(move_uci)
            if move_obj not in board.legal_moves:
                continue
            phi_raw, motifs = scorer.score_move(board, move_obj)
            phi_display = scorer.calibrate_phi(phi_raw)
            raw_score = m.get("score", 0)
            if isinstance(raw_score, int):
                eval_cp = raw_score
                eval_str = f"{eval_cp/100:+.2f}"
            elif isinstance(raw_score, str) and raw_score.startswith("M"):
                mate_val = int(raw_score[1:])
                eval_cp = 10000 if mate_val > 0 else -10000
                eval_str = raw_score
            else:
                eval_cp = 0
                eval_str = "0.00"

            pov_cp = eval_cp if is_white else -eval_cp
            pv_str = pv_lines[i] if i < len(pv_lines) else m.get("san", "")
            pv_list = pv_str.split() if pv_str else [m.get("san", "")]
            top_motifs = [k for k, v in sorted(motifs.items(), key=lambda x: x[1], reverse=True)[:3] if v > 0.15]

            candidates.append({
                "uci": move_uci,
                "san": m.get("san", ""),
                "eval_cp": eval_cp,
                "pov_cp": pov_cp,
                "eval": eval_str,
                "phi_raw": round(phi_raw, 4),
                "phi_display": round(phi_display, 4),
                "phi": round(phi_raw, 4),
                "motifs": top_motifs,
                "pv": pv_list,
                "pv_str": pv_str,
            })
        except Exception:
            continue

    if not candidates:
        return {}

    # Objective best for side to move
    objective = max(candidates, key=lambda c: c["pov_cp"])
    best_pov = objective["pov_cp"]

    # Other candidates
    others = [c for c in candidates if c["uci"] != objective["uci"]]

    # Tier 1: Sound alternatives within 80 cp of best (rank by phi_raw, NEVER calibrated)
    tier1 = [c for c in others if best_pov - c["pov_cp"] <= 80]
    tier1.sort(key=lambda c: c["phi_raw"], reverse=True)

    if len(tier1) >= 2:
        tactical = tier1[:3]
    else:
        # Tier 2: Dynamic alternatives within 150 cp of best (rank by phi_raw)
        tier2 = [c for c in others if best_pov - c["pov_cp"] <= 150]
        tier2.sort(key=lambda c: c["phi_raw"], reverse=True)
        if len(tier2) >= 2:
            tactical = tier2[:3]
        else:
            # Fallback: Top alternatives sorted by phi_raw
            others.sort(key=lambda c: c["phi_raw"], reverse=True)
            tactical = others[:3] if others else [objective]

    curr_phi_raw, _ = scorer.score_board(board)
    curr_phi_display = scorer.calibrate_phi(curr_phi_raw)
    return {
        "current_phi": round(curr_phi_raw, 4),
        "current_phi_raw": round(curr_phi_raw, 4),
        "current_phi_display": round(curr_phi_display, 4),
        "objective_line": objective,
        "tactical_lines": tactical,
    }


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    """
    Analyse a single chess position.

    Combines engine analysis, heatmap generation, and concept mapping
    into a single comprehensive response.

    Args:
        request: JSON body with ``fen``, ``depth``, ``multipv``.

    Returns:
        JSON with keys: fen, engine, heatmaps, concepts, coach_summary.
    """
    fen = request.fen.strip()

    # Validate FEN
    try:
        chess.Board(fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}")

    # Run engine analysis
    engine_result = await lc0_engine.analyze(
        fen=fen,
        depth=request.depth,
        multipv=request.multipv,
        time_limit=request.time_limit,
    )

    # Generate heatmaps
    # Generate heatmaps (fast single board)
    heatmaps = generate_all_heatmaps(fen)
    projected_heatmaps = []
    concepts = {}

    # LLM text-generation bypassed (Phase 0)
    # coach_summary = get_coach_summary(fen)
    # if coach_summary is None:
    #     coach_summary = await generate_conversation(...)

    # Format evaluation for frontend
    raw_eval = engine_result.get("evaluation", 0)
    if isinstance(raw_eval, str) and raw_eval.startswith("M"):
        eval_obj = {"type": "mate", "value": int(raw_eval[1:])}
    else:
        eval_obj = {"type": "cp", "value": int(raw_eval)}

    # Format best_moves for frontend
    frontend_moves = []
    for m in engine_result.get("best_moves", []):
        score = m.get("score", 0)
        if isinstance(score, str) and score.startswith("M"):
            eval_str = f"M{score[1:]}"
        else:
            eval_str = str(score)
        frontend_moves.append({
            "san": m.get("san"),
            "eval": eval_str,
            "score": score,
            "nodes": m.get("nodes"),
            "wdl": m.get("wdl")
        })

    # Get Policy Priors (Phase 1)
    policy_dist = await lc0_engine.get_policy_distribution(fen, nodes=1)

    # Get Neural Vision / Saliency (Phase 2)
    saliency = neural_vision.saliency(fen, policy_dist=policy_dist)

    # Compute configuration steering lines (Objective vs Tal lines)
    steering = compute_steering_analysis(
        board=chess.Board(fen),
        best_moves=engine_result.get("best_moves", []),
        pv_lines=engine_result.get("pv_lines", []),
    )

    return {
        "fen": fen,
        "evaluation": eval_obj,
        "best_moves": frontend_moves,
        "nodes": engine_result.get("nodes"),
        "wdl": engine_result.get("wdl"),
        "interpretation": {
            "observations": concepts.get("observations", [])
        },
        "heatmaps": heatmaps,
        "projected_heatmaps": projected_heatmaps,
        "policy": policy_dist[:20],
        "saliency": saliency,
        "saliency_source": neural_vision.mode,
        "steering": steering,
    }


@app.post("/api/calculation-glow")
async def calculation_glow(request: AnalyzeRequest):
    """
    Compute the aggregated 'Calculation Glow' for a position: BT3 attention
    averaged over the engine's top PV lines, weighted by line strength and depth.
    Expensive (~10-15s). Falls back to the single-position saliency if the engine
    is in mock mode or produced no lines.
    """
    fen = request.fen.strip()
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}")

    lines = await lc0_engine.search_lines(
        fen, time_limit=request.time_limit, multipv=request.multipv
    )
    if not lines:
        # mock mode or no search result -> just return the intuition map
        policy_dist = await lc0_engine.get_policy_distribution(fen, nodes=1)
        return {
            "fen": fen,
            "calculation_saliency": neural_vision.saliency(fen, policy_dist=policy_dist),
            "positions_used": 0,
            "saliency_source": neural_vision.mode,
        }

    calc = await asyncio.to_thread(
        neural_vision.calculation_saliency, board, lines
    )
    return {
        "fen": fen,
        "calculation_saliency": calc,
        "positions_used": min(8, sum(len(l["moves"]) for l in lines)),
        "saliency_source": neural_vision.mode,
    }


@app.post("/api/play-move")
async def play_move(request: AnalyzeRequest):
    """
    Lightweight endpoint to simply get the engine's best move.
    Skips heatmap and concept generation for speed.
    """
    fen = request.fen.strip()

    try:
        chess.Board(fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}")

    # Run engine analysis quickly — non-blocking if engine is busy
    engine_result = await lc0_engine.fast_analyze(
        fen=fen,
        depth=None,
        multipv=1,
        time_limit=request.time_limit or 1.0,
    )

    best_moves = engine_result.get("best_moves", [])
    best_move = best_moves[0] if best_moves else None

    return {
        "fen": fen,
        "best_move": best_move
    }


@app.get("/api/live-game")
async def live_game():
    """
    Returns the FEN of the ongoing self-play match.
    Reads from scratch/live_game_fen.txt
    """
    fen_file = PROJECT_DIR / "scratch" / "live_game_fen.txt"
    if fen_file.exists():
        return {"fen": fen_file.read_text().strip()}
    return {"fen": None}


@app.post("/api/analyze-pgn")
async def analyze_pgn(request: PGNRequest):
    """
    Analyse an entire PGN game move-by-move.

    Parses the PGN, iterates through every position, and returns a
    list of per-position analyses.

    Args:
        request: JSON body with ``pgn`` string.

    Returns:
        JSON with keys: headers (PGN metadata), moves (list of
        per-move analysis dicts).
    """
    pgn_text = request.pgn.strip()
    if not pgn_text:
        raise HTTPException(status_code=400, detail="PGN string is empty.")

    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse PGN: {exc}")

    if game is None:
        raise HTTPException(status_code=400, detail="No game found in PGN.")

    # Extract headers
    headers = dict(game.headers)

    # Walk through the game
    board = game.board()
    moves_analysis = []

    for move_number, node in enumerate(game.mainline(), start=1):
        move = node.move
        san = board.san(move)

        # Analyse BEFORE the move is played
        fen_before = board.fen()

        setup_uci = None
        pre_fen = None
        if board.move_stack:
            setup_uci = board.peek().uci()
            tmp = board.copy()
            tmp.pop()
            pre_fen = tmp.fen()

        engine_result = await lc0_engine.analyze(fen=fen_before, depth=15, multipv=1)
        heatmaps = generate_all_heatmaps(fen_before)
        concepts = analyze_position(
            fen_before,
            engine_analysis=engine_result,
            pre_fen=pre_fen,
            setup_uci=setup_uci,
        )

        board.push(move)

        moves_analysis.append({
            "move_number": move_number,
            "san": san,
            "uci": move.uci(),
            "fen_before": fen_before,
            "fen_after": board.fen(),
            "engine": engine_result,
            "heatmaps": heatmaps,
            "concepts": concepts,
        })

    return {
        "headers": headers,
        "moves": moves_analysis,
    }


# ------------------------------------------------------------------
# Elite Training System endpoints (Gemini-owned)
# ------------------------------------------------------------------

from backend.training.pipeline import run_diagnosis
from backend.training import store, drills, attempts, trends, usual_suspects

@app.get("/api/training/usual-suspects")
async def get_usual_suspects():
    profile = store.load_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    suspects = usual_suspects.usual_suspects(profile)
    by_phase, by_concept = usual_suspects.get_broad_aggregates(profile)
    return {"suspects": suspects, "by_phase": by_phase, "by_concept": by_concept}

class ApproveSuspectsRequest(BaseModel):
    themes: List[str]

class SuspectsDeckRequest(BaseModel):
    count: int = 20

@app.post("/api/training/usual-suspects/approve")
async def approve_usual_suspects(req: ApproveSuspectsRequest):
    profile = store.load_profile()
    suspects = usual_suspects.usual_suspects(profile) if profile else []
    valid_themes = {s["theme"] for s in suspects}
    for t in req.themes:
        if t not in valid_themes:
            raise HTTPException(status_code=400, detail=f"Unknown theme: {t}")
    return store.save_approved_suspects(req.themes)

@app.get("/api/training/usual-suspects/approved")
async def get_approved_usual_suspects():
    return store.load_approved_suspects()

@app.post("/api/training/usual-suspects/deck")
async def build_suspects_deck_endpoint(req: SuspectsDeckRequest):
    profile = store.load_profile()
    approved = store.load_approved_suspects().get("themes", [])
    deck = usual_suspects.build_suspects_deck(profile, approved, count=req.count)
    store.save_drill_set(deck)
    return deck
import asyncio
import json

class DiagnoseRequest(BaseModel):
    pgn: str
    player_name: str

class RepertoireRequest(BaseModel):
    color: str
    build: bool = False
    style: str = "weakness"

class RepertoireTreeRequest(BaseModel):
    eco: str
    color: str

class GenerateDrillsRequest(BaseModel):
    count: int = 20
    steer_weight: float = 0.0

class AttemptDrillRequest(BaseModel):
    set_id: str
    drill_id: str
    move_uci: str
    ply: int = 0  # index of the user's move within the drill's solution line

_training_tasks: set = set()

def _sweep_orphaned_training_jobs():
    """A server restart mid-diagnosis leaves a job 'running' forever, which
    would 409-block every future diagnosis (C3 finding M5)."""
    jobs_dir = Path(store.TRAINING_DIR) / "jobs"
    if not jobs_dir.exists():
        return
    for job_file in jobs_dir.glob("*.json"):
        try:
            with open(job_file, "r") as f:
                j = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if j.get("status") in ("running", "queued"):
            store.update_job(j["id"], status="error",
                             error="Orphaned by server restart")
            logger.info("Marked orphaned training job %s as error", j["id"])

@app.post("/api/training/diagnose")
async def start_diagnose(req: DiagnoseRequest):
    jobs_dir = Path(store.TRAINING_DIR) / "jobs"
    if jobs_dir.exists():
        for job_file in jobs_dir.glob("*.json"):
            # A corrupt/locked job file must not 500 a new diagnosis (audit F3;
            # matches _sweep_orphaned_training_jobs' guarding).
            try:
                with open(job_file, "r") as f:
                    j = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            if j.get("status") == "running":
                raise HTTPException(status_code=409, detail="A diagnosis job is already running")
                    
    job_id = store.create_job()
    task = asyncio.create_task(
        run_diagnosis(job_id, req.pgn, req.player_name, lc0_engine, neural_vision))
    # keep a strong reference — bare create_task results can be GC'd mid-run
    _training_tasks.add(task)
    task.add_done_callback(_training_tasks.discard)
    return {"job_id": job_id}

@app.get("/api/training/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/training/profile")
async def get_profile():
    profile = store.load_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile

@app.post("/api/training/repertoire")
async def get_repertoire(req: RepertoireRequest):
    if req.build:
        from backend.training.select_repertoire import build_repertoire
        profile = store.load_profile()
        if not profile:
            raise HTTPException(status_code=404,
                                detail="No profile — run a diagnosis first")
        rep = await build_repertoire(profile, req.color, lc0_engine,
                                     style=req.style)
        store.save_repertoire(rep)
        return rep
    rep = store.load_repertoire(req.style, req.color)
    if not rep:
        return {}
    return rep

@app.get("/api/training/repertoires")
async def list_repertoires():
    """All built repertoire variants (weakness/sacrificial x white/black)."""
    return store.list_repertoires()

@app.post("/api/training/repertoire/tree")
async def get_repertoire_tree(req: RepertoireTreeRequest):
    import os
    filepath = os.path.join(store.TRAINING_DIR, f"repertoire_tree_{req.eco}_{req.color}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            tree = json.load(f)
    else:
        from backend.training.select_repertoire import build_repertoire_tree
        profile = store.load_profile()
        pgn_path = _corpus_pgn()
        player_name = "derdiedasdie"
        if not pgn_path.exists():
            raise HTTPException(status_code=404, detail="Repertoire tree PGN file not found")
        tree = await build_repertoire_tree(
            req.eco, req.color, str(pgn_path), player_name, lc0_engine, profile=profile
        )

    return tree


@app.get("/api/training/repertoire/top-openings")
async def repertoire_top_openings(limit: int = 12):
    """The user's most-played openings per color, by ECO classification of the
    corpus. Seeds the Train-mode opening selector so trees are built for
    high-volume lines (A40/A46/D02...) instead of only the low-volume weakness
    recommendations (which build empty trees). Cached to disk after first pass."""
    import os
    import chess.pgn
    from collections import Counter
    from backend.training import openings as _openings

    cache_path = os.path.join(store.TRAINING_DIR, "top_openings.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"white": data.get("white", [])[:limit],
                "black": data.get("black", [])[:limit]}

    pgn_path = _corpus_pgn()
    player_name = "derdiedasdie"
    if not pgn_path.exists():
        raise HTTPException(status_code=404, detail="Corpus PGN not found")

    counts = {"white": Counter(), "black": Counter()}
    names: dict[str, str] = {}
    with open(pgn_path, "r", encoding="utf-8") as fh:
        while True:
            game = chess.pgn.read_game(fh)
            if game is None:
                break
            w = game.headers.get("White", "")
            b = game.headers.get("Black", "")
            if player_name.lower() in w.lower():
                col = "white"
            elif player_name.lower() in b.lower():
                col = "black"
            else:
                continue
            ucis = [n.move.uci() for n in game.mainline()]
            if not ucis:
                continue
            m = _openings.classify(ucis)
            if m:
                counts[col][m["eco"]] += 1
                names[m["eco"]] = m.get("name", m["eco"])

    def top(col):
        return [{"eco": eco, "name": names.get(eco, eco), "count": n}
                for eco, n in counts[col].most_common()]

    result = {"white": top("white"), "black": top("black")}
    store._write_json_atomic(cache_path, result)
    return {"white": result["white"][:limit], "black": result["black"][:limit]}

@app.post("/api/training/drills/generate")
async def generate_drills_ep(req: GenerateDrillsRequest):
    profile = store.load_profile()
    repertoire = store.load_repertoire()
    drill_set = await drills.generate_drill_set(req.count, profile, repertoire, lc0_engine, neural_vision, req.steer_weight)
    return drill_set

@app.post("/api/training/repertoire/drills")
async def generate_repertoire_drills(req: RepertoireTreeRequest):
    """Turn an opening's variation tree into an SRS-tracked drill set: one drill
    per CRITICAL node (stable EPD-derived ids, coach explanation in the reveal).
    Saved so it flows through the existing DrillMode + Review/SRS queues."""
    import os
    filepath = os.path.join(store.TRAINING_DIR, f"repertoire_tree_{req.eco}_{req.color}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            tree = json.load(f)
    else:
        from backend.training.select_repertoire import build_repertoire_tree
        profile = store.load_profile()
        pgn_path = _corpus_pgn()
        if not pgn_path.exists():
            raise HTTPException(status_code=404, detail="Repertoire tree PGN file not found")
        tree = await build_repertoire_tree(
            req.eco, req.color, str(pgn_path), "derdiedasdie", lc0_engine, profile=profile
        )

    drill_set = drills.build_repertoire_drill_set(tree)
    if not drill_set["drills"]:
        raise HTTPException(
            status_code=404,
            detail=f"No critical nodes to drill for {req.eco} {req.color} (tree too thin).")
    store.save_drill_set(drill_set)
    return drill_set

@app.get("/api/training/drills")
async def list_drills():
    return store.list_drill_sets()

@app.get("/api/training/drills/{set_id}")
async def get_drill_set(set_id: str):
    ds = store.load_drill_set(set_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Drill set not found")
    
    import copy
    cloned = copy.deepcopy(ds)
    for d in cloned.get("drills", []):
        if "reveal" in d:
            del d["reveal"]
    return cloned

@app.post("/api/training/drills/attempt")
async def attempt_drill(req: AttemptDrillRequest):
    ds = store.load_drill_set(req.set_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Drill set not found")

    for d in ds.get("drills", []):
        if d["id"] == req.drill_id:
            try:
                verdict = drills.check_attempt(d, req.ply, req.move_uci)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            # The drill is scored once: on the first wrong move, or on
            # reaching the end of the line. Mid-line success is unscored.
            if verdict["correct"] and not verdict["complete"]:
                return dict(verdict, reveal=None, next_due=None, lapses=0)

            srs_entry = attempts.record_attempt(
                req.set_id, d, verdict["correct"])
            return dict(verdict, reveal=d.get("reveal"),
                        next_due=srs_entry.get("due"),
                        lapses=srs_entry.get("lapses", 0))

    raise HTTPException(status_code=404, detail="Drill not found")

@app.get("/api/training/srs/due")
async def srs_due():
    """Review queue: due drills (most critical first), reveals stripped."""
    due = attempts.due_drills()
    out = []
    sets_cache = {}
    for entry in due:
        set_id = entry.get("set_id")
        if set_id not in sets_cache:
            sets_cache[set_id] = store.load_drill_set(set_id) or {}
        drill = next((d for d in sets_cache[set_id].get("drills", [])
                      if d["id"] == entry["drill_id"]), None)
        if not drill:
            continue
        drill = {k: v for k, v in drill.items() if k != "reveal"}
        out.append({"set_id": set_id, "due": entry["due"],
                    "lapses": entry.get("lapses", 0), "drill": drill})
    return {"count": len(out), "due": out}

@app.get("/api/training/trends")
async def training_trends():
    return trends.trend_report()

def _ser(items):
    return [{**dataclasses.asdict(c), "kind": "weakness" if c.grade < 0 else "strength"} for c in items]


@app.get("/api/training/weakness-ranking")
async def weakness_ranking_ep(n: int = 6):
    from backend.training import metrics
    profile = store.load_profile()
    if not profile:
        return {"ranking": [], "phase": [], "clock": []}
    allr = metrics.weakness_ranking_all(profile, n)
    return {"ranking": _ser(allr["openings"]), "phase": _ser(allr["phase"]), "clock": _ser(allr["clock"])}


# ------------------------------------------------------------------
# Intuition Speed-Drill Endpoints
# ------------------------------------------------------------------

from backend.training import intuition

@app.post("/api/training/intuition/session")
async def intuition_session(req: IntuitionSessionRequest):
    return intuition.build_session(req.count)


@app.post("/api/training/intuition/guess")
async def intuition_guess(req: IntuitionGuessRequest):
    res = intuition.score_guess(req.epd, req.uci)
    if not res:
        raise HTTPException(status_code=404, detail="Position or policy not found in cache")
    return res


@app.get("/api/training/intuition/stats")
async def intuition_stats():
    return intuition.get_stats()


# ------------------------------------------------------------------
# Sacrifice / Tactical-Landmine Drill Endpoints
# ------------------------------------------------------------------

from backend.training import sac_drill

@app.post("/api/training/sac/session")
async def sac_session(req: SacSessionRequest):
    return sac_drill.build_sac_session(req.count, eco=req.eco)


@app.post("/api/training/sac/guess")
async def sac_guess(req: SacGuessRequest):
    res = sac_drill.score_sac_guess(req.finding_id, req.uci)
    if not res:
        raise HTTPException(status_code=404, detail="Finding not found")
    return res


@app.get("/api/training/sac/stats")
async def sac_stats():
    return sac_drill.get_stats()


@app.post("/api/training/sac/playout/start")
async def sac_playout_start(req: SacPlayoutStartRequest):
    res = await sac_drill.start_sac_playout(req.finding_id, lc0_engine)
    if isinstance(res, dict) and res.get("error"):
        return res
    if not res:
        raise HTTPException(status_code=404, detail="Finding not found")
    return res


@app.post("/api/training/sac/playout/move")
async def sac_playout_move(req: SacPlayoutMoveRequest):
    try:
        res = await sac_drill.play_sac_move(
            req.finding_id, req.line, req.user_uci, lc0_engine, req.history
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if isinstance(res, dict) and res.get("error"):
        return res
    if not res:
        raise HTTPException(status_code=404, detail="Finding not found")
    return res


from backend.training import eco_backfill, openings_sharpness

@app.post("/api/training/openings/backfill-ecos")
async def backfill_ecos_route():
    profile = store.load_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile found")

    pgn_path = str(_corpus_pgn())
    if not os.path.exists(pgn_path):
        raise HTTPException(status_code=404, detail=f"Corpus PGN not found at {pgn_path}")

    enriched, summary = eco_backfill.backfill_ecos(profile, pgn_path)
    store.save_profile(enriched)
    return summary


@app.get("/api/training/openings/sharpness")
async def openings_sharpness_route():
    profile = store.load_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile found")
    return {"openings": openings_sharpness.sharpness_by_opening(profile)}


@app.get("/api/training/openings/recommendations")
async def openings_recommendations_route(color: Optional[str] = None):
    recs = openings_sharpness.load_recommendations(color)
    return {"recommendations": recs}


# ------------------------------------------------------------------
# Critical Points Endpoints
# ------------------------------------------------------------------

from backend.training import critical_points

@app.post("/api/training/critical/points")
async def critical_points_list(req: CriticalPointsRequest):
    cps = critical_points.select_critical_points(
        store.load_profile(), req.min_swing
    )
    return [
        {
            "id": f.get("id"),
            "fen_before": f.get("fen_before"),
            "swing_cp": f.get("confirmation", {}).get("swing_cp"),
            "played": f.get("played"),
            "best": f.get("best"),
            "move_number": f.get("move_number"),
            "user_color": f.get("user_color"),
            "opening": f.get("opening"),
        }
        for f in cps
    ]


@app.post("/api/training/critical/lines")
async def critical_lines_route(req: CriticalLinesRequest):
    profile = store.load_profile()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile found")

    findings = profile.get("findings", [])
    finding = None
    for f in findings:
        if f.get("id") == req.finding_id:
            finding = f
            break
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    result = await critical_points.critical_lines(
        finding["fen_before"],
        finding["played"]["uci"],
        finding["user_color"],
        lc0_engine,
        force=req.force,
    )
    # If result has error, return it (200 with error field, like sac endpoints)
    return result


# ------------------------------------------------------------------
# Puzzle Streak Endpoints
# ------------------------------------------------------------------

from backend.training import puzzle_sets


@app.post("/api/training/puzzles/sets")
async def create_puzzle_set_endpoint(req: CreatePuzzleSetRequest):
    try:
        return puzzle_sets.create_set(
            name=req.name,
            min_rating=req.min_rating,
            max_rating=req.max_rating,
            themes=req.themes,
            size=req.size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/training/puzzles/sets")
async def list_puzzle_sets_endpoint():
    return puzzle_sets.list_sets()


@app.delete("/api/training/puzzles/sets/{set_id}")
async def delete_puzzle_set_endpoint(set_id: str):
    try:
        puzzle_sets.get_set(set_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Set {set_id!r} not found")
    deleted = puzzle_sets.delete_set(set_id)
    return {"deleted": deleted}


@app.post("/api/training/puzzles/session")
async def start_puzzle_session_endpoint(req: StartPuzzleSessionRequest):
    try:
        return puzzle_sets.start_session(req.set_id, seed=req.seed,
                                         session_size=req.session_size)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Set {req.set_id!r} not found")


@app.get("/api/training/puzzles/session/{session_id}")
async def get_puzzle_session_endpoint(session_id: str):
    try:
        return puzzle_sets.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")


@app.post("/api/training/puzzles/session/{session_id}/move")
async def submit_puzzle_move_endpoint(session_id: str, req: SubmitPuzzleMoveRequest):
    try:
        return puzzle_sets.submit_move(session_id, req.uci)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")


@app.post("/api/training/puzzles/session/{session_id}/next")
async def next_puzzle_endpoint(session_id: str):
    try:
        return puzzle_sets.next_puzzle(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")




# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
