"""Repertoire Architect (Engine 2) — style-rooted tactical repertoire.

Epoch II rewrite (TS3): instead of picking openings from a canned motif list
(SACRIFICE_TARGETS — retired), mine the user's ingrained repertoire from
profile["aggregates"]["by_opening"] (ECOs they actually reach), classify each
as kept / repaired / dry, and tint at sound-but-sharper branch points via
steer_candidates (bounded eval loss).

Pure orchestration: metric math from `backend.training.metrics`, lines/tabiya
from `openings`, engine evals from the app's singleton. Deterministic
rationale — no LLM.

OWNERSHIP: Opus worker (TS3). See CLAUDE_TRAINING_TASKS.md.
"""

from __future__ import annotations

import datetime
from collections import Counter
from typing import Optional

import chess

from backend.training import metrics, openings
from backend.training.metrics import DEFAULT_CONFIG, TrainingConfig

# Minimum user-played moves in an ECO for it to be considered "ingrained".
REPERTOIRE_MIN_MOVES = 5

# Engine budget: max analyze() calls per build (reused from the old module).
MAX_ENGINE_CALLS = 15

# Below this mean_complexity an ECO is classified as "dry" (low tactical
# potential — the opening itself is calm, not the user's choice).
DRY_COMPLEXITY_THRESHOLD = 0.25

RATIONALE_TEMPLATE = (
    "Your {name} ({line_pgn}): {origin_text}. "
    "LC0 holds the tabiya at {cp}cp with a {draw_pct} draw share"
    "{tint_text}."
)


def _leaky_ecos(profile: dict) -> set[str]:
    """ECOs that have Track A findings (confirmed mistakes) — genuine leaks."""
    ecos: set[str] = set()
    for f in profile.get("findings", []):
        eco = f.get("opening", {}).get("eco")
        if eco:
            ecos.add(eco)
    return ecos


def _classify_eco(
    eco: str,
    leaky_ecos: set[str],
    steer_summary: dict,
) -> str:
    """Classify: repaired > kept > dry."""
    if eco in leaky_ecos:
        return "repaired"
    ss = steer_summary.get(eco)
    if ss and ss.get("moves", 0) >= 3:
        if ss.get("mean_complexity", 0.0) < DRY_COMPLEXITY_THRESHOLD and ss.get("sharp_moves", ss.get("tal_moves", 0)) == 0:
            return "dry"
    return "kept"


def _findings_color_map(profile: dict) -> dict[str, str]:
    """The color the user played each ECO, inferred from their findings
    (which carry user_color). Covers only openings that produced a mistake,
    but that includes every 'repair' target — the ones that matter most."""
    counts: dict[str, Counter] = {}
    for f in profile.get("findings", []):
        eco = f.get("opening", {}).get("eco")
        c = f.get("user_color")
        if eco and c:
            counts.setdefault(eco, Counter())[c] += 1
    return {eco: cnt.most_common(1)[0][0] for eco, cnt in counts.items()}


def _plays_as_color(stats: dict, eco: str, color: str,
                    findings_color: dict[str, str], line_info: dict) -> bool:
    """Does the user play this ECO as `color`? Precedence, most reliable first:
      1. per-color move counts in the profile (moves_white / moves_black) —
         authoritative, emitted by the pipeline once it aggregates color
         (requires a re-diagnosis to populate);
      2. the color of the user's findings in this ECO — correct for every
         leaky opening, available now with no re-diagnosis;
      3. parity of the tabiya line — a legacy last resort that CAN
         misattribute (e.g. an odd-length Najdorf tabiya reads as white),
         used only when neither signal above exists.
    """
    if "moves_white" in stats or "moves_black" in stats:
        return stats.get(f"moves_{color}", 0) >= REPERTOIRE_MIN_MOVES
    if stats.get("moves", 0) < REPERTOIRE_MIN_MOVES:
        return False
    if eco in findings_color:
        return findings_color[eco] == color
    parity_color = "white" if len(line_info["uci_moves"]) % 2 == 1 else "black"
    return parity_color == color


def _find_eco_line(eco: str) -> Optional[dict]:
    """Find the openings trie entry for an ECO code. Returns
    {"eco", "name", "uci_moves", "fen"} or None."""
    openings._load_openings()
    best = None
    for seq, info in openings._openings_trie.items():
        if info["eco"] == eco:
            if best is None or len(seq) < len(best[0]):
                best = (seq, info)
    if best is None:
        return None
    seq, info = best
    board = chess.Board()
    for uci in seq:
        try:
            board.push_uci(uci)
        except ValueError:
            return None
    return {
        "eco": info["eco"],
        "name": info["name"],
        "uci_moves": list(seq),
        "fen": board.fen(),
    }


