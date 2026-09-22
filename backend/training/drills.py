import datetime
import hashlib
import uuid
import chess
from backend.training import store, puzzle_db, metrics


def check_attempt(drill: dict, ply: int, move_uci: str) -> dict:
    """Judge one user move of a drill, following Lichess puzzle rules:
    the stored line (line_uci: user move, opponent reply, user move, ...)
    must be followed move by move; replies are auto-played by the client;
    the drill completes only at the end of the line. Two extra acceptances,
    also from Lichess: any move that delivers checkmate wins immediately,
    and at ply 0 near-equal engine alternatives (alt_solution_ucis) count
    as correct. Raises ValueError if ply does not address a user move.

    Older drill sets carry only solution_uci; they act as one-move lines.
    """
    line = drill.get("line_uci") or [drill["solution_uci"]]
    if ply < 0 or ply >= len(line) or ply % 2 != 0:
        raise ValueError("ply outside solution line")

    board = chess.Board(drill["fen"])
    if drill.get("setup_move_uci"):
        board.push_uci(drill["setup_move_uci"])
    for m in line[:ply]:
        board.push_uci(m)

    expected = set(metrics.accepted_ucis(board, line[ply]))
    alt = set(drill.get("alt_solution_ucis") or []) if ply == 0 else set()

    if move_uci not in expected and move_uci not in alt:
        try:
            after = board.copy(stack=False)
            after.push(board.parse_uci(move_uci))
            if after.is_checkmate():
                return {"correct": True, "complete": True, "reply_uci": None}
        except ValueError:
            pass
        return {"correct": False, "complete": False, "reply_uci": None}

    if move_uci not in expected:
        # An accepted alternative diverges from the stored line, so there
        # is no line left to walk — the drill counts as solved here.
        return {"correct": True, "complete": True, "reply_uci": None}

    complete = ply + 2 >= len(line)  # no further user move in the line
    reply = line[ply + 1] if ply + 1 < len(line) else None
    return {"correct": True, "complete": complete, "reply_uci": reply}

def build_drill_from_finding(f: dict, source: str = "own_game", suspect_theme: str = None) -> dict:
    """Construct a drill dict from a profile finding object using EpdCache policy and stage_b data."""
    board_before = chess.Board(f["fen_before"])
    epd = board_before.epd()
    policy_data = store.EpdCache("policy").get(epd)
    if policy_data and "policy" in policy_data:
        alt_ucis = metrics.alt_solutions(policy_data["policy"])
    else:
        alt_ucis = [f["best"]["uci"]]
    alt_ucis = sorted({u for a in alt_ucis
                       for u in metrics.accepted_ucis(board_before, a)})

    b_data = store.EpdCache("stage_b").get(epd)
    saliency = b_data["saliency"] if (b_data and "saliency" in b_data) else {}

    tags = list(f.get("motifs", []))
    if suspect_theme and suspect_theme not in tags:
        tags.append(suspect_theme)

    finding_id = f.get("id")
    if finding_id:
        drill_id = f"d-{hashlib.sha1(str(finding_id).encode('utf-8')).hexdigest()[:12]}"
    else:
        drill_id = f"d-{hashlib.sha1(epd.encode('utf-8')).hexdigest()[:12]}"

    drill = {
        "id": drill_id,
        "source": source,
        "fen": f["fen_before"],
        "setup_move_uci": None,
        "solution_uci": f["best"]["uci"],
        "line_uci": [f["best"]["uci"]],
        "alt_solution_ucis": alt_ucis,
        "solution_san": f["best"]["san"],
        "tags": tags,
        "difficulty": 1500,
        "origin": {
            "finding_id": f.get("id"),
            "puzzle_id": None,
            "eco": f.get("opening", {}).get("eco")
        },
        "reveal": {
            "policy": policy_data["policy"] if policy_data else [],
            "saliency": saliency,
            "motifs": f.get("motifs", []),
            "concepts": f.get("concepts", []),
            "pv_san": f.get("pv_san", []),
            "swing_cp": f.get("confirmation", {}).get("swing_cp", 0)
        }
    }
    if suspect_theme:
        drill["suspect_theme"] = suspect_theme
    return drill


