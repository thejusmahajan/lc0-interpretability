"""
Critical Points — selector and lazy cached multipv verdict.

A "Critical Point" is a finding where the user gave up ≥2 pawns
(swing_cp >= 200 by default).  The training value is the missed
continuation, shown as the critical line + alternatives + the user's
own line, with evals.

The SET is free (just a filter on stored swing_cp).  The engine only
ever computes the LINES, lazily, cached by position (EPD).
"""

import datetime
from typing import Optional

import chess

from backend.training import store, metrics, relational_facts


# ------------------------------------------------------------------
# CP-1a — selector (pure, no engine)
# ------------------------------------------------------------------

def select_critical_points(
    profile: Optional[dict] = None,
    min_swing: int = 200,
) -> list[dict]:
    """Return findings where confirmation.swing_cp >= min_swing,
    sorted by swing_cp descending (stable).

    If *profile* is None the current profile is loaded from disk;
    missing/empty profiles return [].
    """
    if profile is None:
        profile = store.load_profile()
    if not profile:
        return []

    findings = profile.get("findings", [])
    if not findings:
        return []

    selected = []
    for f in findings:
        conf = f.get("confirmation") or {}
        swing = conf.get("swing_cp")
        if swing is not None and swing >= min_swing:
            selected.append(f)

    # Stable sort by swing_cp descending
    selected.sort(key=lambda f: f.get("confirmation", {}).get("swing_cp", 0),
                  reverse=True)
    return selected


# ------------------------------------------------------------------
# CP-1b — lazy + cached multipv verdict
# ------------------------------------------------------------------

def _mover_cp(white_eval, color: str) -> int:
    """Convert a white-POV engine eval to the mover's POV.

    *white_eval* may be an int, a mate string like "M5"/"M-3", or None.
    *color* is "white" or "black".
    """
    cp = metrics.eval_cp_number(white_eval) or 0
    return cp if color == "white" else -cp


async def critical_lines(
    fen_before: str,
    played_uci: str,
    user_color: str,
    lc0_engine,
    multipv: int = 4,
    nodes: int = 4000,
    force: bool = False,
) -> dict:
    """Compute (or return cached) the multipv verdict for one position.

    Returns a dict with keys: epd, computed_at, nodes, multipv, lines,
    played, diverge_ply.  On engine unavailability returns
    ``{"error": "engine_unavailable"}`` and does NOT cache.
    """
    epd = chess.Board(fen_before).epd()
    cache = store.EpdCache("critical_lines")

    # --- cache hit? ---------------------------------------------------
    if not force:
        hit = cache.get(epd)
        if hit is not None:
            return hit

    # --- engine call 1: multipv from the position ---------------------
    a = await lc0_engine.analyze(fen_before, multipv=multipv, nodes=nodes)

    best_moves = a.get("best_moves") or []
    if not best_moves:
        # Engine mock / unavailable — signal but do NOT cache
        return {"error": "engine_unavailable"}

    pv_lines = a.get("pv_lines") or []

    lines = []
    for i, bm in enumerate(best_moves):
        pv_san_str = pv_lines[i] if i < len(pv_lines) else ""
        lines.append({
            "rank": i,
            "first_uci": bm["move"],
            "first_san": bm["san"],
            "eval_cp": _mover_cp(bm["score"], user_color),
            "pv_san": pv_san_str.split() if pv_san_str else [],
        })

    # --- engine call 2: eval the user's played move -------------------
    b = chess.Board(fen_before)
    # Get SAN before pushing the move
    played_move = b.parse_uci(played_uci)
    played_san = b.san(played_move)
    b.push(played_move)
    fen_after = b.fen()

    pa = await lc0_engine.analyze(fen_after, multipv=1, nodes=nodes)

    # After the user's move, it's the OPPONENT to move.
    # pa["evaluation"] is white-POV.  We keep eval in the USER's POV
    # (same flip as lines) so it compares directly.
    played = {
        "uci": played_uci,
        "san": played_san,
        "eval_cp": _mover_cp(pa.get("evaluation", 0), user_color),
        "pv_san": (pa["pv_lines"][0].split()
                   if pa.get("pv_lines") and pa["pv_lines"]
                   else []),
    }

    # --- diverge ply --------------------------------------------------
    if played_uci != lines[0]["first_uci"]:
        # The fork IS the move itself
        diverge_ply = 0
    else:
        # Compare user PV vs engine top PV move-by-move
        diverge_ply = 0
        user_pv = played["pv_san"]
        engine_pv = lines[0]["pv_san"]
        min_len = min(len(user_pv), len(engine_pv))
        diverge_ply = min_len  # default: they agree on everything in range
        for idx in range(min_len):
            if user_pv[idx] != engine_pv[idx]:
                diverge_ply = idx
                break

    # --- build verdict and cache --------------------------------------
    verdict = {
        "epd": epd,
        "computed_at": datetime.datetime.utcnow().isoformat(),
        "nodes": nodes,
        "multipv": multipv,
        "lines": lines,
        "played": played,
        "diverge_ply": diverge_ply,
    }
    cache.put(epd, verdict)
    return verdict


async def position_plan_facts(fen: str, pov: chess.Color, lc0_engine,
                              nodes: int = 4000, multipv: int = 1) -> dict:
    """Run LC0 on `fen`, then extract relational facts along its chosen line.

    Returns the STATIC facts of the position PLUS the PLAN-level facts (what LC0's
    continuation creates/removes, move by move) — the north-star principle "LC0 chooses
    the line, the facts describe it", now covering plans as well as static positions.
    No salience filtering: every true fact is emitted; ranking is the learned layer's job.
    """
    a = await lc0_engine.analyze(fen, multipv=multipv, nodes=nodes)
    pv_san = (a.get("pv_lines") or [""])[0]
    board = chess.Board(fen)
    ucis = []
    for san in pv_san.split():
        try:
            m = board.parse_san(san)
            ucis.append(m.uci())
            board.push(m)
        except Exception:
            break
    if not ucis:
        return {"fen": fen, "line_san": "", "line_uci": [], "eval": a.get("evaluation"),
                "position_facts": [], "plan_facts": [], "note": "engine_unavailable"}
    facts = relational_facts.relational_facts(fen, ucis, pov)
    return {
        "fen": fen,
        "line_san": pv_san,
        "line_uci": ucis,
        "eval": a.get("evaluation"),
        "position_facts": facts.get("position_facts", []),
        "plan_facts": facts.get("per_move", []),
    }