async def build_repertoire(
    profile: dict,
    color: str,
    engine,
    top_n: int = 5,
    cfg: TrainingConfig = DEFAULT_CONFIG,
    style: str = "weakness",
) -> dict:
    """Style-rooted tactical repertoire builder (Epoch II, TS3).

    Mines the user's ingrained openings, classifies them, and tints
    each at the sharpest-but-sound branch point via steer_candidates.
    The `style` parameter is kept for backward compatibility but both
    values now use the same style-rooted logic (SACRIFICE_TARGETS retired).
    """
    if color not in ("white", "black"):
        raise ValueError(f"color must be 'white' or 'black', got {color!r}")

    by_opening = (profile or {}).get("aggregates", {}).get("by_opening", {})
    steer_summary = (profile or {}).get("steer_summary", {})
    leaky = _leaky_ecos(profile or {})

    # Step 1: Mine ingrained ECOs the user actually plays as `color`
    findings_color = _findings_color_map(profile or {})
    base_ecos: list[tuple[str, dict]] = []
    for eco, stats in by_opening.items():
        line_info = _find_eco_line(eco)
        if line_info is None:
            continue
        if not _plays_as_color(stats, eco, color, findings_color, line_info):
            continue
        base_ecos.append((eco, {**stats, "_line_info": line_info}))

    # Sort by move count (most played first — these are the most ingrained)
    base_ecos.sort(key=lambda x: -x[1].get("moves", 0))

    # Step 2 + 3: Classify and tint each base opening
    recommendations = []
    engine_calls = 0

    for eco, stats in base_ecos:
        if engine_calls >= MAX_ENGINE_CALLS:
            break
        if len(recommendations) >= top_n:
            break

        line_info = stats["_line_info"]
        classification = _classify_eco(eco, leaky, steer_summary)
        tabiya_fen = line_info["fen"]

        # Soundness + sharpness gate on tabiya
        analysis = await engine.analyze(
            tabiya_fen, depth=None, multipv=2,
            time_limit=cfg.repertoire_eval_seconds,
            nodes=cfg.repertoire_eval_nodes)
        engine_calls += 1

        cp = metrics.eval_cp_number(analysis["evaluation"])
        if cp is None:
            continue
        pov_cp = cp if color == "white" else -cp
        if pov_cp < -cfg.sound_eval_cp:
            continue  # unsound for the requested color

        sharpness = metrics.sharpness_from_wdl(analysis.get("wdl"), cfg)
        is_sharp = sharpness["sharp"] if sharpness else False
        draw_pct = sharpness["draw_pct"] if sharpness else None

        # Tactical tint via steer_candidates
        tint_move = None
        tint_complexity = None
        tint_eval_cp = None
        tint_eval_loss_cp = None
        had_sharp_move = False

        # Gather policy for the tabiya to score candidate complexity
        policy = await engine.get_policy_distribution(tabiya_fen, nodes=1)
        if policy:
            # Evaluate top-k candidate moves at the tabiya
            candidates = []
            top_k = min(cfg.steer_top_k, len(policy))
            for p_entry in policy[:top_k]:
                uci = p_entry.get("uci")
                if not uci:
                    continue
                try:
                    move = chess.Board(tabiya_fen).parse_uci(uci)
                except (ValueError, chess.InvalidMoveError):
                    continue

                board_after = chess.Board(tabiya_fen)
                board_after.push(move)

                if engine_calls >= MAX_ENGINE_CALLS:
                    break
                cand_analysis = await engine.analyze(
                    board_after.fen(), depth=None, multipv=2,
                    time_limit=cfg.repertoire_eval_seconds,
                    nodes=cfg.repertoire_eval_nodes)
                engine_calls += 1

                cand_policy = await engine.get_policy_distribution(
                    board_after.fen(), nodes=1)

                complexity = metrics.tactical_complexity(
                    cand_analysis, cand_policy or [], None, cfg)

                cand_cp = metrics.eval_cp_number(cand_analysis["evaluation"])
                if cand_cp is None:
                    continue
                # Mover POV after our move = opponent to move, so our eval =
                # white-POV negated for black.
                eval_cp_mover = cand_cp if color == "white" else -cand_cp

                candidates.append({
                    "uci": uci,
                    "san": p_entry.get("san", uci),
                    "eval_cp": eval_cp_mover,
                    "complexity": complexity["score"],
                    "components": complexity,
                })

            if candidates:
                best_eval = max(c["eval_cp"] for c in candidates)
                steer_res = metrics.steer_candidates(candidates, best_eval, cfg)
                if steer_res["had_sharp_move"] and steer_res["sharp_move"]:
                    had_sharp_move = True
                    tm = steer_res["sharp_move"]
                    tint_move = {"uci": tm["uci"], "san": tm["san"]}
                    tint_complexity = tm["complexity"]
                    tint_eval_cp = tm["eval_cp"]
                    tint_eval_loss_cp = best_eval - tm["eval_cp"]

        # Inclusion: always help repair an opening the user leaks in (soundness
        # already checked above — sharpness must NOT exclude a solid opening
        # they actually play). Otherwise the opening earns a slot only if it
        # offers tactical value: a sharp tabiya or a sound sharper tint. A calm
        # 'kept'/'dry' line with nothing to fix or sharpen is not worth a slot.
        if classification != "repaired" and not had_sharp_move and not is_sharp:
            continue

        # Determine final origin
        if had_sharp_move:
            origin = "tinted"
        elif classification == "repaired":
            origin = "repaired"
        else:
            origin = "kept"

        # Build rationale text
        origin_texts = {
            "kept": "sound and ingrained — keep playing it",
            "repaired": "has leaks in your play — study the corrected lines",
            "tinted": "has a sharper-but-sound branch to explore",
        }
        origin_text = origin_texts[origin]

        tint_text = ""
        if tint_move:
            tint_text = (
                f"; the tactical tint {tint_move['san']} "
                f"(complexity {tint_complexity:.2f}, "
                f"eval loss {tint_eval_loss_cp}cp) "
                f"creates more danger for the opponent"
            )

        board = chess.Board()
        line_pgn = board.variation_san(
            [chess.Move.from_uci(u) for u in line_info["uci_moves"]])

        recommendations.append({
            "eco": eco,
            "name": line_info["name"],
            "line_pgn": line_pgn,
            "eval_cp": cp,
            "draw_pct": round(draw_pct, 1) if draw_pct is not None else None,
            "origin": origin,
            "classification": classification,
            "complexity": round(tint_complexity, 4) if tint_complexity else None,
            "tint_move": tint_move,
            "eval_loss_cp": tint_eval_loss_cp,
            "steer_summary": steer_summary.get(eco),
            "user_moves": stats.get("moves", 0),
            "user_blind_rate": stats.get("blind_rate", 0.0),
            "rationale": RATIONALE_TEMPLATE.format(
                name=line_info["name"],
                line_pgn=line_pgn,
                origin_text=origin_text,
                cp=cp,
                draw_pct=(f"{draw_pct:.0f}%" if draw_pct is not None
                          else "unmeasured"),
                tint_text=tint_text,
            ),
        })

    return {
        "version": 2,
        "color": color,
        "style": style,
        "created": datetime.datetime.utcnow().isoformat(),
        "recommendations": recommendations,
    }


