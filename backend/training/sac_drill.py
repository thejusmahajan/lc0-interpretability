import os
import json
import time
import random
import chess
from typing import List, Dict, Any, Optional
from backend.training import store, metrics


def _get_sharp_findings(eco: Optional[str] = None) -> List[Dict[str, Any]]:
    """Select steer_findings where had_sharp_move is True."""
    profile = store.load_profile()
    if not profile or "steer_findings" not in profile:
        return []

    steer_findings = profile["steer_findings"]
    sharp_findings = [sf for sf in steer_findings if sf.get("had_sharp_move") is True]

    if eco:
        eco_clean = eco.strip()
        sharp_findings = [sf for sf in sharp_findings if sf.get("opening", {}).get("eco") == eco_clean]

    # Rank by steer.complexity DESC
    sharp_findings.sort(
        key=lambda sf: sf.get("steer", {}).get("complexity", 0.0),
        reverse=True
    )

    # Deduplicate by board EPD
    seen_epds = set()
    deduped = []
    for sf in sharp_findings:
        fen = sf.get("fen_before")
        if not fen:
            continue
        try:
            epd = chess.Board(fen).epd()
        except Exception:
            epd = fen.split(" ")[0]

        if epd not in seen_epds:
            seen_epds.add(epd)
            deduped.append(sf)

    return deduped


_get_tal_findings = _get_sharp_findings


def select_missed_sacrifices(profile: Optional[Dict[str, Any]] = None, eco: Optional[str] = None) -> List[Dict[str, Any]]:
    """Select findings where 'sacrifice' is in motifs (sound material sacrifices missed by user).

    Source of truth: Phase A Lichess cook() motifs on profile['findings'].
    NEVER falls back to had_sharp_move / steer_findings.
    """
    if profile is None:
        profile = store.load_profile()
    if not profile or "findings" not in profile:
        return []

    findings = profile["findings"]
    sac_findings = [f for f in findings if "sacrifice" in (f.get("motifs") or [])]

    if eco:
        eco_clean = eco.strip()
        sac_findings = [f for f in sac_findings if f.get("opening", {}).get("eco") == eco_clean]

    return sac_findings


def build_sac_session(count: int = 10, eco: Optional[str] = None) -> List[Dict[str, str]]:
    """Select eligible sharp candidate positions from profile steer_findings.
    
    Filters had_sharp_move=True, optional eco filter, ranks by complexity DESC,
    dedupes by board EPD, and returns [{"id": finding_id, "fen": fen_before}] ONLY.
    Answers and evaluations stay server-side.
    """
    eligible = _get_sharp_findings(eco=eco)
    if not eligible:
        return []

    if len(eligible) <= count:
        sampled = eligible
    else:
        sampled = random.sample(eligible, count)

    session = []
    for sf in sampled:
        session.append({
            "id": sf["id"],
            "fen": sf["fen_before"],
        })

    return session