async def generate_drill_set(count: int, profile: dict, repertoire: dict, engine, vision, steer_weight: float = 0.0) -> dict:
    steer_count = int(count * steer_weight)
    rem_count = count - steer_count
    own_game_count = int(rem_count * 0.4)
    corpus_count = int(rem_count * 0.4)
    hidden_gem_count = rem_count - own_game_count - corpus_count

    drills = []
    
    if steer_count > 0 and profile and "steer_findings" in profile:
        s_findings = [f for f in profile["steer_findings"] if f.get("had_sharp_move")]
        s_findings.sort(key=lambda x: x["steer"]["complexity"], reverse=True)
        seen_s_epds = set()
        
        for f in s_findings:
            if len([d for d in drills if d["source"] == "steer"]) >= steer_count:
                break
            board_before = chess.Board(f["fen_before"])
            epd = board_before.epd()
            if epd in seen_s_epds:
                continue
            seen_s_epds.add(epd)
            
            p_data = store.EpdCache("policy").get(epd)
            policy = p_data["policy"] if p_data else []
            s_data = store.EpdCache("stage_b").get(epd)
            saliency = s_data["saliency"] if s_data and "saliency" in s_data else {}
            
            playable_ucis = [c["uci"] for c in f.get("playable_candidates", [])]
            alt_ucis = sorted({u for a in playable_ucis for u in metrics.accepted_ucis(board_before, a)})
            
            drills.append({
                "id": f"d-{uuid.uuid4().hex[:8]}",
                "source": "steer",
                "fen": f["fen_before"],
                "setup_move_uci": None,
                "solution_uci": f["steer"]["uci"],
                "line_uci": [f["steer"]["uci"]],
                "alt_solution_ucis": alt_ucis,
                "solution_san": f["steer"]["san"],
                "tags": ["steer"],
                "difficulty": 1700,
                "origin": {"finding_id": f["id"], "puzzle_id": None, "eco": f.get("opening", {}).get("eco")},
                "reveal": {
                    "policy": policy,
                    "saliency": saliency,
                    "complexity_components": f["steer"]["components"],
                    "best_uci": f["best"]["uci"],
                    "best_eval_cp": f["best"]["eval_cp"],
                    "steer_uci": f["steer"]["uci"],
                    "steer_eval_cp": f["steer"]["eval_cp"],
                    "eval_loss_cp": f.get("eval_loss_cp", 0),
                    "minefield": f.get("playable_candidates", []),
                    "motifs": [],
                    "concepts": [],
                    "pv_san": [],
                    "swing_cp": 0
                }
            })
    
    if profile and "findings" in profile:
        def sort_key(f):
            conf = f.get("confirmation", {})
            return (conf.get("confirmed", False), conf.get("swing_cp", 0))
            
        findings = sorted(profile["findings"], key=sort_key, reverse=True)

        seen_epds = set()
        seen_solutions = set()
        own_game_added = 0
        for f in findings:
            if own_game_added >= own_game_count:
                break
            board_before = chess.Board(f["fen_before"])
            epd = board_before.epd()
            # findings are sorted best-first, so dedupe keeps the strongest
            # instance of a repeated position or repeated solution move
            if epd in seen_epds or f["best"]["uci"] in seen_solutions:
                continue
            seen_epds.add(epd)
            seen_solutions.add(f["best"]["uci"])
            own_game_added += 1
            drills.append(build_drill_from_finding(f, source="own_game"))
            
    top_motifs = []
    if profile and "aggregates" in profile and "by_motif" in profile["aggregates"]:
        top_motifs = [m for m, stat in sorted(profile["aggregates"]["by_motif"].items(), key=lambda x: -x[1]["blind"])]
        
    puzzles = puzzle_db.sample_puzzles(top_motifs[:3] if top_motifs else None, None, (1600, 2300), corpus_count)
    
    for p in puzzles:
        moves = p["moves"].split()
        if len(moves) < 2:
            continue
        setup_move_uci = moves[0]
        solution_uci = moves[1]
        
        board = chess.Board(p["fen"])
        board.push_uci(setup_move_uci)
        fen_after_setup = board.fen()
        
        policy_dist = await engine.get_policy_distribution(fen_after_setup, nodes=1)
        if not policy_dist:
            continue  # engine in mock mode — never save mock data
        saliency = vision.saliency_absolute(fen_after_setup)
        
        pv_san_list = []
        board_copy = board.copy()
        for m in moves[1:]:
            move = chess.Move.from_uci(m)
            pv_san_list.append(board_copy.san(move))
            board_copy.push(move)
        
        drills.append({
            "id": f"d-{uuid.uuid4().hex[:8]}",
            "source": "corpus",
            "fen": p["fen"],
            "setup_move_uci": setup_move_uci,
            "solution_uci": solution_uci,
            "line_uci": moves[1:],
            "alt_solution_ucis": metrics.accepted_ucis(board, solution_uci),
            "solution_san": board.san(chess.Move.from_uci(solution_uci)),
            "tags": p["themes"].split(),
            "difficulty": p["rating"],
            "origin": {"finding_id": None, "puzzle_id": p["id"], "eco": None},
            "reveal": {
                "policy": policy_dist,
                "saliency": saliency,
                "motifs": p["themes"].split(),
                "concepts": [],
                "pv_san": pv_san_list,
                "swing_cp": 0
            }
        })
        
    if hidden_gem_count > 0:
        from backend.training.gems import scan_for_gems, gem_candidates_from_profile
        candidates = gem_candidates_from_profile(profile)
        gem_results = await scan_for_gems(
            candidates, engine, vision, max_bt3=hidden_gem_count * 5)
        for g in gem_results[:hidden_gem_count]:
            drills.append({
                "id": f"d-{uuid.uuid4().hex[:8]}",
                "source": "hidden_gem",
                "fen": g["fen"],
                "setup_move_uci": None,
                "solution_uci": g["solution_uci"],
                "line_uci": [g["solution_uci"]],
                "alt_solution_ucis": g["alt_solution_ucis"],
                "solution_san": g["solution_san"],
                "tags": g["motifs"],
                "difficulty": 1800,
                "origin": {"finding_id": None, "puzzle_id": None, "eco": None},
                "reveal": {
                    "policy": g["policy"],
                    "saliency": g["saliency"],
                    "motifs": g["motifs"],
                    "concepts": [],
                    "pv_san": g["pv_san"],
                    "swing_cp": 0
                }
            })

    import random
    random.shuffle(drills)

    drill_set = {
        "id": f"set-{datetime.datetime.utcnow().strftime('%Y-%m-%d-%H%M%S')}-{uuid.uuid4().hex[:4]}",
        "created": datetime.datetime.utcnow().isoformat(),
        "drills": drills
    }
    store.save_drill_set(drill_set)
    return drill_set