def _replies_from(transitions, epd, min_games):
    """Opponent replies actually seen from a position, frequency-weighted.
    Prunes moves seen in fewer than min_games games."""
    trans = transitions.get(epd, {})
    kept = [(u, d) for u, d in trans.items() if d["count"] >= min_games]
    total = sum(d["count"] for _, d in kept)
    replies = [{"uci": u, "san": d["san"], "count": d["count"],
                "pct": round(d["count"] / total, 4) if total else 0.0}
               for u, d in kept]
    return sorted(replies, key=lambda r: r["count"], reverse=True)


async def build_repertoire_tree(
    eco: str,
    color: str,
    pgn_path_or_text: str,
    player_name: str,
    engine,
    profile: Optional[dict] = None,
    cfg: TrainingConfig = DEFAULT_CONFIG,
    min_games: int = 2,
    max_depth: int = 8,
) -> dict:
    """Build an engine-vetted, critical-marked variation tree of the user's OWN
    games in one opening (Epoch III, R1).

    Rooted at the initial position and grown down the paths the user actually
    played (games that reach this ECO's tabiya), NOT at the deep tabiya itself.
    A repertoire's decisions live in the plies leading into the opening, and a
    deep-tabiya root collapses to a single node. Explicit nodes are the user's
    decision points; opponent moves are frequency-weighted edges. user_move at
    each user node is the most-played *sound* move (steer-vetted). A node is
    critical when the user is genuinely blind there (from profile findings),
    or a wrong reply swings >= 150cp, or the position is tactically sharp.
    """
    import os
    import io
    from collections import defaultdict
    import chess.pgn
    from backend.training import store

    if os.path.exists(pgn_path_or_text):
        pgn_io = open(pgn_path_or_text, "r", encoding="utf-8")
    else:
        pgn_io = io.StringIO(pgn_path_or_text)

    try:
        user_color_enum = chess.WHITE if color == "white" else chess.BLACK
        line_info = _find_eco_line(eco)
        if not line_info:
            raise ValueError(f"Unknown ECO: {eco}")
        tabiya_epd = chess.Board(line_info["fen"]).epd()
        tabiya_ply = len(line_info["uci_moves"])
        # cover the whole opening trunk plus a few plies past the tabiya
        max_ply = tabiya_ply + max_depth

        # --- select the user's games that reach this opening --------------
        valid_games = []
        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break
            white = game.headers.get("White", "")
            black = game.headers.get("Black", "")
            if player_name.lower() in white.lower():
                gcol = chess.WHITE
            elif player_name.lower() in black.lower():
                gcol = chess.BLACK
            else:
                continue
            if gcol != user_color_enum:
                continue
            # Membership by longest-prefix ECO classification — the same way
            # the profile groups games. Matching the exact deep tabiya EPD is
            # far too strict (transpositions / move-order variants never hit it,
            # so deep ECOs like C99 select zero games).
            ucis = [n.move.uci() for n in game.mainline()]
            if not ucis:
                continue
            match = openings.classify(ucis)
            if match and match.get("eco") == eco:
                valid_games.append(game)
        n_valid = len(valid_games)

        # --- move-frequency transitions, recorded from ply 0 --------------
        transitions = defaultdict(dict)   # epd -> {uci: {"san","count"}}
        for game in valid_games:
            board = game.board()
            for node in game.mainline():
                epd = board.epd()
                move = node.move
                uci = move.uci()
                t = transitions[epd]
                if uci not in t:
                    t[uci] = {"san": board.san(move), "count": 0}
                t[uci]["count"] += 1
                board.push(move)

        # --- real blindness per position, from the profile findings -------
        # user_blind_rate = (blind/missed findings at this position) / (games
        # the user reached it) -- the actual intuitive-blindness signal, not
        # the move-inconsistency proxy.
        # Scope blind findings to games actually IN this tree (audit F5): a
        # transposition EPD reached by an unrelated opening's games must not
        # inflate a node's blind_rate. Match findings to valid_games by identity.
        valid_game_keys = set()
        for g in valid_games:
            h = g.headers
            valid_game_keys.add((h.get("White", ""), h.get("Black", ""),
                                 h.get("Date", ""), h.get("Result", "")))
        blind_by_epd = defaultdict(int)
        if profile:
            for f in profile.get("findings", []):
                fg = f.get("game", {})
                if (fg.get("white", ""), fg.get("black", ""),
                        fg.get("date", ""), fg.get("result", "")) not in valid_game_keys:
                    continue
                fb = f.get("fen_before")
                if not fb:
                    continue
                try:
                    fepd = chess.Board(fb).epd()
                except ValueError:
                    continue
                if f.get("severity") in ("blind", "missed"):
                    blind_by_epd[fepd] += 1

        # --- BFS the tree from the initial position -----------------------
        nodes = []
        node_by_id = {}
        visited = set()
        root_board = chess.Board()
        epd_to_node_id = {}
        queue = [(root_board.epd(), root_board.fen(), 0, None)]
        counter = 1

        while queue:
            epd, fen, ply, parent_id = queue.pop(0)
            if epd in visited:
                existing_id = epd_to_node_id.get(epd)
                if existing_id and parent_id and parent_id in node_by_id:
                    if existing_id not in node_by_id[parent_id]["children"]:
                        node_by_id[parent_id]["children"].append(existing_id)
                continue
            visited.add(epd)
            if ply > max_ply:
                continue

            board = chess.Board(fen)
            is_user_node = (board.turn == user_color_enum)
            node_id = f"{eco}-{color[0]}-{counter:04d}"
            counter += 1
            epd_to_node_id[epd] = node_id

            node = {
                "id": node_id,
                "fen_before": fen,
                "ply": ply,
                "is_user_node": is_user_node,
                "n_games": sum(t["count"] for t in transitions.get(epd, {}).values()),
                "parent": parent_id,
                "children": [],
            }
            if parent_id is not None and parent_id in node_by_id:
                node_by_id[parent_id]["children"].append(node_id)
            nodes.append(node)
            node_by_id[node_id] = node

            if is_user_node:
                played = list(transitions.get(epd, {}).keys())
                if not played:
                    node["opponent_replies"] = []
                    continue

                # candidates = the user's played moves + the policy-best move
                policy = await engine.get_policy_distribution(fen, nodes=1)
                cand_ucis = set(played)
                if policy:
                    cand_ucis.add(policy[0]["uci"])

                candidates = []
                for cuci in cand_ucis:
                    try:
                        mv = board.parse_uci(cuci)
                    except ValueError:
                        continue
                    after = board.copy(stack=False)
                    after.push(mv)
                    analysis = await engine.analyze(
                        after.fen(), depth=None, multipv=2,
                        time_limit=cfg.repertoire_eval_seconds,
                        nodes=cfg.repertoire_eval_nodes)
                    cand_pol = await engine.get_policy_distribution(after.fen(), nodes=1)
                    cp = metrics.eval_cp_number(analysis.get("evaluation"))
                    if cp is None:
                        continue
                    eval_mover = cp if color == "white" else -cp
                    comp = metrics.tactical_complexity(analysis, cand_pol or [], None, cfg)
                    candidates.append({
                        "uci": cuci, "san": board.san(mv),
                        "eval_cp": eval_mover, "complexity": comp["score"],
                    })

                if not candidates:
                    node["opponent_replies"] = []
                    continue

                best_eval = max(c["eval_cp"] for c in candidates)
                steer = metrics.steer_candidates(candidates, best_eval, cfg)
                playable = {c["uci"] for c in steer["playable"]}

                # user_move = most-played SOUND move; fall back to objective best
                chosen, best_ct = None, -1
                for c in candidates:
                    if c["uci"] in playable:
                        ct = transitions[epd].get(c["uci"], {}).get("count", 0)
                        if ct > best_ct:
                            chosen, best_ct = c, ct
                if chosen is None:
                    chosen = steer.get("objective_best")
                if chosen is None:
                    node["opponent_replies"] = []
                    continue

                node["user_move"] = {"uci": chosen["uci"], "san": chosen["san"]}
                node["eval_cp"] = chosen["eval_cp"]
                node["complexity"] = round(chosen["complexity"], 4)

                n_here = node["n_games"]
                blind_rate = min(1.0, blind_by_epd.get(epd, 0) / n_here) if n_here else 0.0
                node["user_blind_rate"] = round(blind_rate, 4)

                evals = sorted((c["eval_cp"] for c in candidates), reverse=True)
                eval_swing = evals[0] - evals[1] if len(evals) > 1 else 0

                critical, reason = False, None
                if blind_rate >= 0.5:
                    critical, reason = True, "blind_rate"
                elif eval_swing >= 150:
                    critical, reason = True, "eval_swing"
                elif chosen["complexity"] >= cfg.steer_highlight_complexity:
                    critical, reason = True, "complexity"
                node["critical"] = critical
                if critical:
                    node["critical_reason"] = reason

                # opponent replies FOLLOW the user_move; queue the grandchild
                # user nodes that result.
                after_user = board.copy(stack=False)
                after_user.push_uci(chosen["uci"])
                node["opponent_replies"] = _replies_from(
                    transitions, after_user.epd(), min_games)
                for rep in node["opponent_replies"]:
                    cb = chess.Board(after_user.fen())
                    cb.push_uci(rep["uci"])
                    queue.append((cb.epd(), cb.fen(), ply + 2, node_id))
            else:
                node["opponent_replies"] = _replies_from(transitions, epd, min_games)
                for rep in node["opponent_replies"]:
                    cb = board.copy(stack=False)
                    cb.push_uci(rep["uci"])
                    queue.append((cb.epd(), cb.fen(), ply + 1, node_id))

        tree = {
            "eco": eco,
            "color": color,
            "root_fen": root_board.fen(),
            "tabiya_ply": tabiya_ply,
            "depth": max_depth,
            "n_games": n_valid,
            "nodes": nodes,
        }
        filepath = os.path.join(store.TRAINING_DIR, f"repertoire_tree_{eco}_{color}.json")
        store._write_json_atomic(filepath, tree)
        return tree
    finally:
        if os.path.exists(pgn_path_or_text):
            pgn_io.close()