def _record_attempt(finding_id: str, uci: str, correct: bool, acceptable: bool):
    store._ensure_dirs()
    attempts_path = os.path.join(store.TRAINING_DIR, "sac_attempts.jsonl")
    record = {
        "finding_id": finding_id,
        "uci": uci,
        "correct": correct,
        "acceptable": acceptable,
        "ts": time.time(),
    }
    with open(attempts_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def score_sac_guess(finding_id: str, uci: str) -> Dict[str, Any]:
    """Score guess against a sacrifice steer_finding by id.
    
    Computes correct (found sac_uci), acceptable (in playable_candidates and not sac),
    soundness comparison (sac vs safe move evals & complexity), and playable candidates.
    Logs attempt to sac_attempts.jsonl.
    """
    profile = store.load_profile()
    if not profile or "steer_findings" not in profile:
        return {}

    sf = next((f for f in profile["steer_findings"] if f.get("id") == finding_id), None)
    if not sf or "steer" not in sf or "best" not in sf:
        return {}

    sac_move = sf["steer"]
    safe_move = sf["best"]
    sac_uci = sac_move.get("uci")

    playable = sf.get("playable_candidates", [])
    alt_ucis = {c["uci"] for c in playable if c.get("uci")}

    correct = (uci == sac_uci)
    acceptable = (uci in alt_ucis and not correct)

    eval_loss_cp = sf.get("eval_loss_cp", 0)

    res = {
        "correct": correct,
        "acceptable": acceptable,
        "sac_move": {
            "uci": sac_move.get("uci", ""),
            "san": sac_move.get("san", ""),
            "eval_cp": sac_move.get("eval_cp", 0),
            "complexity": sac_move.get("complexity", 0.0),
        },
        "safe_move": {
            "san": safe_move.get("san", ""),
            "eval_cp": safe_move.get("eval_cp", 0),
        },
        "eval_loss_cp": eval_loss_cp,
        "playable_candidates": playable,
    }

    _record_attempt(finding_id, uci, correct, acceptable)

    return res


def get_stats() -> Dict[str, Any]:
    """Calculate overall and recent (last 50) sacrifice drill stats."""
    store._ensure_dirs()
    attempts_path = os.path.join(store.TRAINING_DIR, "sac_attempts.jsonl")
    attempts = []
    if os.path.exists(attempts_path):
        with open(attempts_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    attempts.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    total = len(attempts)
    correct_count = sum(1 for a in attempts if a.get("correct"))
    acceptable_count = sum(1 for a in attempts if a.get("acceptable"))
    accuracy = round(correct_count / total, 4) if total > 0 else 0.0

    recent = attempts[-50:]
    recent_correct = sum(1 for a in recent if a.get("correct"))
    recent_accuracy = round(recent_correct / len(recent), 4) if len(recent) > 0 else 0.0

    return {
        "total": total,
        "correct": correct_count,
        "acceptable": acceptable_count,
        "accuracy": accuracy,
        "recent_accuracy": recent_accuracy,
    }


# ------------------------------------------------------------------
# Phase C1 — Sacrifice Playout vs LC0
# ------------------------------------------------------------------

PLAYOUT_NODES = 4000
PLAYOUT_PLIES = 8


async def start_sac_playout(finding_id: str, lc0_engine) -> Dict[str, Any]:
    """Start engine playout session for a sacrifice finding.
    
    Plays sac_uci, gets LC0's best defense, and returns state ready for user attack.
    Does NOT leak LC0's preferred attack move.
    """
    if not lc0_engine or not lc0_engine.is_available():
        return {"error": "engine_unavailable"}

    profile = store.load_profile()
    if not profile or "steer_findings" not in profile:
        return {}

    sf = next((f for f in profile["steer_findings"] if f.get("id") == finding_id), None)
    if not sf or "fen_before" not in sf or "steer" not in sf:
        return {}

    fen_before = sf["fen_before"]
    board = chess.Board(fen_before)
    attacker_is_white = (board.turn == chess.WHITE)

    sac_uci = sf["steer"].get("uci")
    if not sac_uci:
        return {}

    try:
        sac_move = chess.Move.from_uci(sac_uci)
        if sac_move not in board.legal_moves:
            return {}
        board.push(sac_move)
    except Exception:
        return {}

    if board.is_game_over():
        analysis = await lc0_engine.analyze(board.fen(), nodes=PLAYOUT_NODES)
        white_cp = metrics.eval_cp_number(analysis.get("evaluation")) or 0
        attacker_eval_cp = white_cp if attacker_is_white else -white_cp
        return {
            "finding_id": finding_id,
            "fen": board.fen(),
            "line": [sac_uci],
            "attacker_is_white": attacker_is_white,
            "attacker_eval_cp": attacker_eval_cp,
            "ply": 1,
            "target_plies": PLAYOUT_PLIES,
            "user_to_move": False,
        }

    # LC0 plays best defense
    def_analysis = await lc0_engine.analyze(board.fen(), nodes=PLAYOUT_NODES)
    best_moves = def_analysis.get("best_moves", [])
    if not best_moves:
        return {"error": "engine_unavailable"}

    m0 = best_moves[0]
    defense_uci = m0["move"] if isinstance(m0, dict) else m0
    def_move = chess.Move.from_uci(defense_uci)
    board.push(def_move)

    # Analyze position after LC0 defense (attacker is now to move)
    post_def_analysis = await lc0_engine.analyze(board.fen(), nodes=PLAYOUT_NODES)
    white_cp = metrics.eval_cp_number(post_def_analysis.get("evaluation"))
    if white_cp is None:
        white_cp = 0
    attacker_eval_cp = white_cp if attacker_is_white else -white_cp

    return {
        "finding_id": finding_id,
        "fen": board.fen(),
        "line": [sac_uci, defense_uci],
        "attacker_is_white": attacker_is_white,
        "attacker_eval_cp": attacker_eval_cp,
        "ply": 2,
        "target_plies": PLAYOUT_PLIES,
        "user_to_move": True,
    }


async def play_sac_move(
    finding_id: str,
    line: List[str],
    user_uci: str,
    lc0_engine,
    history: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Execute user attack move against defender LC0, judge move quality, and get LC0 defense reply."""
    if not lc0_engine or not lc0_engine.is_available():
        return {"error": "engine_unavailable"}

    profile = store.load_profile()
    if not profile or "steer_findings" not in profile:
        return None

    sf = next((f for f in profile["steer_findings"] if f.get("id") == finding_id), None)
    if not sf or "fen_before" not in sf:
        return None

    fen_before = sf["fen_before"]
    board = chess.Board(fen_before)
    attacker_is_white = (board.turn == chess.WHITE)

    # Replay existing line from fen_before
    for move_uci in line:
        try:
            m = chess.Move.from_uci(move_uci)
            if m not in board.legal_moves:
                raise ValueError(f"Invalid line move: {move_uci}")
            board.push(m)
        except Exception as e:
            raise ValueError(f"Invalid line move: {move_uci}") from e

    if (board.turn == chess.WHITE) != attacker_is_white:
        raise ValueError("Not attacker's turn to move")

    try:
        user_move = chess.Move.from_uci(user_uci)
    except Exception as e:
        raise ValueError(f"Invalid UCI move format: {user_uci}") from e

    if user_move not in board.legal_moves:
        raise ValueError(f"Illegal move: {user_uci}")

    # 1. Pre-move analysis
    pre_analysis = await lc0_engine.analyze(board.fen(), nodes=PLAYOUT_NODES)
    best_moves_pre = pre_analysis.get("best_moves", [])
    if not best_moves_pre:
        return {"error": "engine_unavailable"}

    mb = best_moves_pre[0]
    lc0_best_uci = mb["move"] if isinstance(mb, dict) else mb
    try:
        m_best = chess.Move.from_uci(lc0_best_uci)
        lc0_best_san = board.san(m_best) if m_best in board.legal_moves else lc0_best_uci
    except Exception:
        lc0_best_san = lc0_best_uci

    white_cp_pre = metrics.eval_cp_number(pre_analysis.get("evaluation"))
    if white_cp_pre is None:
        white_cp_pre = 0
    eval_best_att = white_cp_pre if attacker_is_white else -white_cp_pre

    # 2. Apply user move
    board.push(user_move)
    ply = len(line) + 1

    # 3. Post-user analysis
    post_user_analysis = await lc0_engine.analyze(board.fen(), nodes=PLAYOUT_NODES)
    white_cp_user = metrics.eval_cp_number(post_user_analysis.get("evaluation"))
    if white_cp_user is None:
        white_cp_user = 0
    eval_after_att = white_cp_user if attacker_is_white else -white_cp_user

    drop = eval_best_att - eval_after_att

    if user_uci == lc0_best_uci or drop <= 30:
        quality = "great"
    elif drop <= 100:
        quality = "ok"
    else:
        quality = "drift"

    current_history = (history or []) + [quality]

    # 4. Check completion or play LC0 reply
    game_over_after_user = board.is_game_over()
    if game_over_after_user or ply >= PLAYOUT_PLIES:
        is_complete = True
        lc0_reply = None
        final_line = line + [user_uci]
        final_eval_att = eval_after_att
    else:
        best_moves_post = post_user_analysis.get("best_moves", [])
        if not best_moves_post:
            return {"error": "engine_unavailable"}
        mr = best_moves_post[0]
        lc0_reply_uci = mr["move"] if isinstance(mr, dict) else mr
        try:
            m_rep = chess.Move.from_uci(lc0_reply_uci)
            lc0_reply_san = board.san(m_rep) if m_rep in board.legal_moves else lc0_reply_uci
        except Exception:
            lc0_reply_san = lc0_reply_uci

        lc0_reply = {"uci": lc0_reply_uci, "san": lc0_reply_san}

        try:
            board.push(chess.Move.from_uci(lc0_reply_uci))
        except Exception:
            pass
        ply += 1
        final_line = line + [user_uci, lc0_reply_uci]

        post_reply_analysis = await lc0_engine.analyze(board.fen(), nodes=PLAYOUT_NODES)
        white_cp_reply = metrics.eval_cp_number(post_reply_analysis.get("evaluation"))
        if white_cp_reply is None:
            white_cp_reply = 0
        final_eval_att = white_cp_reply if attacker_is_white else -white_cp_reply

        is_complete = board.is_game_over() or (ply >= PLAYOUT_PLIES)


    res = {
        "quality": quality,
        "lc0_best_attack": {
            "uci": lc0_best_uci,
            "san": lc0_best_san,
        },
        "eval_after_cp": eval_after_att,
        "lc0_reply": lc0_reply,
        "fen": board.fen(),
        "line": final_line,
        "ply": ply,
        "attacker_eval_cp": final_eval_att,
        "is_complete": is_complete,
    }

    if is_complete:
        great_cnt = current_history.count("great")
        ok_cnt = current_history.count("ok")
        drift_cnt = current_history.count("drift")
        total_moves = len(current_history)

        defender_is_white = not attacker_is_white
        attacker_won_by_mate = board.is_checkmate() and (board.turn == (chess.WHITE if defender_is_white else chess.BLACK))

        if final_eval_att >= 50 or attacker_won_by_mate:
            verdict = "You kept the attack"
        else:
            verdict = "the attack fizzled — LC0 held"

        res["summary"] = {
            "moves": total_moves,
            "great": great_cnt,
            "ok": ok_cnt,
            "drift": drift_cnt,
            "final_eval_cp": final_eval_att,
            "verdict": verdict,
        }

    return res

