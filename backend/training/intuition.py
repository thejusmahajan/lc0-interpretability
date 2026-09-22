import os
import json
import time
import random
import chess
from typing import List, Dict, Any, Optional
from backend.training import store

NEAR_FORCED_THRESHOLD = 0.9
REVEAL_TOP_K = 5


def build_session(count: int = 10) -> List[Dict[str, str]]:
    """Sample eligible positions from EpdCache('policy') for a intuition session.
    
    Filters out near-forced moves (policy[0].p >= 0.9) and positions with <2 policy moves.
    Returns list of {"epd": epd, "fen": fen}. Policy and answers stay server-side.
    """
    cache = store.EpdCache("policy")
    epd_keys = cache.keys()
    eligible = []

    for epd in epd_keys:
        rec = cache.get(epd)
        if not rec:
            continue
        policy = rec.get("policy", [])
        if len(policy) >= 2 and policy[0].get("p", 0.0) < NEAR_FORCED_THRESHOLD:
            eligible.append(epd)

    if len(eligible) <= count:
        sampled_epds = eligible
    else:
        sampled_epds = random.sample(eligible, count)

    session = []
    for epd in sampled_epds:
        board = chess.Board()
        board.set_epd(epd)
        session.append({
            "epd": epd,
            "fen": board.fen(),
        })

    return session


def _record_attempt(epd: str, uci: str, correct: bool, rank: Optional[int]):
    store._ensure_dirs()
    attempts_path = os.path.join(store.TRAINING_DIR, "intuition_attempts.jsonl")
    record = {
        "epd": epd,
        "uci": uci,
        "correct": correct,
        "rank": rank,
        "ts": time.time(),
    }
    with open(attempts_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def score_guess(epd: str, uci: str) -> Dict[str, Any]:
    """Score user's guess against LC0's policy ranking for a position.
    
    Computes top-1 match, rank index, your move p%, top move p%, and top-5 policy.
    Logs attempt to intuition_attempts.jsonl.
    """
    cache = store.EpdCache("policy")
    rec = cache.get(epd)
    if not rec or not rec.get("policy"):
        return {}

    policy = rec["policy"]
    top = policy[0]
    top_uci = top.get("uci")
    correct = (uci == top_uci)

    rank = None
    your_move = None
    for i, entry in enumerate(policy, start=1):
        if entry.get("uci") == uci:
            rank = i
            your_move = {
                "uci": entry["uci"],
                "san": entry.get("san", uci),
                "p": entry.get("p", 0.0),
            }
            break

    top_move = {
        "uci": top["uci"],
        "san": top.get("san", top["uci"]),
        "p": top.get("p", 0.0),
    }

    top_policy = [
        {
            "uci": entry["uci"],
            "san": entry.get("san", entry["uci"]),
            "p": entry.get("p", 0.0),
        }
        for entry in policy[:REVEAL_TOP_K]
    ]

    _record_attempt(epd, uci, correct, rank)

    return {
        "correct": correct,
        "rank": rank,
        "your_move": your_move,
        "top_move": top_move,
        "top_policy": top_policy,
    }


def get_stats() -> Dict[str, Any]:
    """Calculate overall and recent (last 50) intuition accuracy stats."""
    store._ensure_dirs()
    attempts_path = os.path.join(store.TRAINING_DIR, "intuition_attempts.jsonl")
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
    accuracy = round(correct_count / total, 4) if total > 0 else 0.0

    recent = attempts[-50:]
    recent_correct = sum(1 for a in recent if a.get("correct"))
    recent_accuracy = round(recent_correct / len(recent), 4) if len(recent) > 0 else 0.0

    return {
        "total": total,
        "correct": correct_count,
        "accuracy": accuracy,
        "recent_accuracy": recent_accuracy,
    }