# ======================================================================
# Repertoire drills (Epoch III, R2) — turn a variation tree's CRITICAL
# nodes into SRS-tracked line drills the user must solve. Reuses
# check_attempt for judging and record_attempt (attempts.py) for
# scheduling. Deterministic; no engine calls.
# ======================================================================

import hashlib


def _rep_drill_id(color: str, epd: str) -> str:
    """Stable id for a critical position, so the SRS tracks the SAME node
    across tree rebuilds (tree node ids are per-build counters and change)."""
    return "rep-" + hashlib.sha1(f"{color}:{epd}".encode("utf-8")).hexdigest()[:12]


def _walk_line(tree: dict, start: dict, max_len: int = 5) -> list:
    """Walk the main (most-played) line from a user node into a
    check_attempt line_uci: [user, opp, user, opp, ...] ending on a user
    move. Opponent replies are the highest-frequency child each step."""
    by_epd = {chess.Board(n["fen_before"]).epd(): n for n in tree["nodes"]}
    line: list = []
    node = start
    while len(line) < max_len:
        um = node.get("user_move")
        if not um:
            break
        line.append(um["uci"])
        board = chess.Board(node["fen_before"])
        try:
            board.push_uci(um["uci"])
        except ValueError:
            line.pop()
            break
        replies = node.get("opponent_replies") or []
        if not replies:
            break
        top = replies[0]  # opponent_replies is sorted by count desc
        board.push_uci(top["uci"])
        child = by_epd.get(board.epd())
        if not child:
            break
        line.append(top["uci"])
        node = child
    # end on a user move (odd length) so check_attempt completes cleanly
    if len(line) % 2 == 0 and line:
        line = line[:-1]
    return line


def build_repertoire_drills(tree: dict, max_line_len: int = 5) -> list:
    """One drill per CRITICAL node of a repertoire tree. Each is a
    check_attempt-compatible line drill with a stable, position-derived id,
    source 'repertoire', and the node's coach reveal (incl. any explanation)."""
    eco = tree.get("eco", "???")
    color = tree.get("color", "white")
    drills: list = []
    seen: set = set()
    for node in tree.get("nodes", []):
        if not node.get("critical") or not node.get("user_move"):
            continue
        try:
            board = chess.Board(node["fen_before"])
        except ValueError:
            continue
        epd = board.epd()
        drill_id = _rep_drill_id(color, epd)
        if drill_id in seen:
            continue
        seen.add(drill_id)

        line = _walk_line(tree, node, max_line_len) or [node["user_move"]["uci"]]
        drills.append({
            "id": drill_id,
            "source": "repertoire",
            "fen": node["fen_before"],
            "setup_move_uci": None,
            "solution_uci": node["user_move"]["uci"],
            "line_uci": line,
            "alt_solution_ucis": metrics.accepted_ucis(board, node["user_move"]["uci"]),
            "solution_san": node["user_move"].get("san"),
            "tags": [eco, node.get("critical_reason", "critical")],
            "difficulty": 1650,
            "origin": {
                "eco": eco, "color": color, "node_id": node.get("id"),
                "critical_reason": node.get("critical_reason"),
            },
            "reveal": {
                "best_uci": node["user_move"]["uci"],
                "best_eval_cp": node.get("eval_cp"),
                "complexity": node.get("complexity"),
                "user_blind_rate": node.get("user_blind_rate"),
                "critical_reason": node.get("critical_reason"),
                "explanation": node.get("explanation"),
                "minefield": node.get("opponent_replies", []),
                "motifs": [], "concepts": [], "pv_san": [], "swing_cp": 0,
            },
        })
    return drills


def build_repertoire_drill_set(tree: dict, max_line_len: int = 5) -> dict:
    """Wrap build_repertoire_drills in a drill-set envelope (same shape as
    generate_drill_set) so it can be saved and flow through DrillMode + SRS."""
    eco = tree.get("eco", "???")
    color = tree.get("color", "white")
    return {
        "id": f"rep-{eco}-{color}-{datetime.datetime.utcnow().strftime('%Y-%m-%d-%H%M%S')}",
        "created": datetime.datetime.utcnow().isoformat(),
        "source": "repertoire",
        "eco": eco,
        "color": color,
        "drills": build_repertoire_drills(tree, max_line_len),
    }
