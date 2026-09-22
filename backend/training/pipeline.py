import io
import os
import re
import asyncio
import datetime
import logging
from collections import defaultdict
from typing import Optional
import chess
import chess.pgn

logger = logging.getLogger(__name__)
from backend.training import store, openings, metrics
from backend.tactics import MotifDetector
from backend.concept_mapper import analyze_position
from tqdm.auto import tqdm

_CLK_RE = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]")


def clock_seconds(comment: str) -> Optional[float]:
    """Seconds left on the mover's clock, read from a lichess-style
    [%clk H:MM:SS] annotation. None when the comment carries no clock."""
    m = _CLK_RE.search(comment or "")
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def is_time_scramble(comment: str,
                     cfg: metrics.TrainingConfig = metrics.DEFAULT_CONFIG) -> bool:
    """True when the move was played in a time scramble (clock below
    cfg.min_clock_seconds). Moves without clock data never count as
    scrambles, so PGNs without [%clk] are analyzed in full."""
    secs = clock_seconds(comment)
    return secs is not None and secs < cfg.min_clock_seconds


def _clock_bucket(secs: Optional[float]) -> str:
    """Classify clock time into buckets.
    None -> "no_clock"; secs < 60 -> "fast"; 60 <= secs < 180 -> "normal"; secs >= 180 -> "slow"."""
    if secs is None:
        return "no_clock"
    if secs < 60:
        return "fast"
    if secs < 180:
        return "normal"
    return "slow"


def aggregate_phase_clock(games_to_process, findings,
                          cfg: metrics.TrainingConfig = metrics.DEFAULT_CONFIG):
    """Pure. Returns (by_phase, by_clock), each
    {bucket: {"moves","blind","missed","blind_rate"}}, computed over the user's
    NON-time-scramble decision nodes (the analyzed population). No engine, no I/O."""
    def _get_game_idx(f: dict) -> Optional[int]:
        if "game_idx" in f:
            return f["game_idx"]
        if "id" in f and isinstance(f["id"], str) and f["id"].startswith("g"):
            try:
                return int(f["id"].split("-")[0][1:])
            except ValueError:
                pass
        return None

    blind_keys = {
        (_get_game_idx(f), f["ply"])
        for f in findings
        if f.get("severity") == "blind" and _get_game_idx(f) is not None and "ply" in f
    }
    missed_keys = {
        (_get_game_idx(f), f["ply"])
        for f in findings
        if f.get("severity") == "missed" and _get_game_idx(f) is not None and "ply" in f
    }

    by_phase = {
        "opening": {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0},
        "middlegame": {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0},
        "endgame": {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0},
    }
    by_clock = {
        "fast": {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0},
        "normal": {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0},
        "slow": {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0},
        "no_clock": {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0},
    }

    for game_idx, (game, user_color) in enumerate(games_to_process):
        board = game.board()
        ply = 0
        increment = metrics.parse_increment(game.headers.get("TimeControl"))
        prev_user_clock = None
        for node in game.mainline():
            ply += 1
            if board.turn == user_color:
                clock = clock_seconds(node.comment)
                reflex = metrics.is_reflex_move(prev_user_clock, clock, increment, cfg)
                prev_user_clock = clock
                if not reflex and not is_time_scramble(node.comment, cfg):
                    phase = metrics.classify_phase(board)
                    bucket = _clock_bucket(clock)

                    if phase not in by_phase:
                        by_phase[phase] = {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0}
                    if bucket not in by_clock:
                        by_clock[bucket] = {"moves": 0, "blind": 0, "missed": 0, "blind_rate": 0.0}

                    by_phase[phase]["moves"] += 1
                    by_clock[bucket]["moves"] += 1

                    key = (game_idx, ply)
                    if key in blind_keys:
                        by_phase[phase]["blind"] += 1
                        by_clock[bucket]["blind"] += 1
                    if key in missed_keys:
                        by_phase[phase]["missed"] += 1
                        by_clock[bucket]["missed"] += 1

            board.push(node.move)

    for d in (by_phase, by_clock):
        for b_data in d.values():
            moves = b_data["moves"]
            b_data["blind_rate"] = b_data["blind"] / moves if moves > 0 else 0.0

    return by_phase, by_clock



def _progress(job_id: str, **prog):
    """Best-effort progress ping. Progress is cosmetic — a locked job file
    (antivirus scan, concurrent poll) must never abort a multi-hour run.
    Status transitions still go through store.update_job directly and raise."""
    try:
        store.update_job(job_id, progress=prog)
    except OSError:
        pass

async def run_diagnosis(job_id: str, pgn_text: str, player_name: str, engine, vision):
    try:
        store.update_job(job_id, status="running")
        
        policy_cache = store.EpdCache("policy")
        stage_b_cache = store.EpdCache("stage_b")
        steer_cache = store.EpdCache("steer")
        
        pgn_io = io.StringIO(pgn_text)
        games_to_process = []
        all_players = set()
        
        # 1. Split multi-game PGN
        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break
                
            white = game.headers.get("White", "")
            black = game.headers.get("Black", "")
            
            if white and white != "?": all_players.add(white)
            if black and black != "?": all_players.add(black)
            
            user_color = None
            if player_name.lower() in white.lower():
                user_color = chess.WHITE
            elif player_name.lower() in black.lower():
                user_color = chess.BLACK
                
            if user_color is not None:
                games_to_process.append((game, user_color))

        if not games_to_process:
            players_str = ", ".join(sorted(list(all_players))) if all_players else "None"
            store.update_job(job_id, status="error", error=f"No games matched player '{player_name}'. Players in this PGN: {players_str}")
            return
                
        cfg = metrics.DEFAULT_CONFIG
        user_moves_count = 0
        decisions_count = 0
        reflex_skipped_count = 0
        for game, color in games_to_process:
            board = game.board()
            increment = metrics.parse_increment(game.headers.get("TimeControl"))
            prev_user_clock = None
            for node in game.mainline():
                if board.turn == color:
                    clock = clock_seconds(node.comment)
                    reflex = metrics.is_reflex_move(prev_user_clock, clock, increment, cfg)
                    prev_user_clock = clock
                    user_moves_count += 1
                    if reflex:
                        reflex_skipped_count += 1
                    else:
                        decisions_count += 1
                board.push(node.move)

        _progress(job_id, total=user_moves_count,
                  moves_analyzed=user_moves_count,
                  decisions=decisions_count,
                  reflex_skipped=reflex_skipped_count,
                  time_scramble_skipped=0)
        
        findings = []
        moves_processed = 0
        flagged_count = 0
        games_analyzed = len(games_to_process)
        
        flagged_moves = []
        user_decision_nodes = []
        
        # STAGE A (Policy Source: LC0Engine.get_policy_distribution — defines the blindness metric)
        pbar_a = tqdm(total=user_moves_count, desc="Stage A: Policy Screen", unit="move")
        for game_idx, (game, user_color) in enumerate(games_to_process):
            board = game.board()
            ply = 0
            uci_moves = []
            increment = metrics.parse_increment(game.headers.get("TimeControl"))
            prev_user_clock = None

            for node in game.mainline():
                move = node.move
                ply += 1
                uci_moves.append(move.uci())

                if board.turn == user_color:
                    clock = clock_seconds(node.comment)
                    reflex = metrics.is_reflex_move(prev_user_clock, clock, increment, cfg)
                    prev_user_clock = clock

                    epd = board.epd()

                    if board.move_stack:
                        setup_uci = board.peek().uci()
                        tmp_b = board.copy()
                        tmp_b.pop()
                        pre_fen = tmp_b.fen()
                    else:
                        setup_uci = None
                        pre_fen = None

                    policy_data = policy_cache.get(epd)
                    if policy_data is None:
                        dist = await engine.get_policy_distribution(board.fen(), nodes=1)
                        if not dist:
                            raise Exception("engine in mock mode")
                        policy_data = {"policy": dist}
                        policy_cache.put(epd, policy_data)

                    policy = policy_data["policy"]
                    div = metrics.policy_divergence(policy, metrics.policy_uci(board, move))

                    # Stage B confirmations and TS2 steering run ONLY on non-reflex decisions
                    if not reflex:
                        if div and div["severity"] is not None:
                            flagged_moves.append({
                                "game_idx": game_idx,
                                "game": game,
                                "user_color": "white" if user_color == chess.WHITE else "black",
                                "ply": ply,
                                "move_number": (ply + 1) // 2,
                                "fen_before": board.fen(),
                                "setup_uci": setup_uci,
                                "pre_fen": pre_fen,
                                "epd": epd,
                                "played_move": move,
                                "played_uci": move.uci(),
                                "played_san": board.san(move),
                                "best_uci": div["best_uci"],
                                "best_san": div["best_san"],
                                "p_played": div["p_played"],
                                "p_best": div["p_best"],
                                "divergence": div["divergence"],
                                "severity": div["severity"],
                                "uci_moves_so_far": list(uci_moves)
                            })
                            flagged_count += 1

                        user_decision_nodes.append({
                            "game_idx": game_idx,
                            "game": game,
                            "ply": ply,
                            "user_color": user_color,
                            "fen_before": board.fen(),
                            "epd": epd,
                            "uci_moves_so_far": list(uci_moves)
                        })

                    moves_processed += 1
                    pbar_a.update(1)
                    if moves_processed % 20 == 0:
                        _progress(job_id, stage_a_done=moves_processed, flagged=flagged_count)

                board.push(move)

        pbar_a.close()
        _progress(job_id, stage_a_done=moves_processed, flagged=flagged_count)

        # STAGE B (Parallelized across positions with bounded concurrency = engine.n)
        stage_b_done = 0
        opening_sidelines_excluded = 0
        pbar_b = tqdm(total=len(flagged_moves), desc="Stage B: Deep Confirmation", unit="candidate")
        _progress(job_id, stage_b_total=len(flagged_moves))

        concurrency_limit = max(1, int(getattr(engine, "n", 1)))

        # Pre-batch saliency calculations for uncached Stage B positions
        uncached_stage_b = [f for f in flagged_moves if stage_b_cache.get(f["epd"]) is None]
        if uncached_stage_b:
            uncached_fens = [f["fen_before"] for f in uncached_stage_b]
            if hasattr(vision, "saliency_absolute_batch"):
                saliency_batch = vision.saliency_absolute_batch(uncached_fens)
            else:
                saliency_batch = [vision.saliency_absolute(fen) for fen in uncached_fens]
            for f_item, sal in zip(uncached_stage_b, saliency_batch):
                f_item["_precomputed_saliency"] = sal

        b_sem = asyncio.Semaphore(concurrency_limit)
        in_flight_b: dict[str, asyncio.Future] = {}

        async def _process_flagged_move(idx: int, flagged: dict):
            nonlocal stage_b_done
            epd = flagged["epd"]
            board_before = chess.Board(flagged["fen_before"])
            played_move = flagged["played_move"]

            b_data = stage_b_cache.get(epd)
            if b_data is None:
                if epd in in_flight_b:
                    b_data = await in_flight_b[epd]
                else:
                    fut = asyncio.get_running_loop().create_future()
                    in_flight_b[epd] = fut
                    try:
                        async with b_sem:
                            b_data_new = {}
                            analysis_before = await engine.analyze(
                                flagged["fen_before"], depth=None, multipv=2,
                                time_limit=metrics.DEFAULT_CONFIG.confirm_best_seconds,
                                nodes=metrics.DEFAULT_CONFIG.confirm_best_nodes)
                            b_data_new["eval_best_cp"] = analysis_before["evaluation"]
                            b_data_new["pv_lines"] = analysis_before["pv_lines"]

                            board_after = board_before.copy()
                            board_after.push(played_move)
                            analysis_after = await engine.analyze(
                                board_after.fen(), depth=None, multipv=1,
                                time_limit=metrics.DEFAULT_CONFIG.confirm_played_seconds,
                                nodes=metrics.DEFAULT_CONFIG.confirm_played_nodes)
                            b_data_new["eval_played_cp"] = analysis_after["evaluation"]

                            saliency = flagged.get("_precomputed_saliency") or vision.saliency_absolute(flagged["fen_before"])
                            b_data_new["saliency"] = saliency

                            mover_is_white = (flagged["user_color"] == "white")
                            eval_best_cp = analysis_before.get("evaluation")
                            if eval_best_cp is None:
                                eval_best_cp = 0
                            cp_mover = eval_best_cp if mover_is_white else -eval_best_cp

                            pv_san_list = analysis_before["pv_lines"][0].split() if analysis_before.get("pv_lines") else []
                            b_data_new["pv_san_list"] = pv_san_list
                            b_data_new["motifs"] = list(
                                MotifDetector.analyze_pv(
                                    flagged.get("pre_fen"),
                                    flagged.get("setup_uci"),
                                    pv_san_list,
                                    cp_mover,
                                )
                            )
                            b_data_new["concepts"] = analyze_position(flagged["fen_before"], analysis_before)

                            stage_b_cache.put(epd, b_data_new)
                            b_data = b_data_new
                            fut.set_result(b_data)
                    except Exception as exc:
                        fut.set_exception(exc)
                        raise
                    finally:
                        if not fut.done():
                            fut.cancel()
                        in_flight_b.pop(epd, None)

            mover_is_white = (flagged["user_color"] == "white")
            conf = metrics.confirmation_swing(b_data["eval_best_cp"], b_data["eval_played_cp"], mover_is_white)
            if not conf:
                conf = {"swing_cp": 0, "confirmed": False}

            is_excluded = not metrics.is_opening_mistake(flagged["ply"], flagged["severity"], conf.get("swing_cp"))

            finding = None
            if not is_excluded:
                best_move = board_before.parse_uci(flagged["best_uci"])
                att = metrics.attention_blindness(b_data["saliency"], board_before, played_move, best_move)

                opening_match = openings.classify(flagged["uci_moves_so_far"])
                if opening_match:
                    opening_data = {"eco": opening_match["eco"], "name": opening_match["name"]}
                else:
                    opening_data = {"eco": "???", "name": "Unknown"}

                finding_id = f"g{flagged['game_idx']:03d}-p{flagged['ply']:03d}"
                headers = flagged["game"].headers

                finding = {
                    "id": finding_id,
                    "game": {
                        "white": headers.get("White", "?"),
                        "black": headers.get("Black", "?"),
                        "date": headers.get("Date", "?"),
                        "result": headers.get("Result", "?")
                    },
                    "user_color": flagged["user_color"],
                    "ply": flagged["ply"],
                    "move_number": flagged["move_number"],
                    "fen_before": flagged["fen_before"],
                    "setup_uci": flagged.get("setup_uci"),
                    "pre_fen": flagged.get("pre_fen"),
                    "played": {"uci": flagged["played_uci"], "san": flagged["played_san"], "p": flagged["p_played"]},
                    "best": {"uci": flagged["best_uci"], "san": flagged["best_san"], "p": flagged["p_best"]},
                    "divergence": flagged["divergence"],
                    "severity": flagged["severity"],
                    "attention": att,
                    "confirmation": conf,
                    "motifs": b_data["motifs"],
                    "concepts": [obs["category"] for obs in b_data["concepts"].get("observations", [])] if isinstance(b_data["concepts"], dict) else [],
                    "opening": opening_data,
                    "pv_san": b_data["pv_san_list"]
                }

            stage_b_done += 1
            pbar_b.update(1)
            _progress(job_id, stage_b_done=stage_b_done)

            return idx, finding, is_excluded

        if flagged_moves:
            b_results = await asyncio.gather(*[_process_flagged_move(i, f) for i, f in enumerate(flagged_moves)])
            b_results.sort(key=lambda x: x[0])
            for _, f_item, is_ex in b_results:
                if is_ex:
                    opening_sidelines_excluded += 1
                if f_item is not None:
                    findings.append(f_item)

        pbar_b.close()

        # STAGE TS2: Steering Pass (Parallelized with bounded concurrency = engine.n)
        steer_findings = []
        by_opening_steer = defaultdict(lambda: {"moves": 0, "complexity_sum": 0.0, "sharp_moves": 0})
        bt3_budget_remaining = metrics.DEFAULT_CONFIG.steer_bt3_budget
        steer_processed = 0
        search_used = 0
        steer_budget_exhausted = False
        steer_search_budget = int(os.environ.get("STEER_SEARCH_BUDGET", str(metrics.DEFAULT_CONFIG.steer_search_budget)))

        ts2_sem = asyncio.Semaphore(concurrency_limit)
        in_flight_steer: dict[str, asyncio.Future] = {}

        # Synchronous budget reservation helpers (Trap #1 & #4)
        def try_reserve_search() -> bool:
            nonlocal search_used, steer_budget_exhausted
            if steer_budget_exhausted or search_used >= steer_search_budget:
                steer_budget_exhausted = True
                return False
            search_used += 1
            return True

        def refund_search():
            nonlocal search_used
            search_used -= 1

        def try_reserve_bt3_saliency() -> bool:
            nonlocal bt3_budget_remaining
            if bt3_budget_remaining > 0:
                bt3_budget_remaining -= 1
                return True
            return False

        def try_reserve_bt3_saliency_batch(n_needed: int) -> int:
            nonlocal bt3_budget_remaining
            take = min(n_needed, max(0, bt3_budget_remaining))
            bt3_budget_remaining -= take
            return take

        pbar_ts2 = tqdm(total=len(user_decision_nodes), desc="Stage TS2: Tactical Steering", unit="node")
        _progress(job_id, stage_steer_total=len(user_decision_nodes))

        async def _process_steer_node(node_idx: int, node: dict):
            async with ts2_sem:
                nonlocal steer_processed, steer_budget_exhausted
                epd = node["epd"]
                fen_before = node["fen_before"]
                user_color = node["user_color"]
                board_before = chess.Board(fen_before)

                policy_data = policy_cache.get(epd)
                if not policy_data or not policy_data.get("policy"):
                    steer_processed += 1
                    pbar_ts2.update(1)
                    if steer_processed % 10 == 0:
                        _progress(job_id, stage_steer_done=steer_processed)
                    return node_idx, None, None, False, 0.0, False

                policy = policy_data["policy"]
                top_k = metrics.DEFAULT_CONFIG.steer_top_k
                top_moves = policy[:top_k]

                cand_infos = []
                for p_entry in top_moves:
                    uci = p_entry.get("uci")
                    try:
                        move = board_before.parse_uci(uci)
                    except ValueError:
                        continue
                    board_after = board_before.copy(stack=False)
                    board_after.push(move)
                    cand_infos.append({
                        "p_entry": p_entry, "uci": uci,
                        "fen_after": board_after.fen(), "epd_after": board_after.epd(),
                    })

                has_batch = hasattr(vision, "saliency_absolute_batch")
                sal_map = {}
                if has_batch and bt3_budget_remaining > 0:
                    uncached = [c for c in cand_infos if steer_cache.get(c["epd_after"]) is None]
                    n_take = try_reserve_bt3_saliency_batch(len(uncached))
                    take = uncached[:n_take]
                    if take:
                        sals = vision.saliency_absolute_batch([c["fen_after"] for c in take])
                        for c, s in zip(take, sals):
                            sal_map[c["epd_after"]] = s

                candidates = []

                for c in cand_infos:
                    p_entry = c["p_entry"]
                    uci = c["uci"]
                    fen_after_m = c["fen_after"]
                    epd_after_m = c["epd_after"]

                    s_data = steer_cache.get(epd_after_m)
                    if not s_data:
                        if epd_after_m in in_flight_steer:
                            s_data = await in_flight_steer[epd_after_m]
                        else:
                            if not try_reserve_search():
                                break

                            fut = asyncio.get_running_loop().create_future()
                            in_flight_steer[epd_after_m] = fut
                            try:
                                try:
                                    analysis = await engine.analyze(
                                        fen_after_m, depth=None, multipv=2,
                                        time_limit=metrics.DEFAULT_CONFIG.confirm_played_seconds,
                                        nodes=metrics.DEFAULT_CONFIG.confirm_played_nodes)
                                    if not analysis:
                                        raise Exception("engine in mock mode")
                                    pol_after = await engine.get_policy_distribution(fen_after_m, nodes=1)
                                except Exception as exc:
                                    refund_search()
                                    raise exc

                                if has_batch:
                                    saliency = sal_map.get(epd_after_m)
                                else:
                                    if try_reserve_bt3_saliency():
                                        saliency = vision.saliency_absolute(fen_after_m)
                                    else:
                                        saliency = None

                                s_data = {"analysis": analysis, "policy": pol_after, "saliency": saliency}
                                steer_cache.put(epd_after_m, s_data)
                                fut.set_result(s_data)
                            except Exception as exc:
                                fut.set_exception(exc)
                                raise
                            finally:
                                if not fut.done():
                                    fut.cancel()
                                in_flight_steer.pop(epd_after_m, None)

                    if not s_data:
                        break

                    analysis_after = s_data["analysis"]
                    policy_after = s_data["policy"]
                    saliency = s_data.get("saliency")

                    complexity = metrics.tactical_complexity(analysis_after, policy_after, saliency)

                    cp_eval = metrics.eval_cp_number(analysis_after.get("evaluation"))
                    if cp_eval is None:
                        continue

                    eval_cp_mover = cp_eval if user_color == chess.WHITE else -cp_eval

                    candidates.append({
                        "uci": uci,
                        "san": p_entry.get("san"),
                        "eval_cp": eval_cp_mover,
                        "complexity": complexity["score"],
                        "components": complexity
                    })

                opening_match_all = openings.classify(node["uci_moves_so_far"])
                eco_all = opening_match_all["eco"] if opening_match_all else "???"

                steer_finding = None
                had_sharp_move = False
                obj_best_complexity = 0.0

                if candidates:
                    best_eval_cp = max(c["eval_cp"] for c in candidates)
                    steer_res = metrics.steer_candidates(candidates, best_eval_cp)

                    if steer_res["had_sharp_move"] or (steer_res["objective_best"] and steer_res["objective_best"]["complexity"] >= metrics.DEFAULT_CONFIG.steer_highlight_complexity):
                        best_c = steer_res["objective_best"]
                        sharp_c = steer_res["sharp_move"]

                        steer_finding = {
                            "id": f"s-{node['game_idx']:03d}-p{node['ply']:03d}",
                            "game": {
                                "white": node["game"].headers.get("White", "?"),
                                "black": node["game"].headers.get("Black", "?"),
                                "date": node["game"].headers.get("Date", "?")
                            },
                            "ply": node["ply"],
                            "fen_before": fen_before,
                            "best": {"uci": best_c["uci"], "san": best_c["san"], "eval_cp": best_c["eval_cp"], "complexity": best_c["complexity"], "components": best_c["components"]},
                            "steer": {"uci": sharp_c["uci"], "san": sharp_c["san"], "eval_cp": sharp_c["eval_cp"], "complexity": sharp_c["complexity"], "components": sharp_c["components"]} if sharp_c else {"uci": best_c["uci"], "san": best_c["san"], "eval_cp": best_c["eval_cp"], "complexity": best_c["complexity"], "components": best_c["components"]},
                            "playable_candidates": [{"uci": c["uci"], "complexity": c["complexity"], "eval_cp": c["eval_cp"]} for c in steer_res["playable"]],
                            "eval_loss_cp": best_eval_cp - (sharp_c["eval_cp"] if sharp_c else best_eval_cp),
                            "had_sharp_move": steer_res["had_sharp_move"],
                            "opening": {"eco": eco_all}
                        }
                        had_sharp_move = steer_res["had_sharp_move"]

                    if steer_res["objective_best"]:
                        obj_best_complexity = steer_res["objective_best"]["complexity"]

                steer_processed += 1
                pbar_ts2.update(1)
                if steer_processed % 10 == 0:
                    _progress(job_id, stage_steer_done=steer_processed)

                return node_idx, steer_finding, eco_all, had_sharp_move, obj_best_complexity, bool(candidates)

        if user_decision_nodes:
            ts2_results = await asyncio.gather(*[_process_steer_node(i, n) for i, n in enumerate(user_decision_nodes)])
            ts2_results.sort(key=lambda x: x[0])

            for _, s_finding, eco_all, had_sharp, obj_comp, had_cands in ts2_results:
                if s_finding is not None:
                    steer_findings.append(s_finding)
                    by_opening_steer[eco_all]["sharp_moves"] += 1 if had_sharp else 0

                if eco_all is not None:
                    by_opening_steer[eco_all]["moves"] += 1
                    if had_cands:
                        by_opening_steer[eco_all]["complexity_sum"] += obj_comp

        pbar_ts2.close()
        _progress(job_id, stage_steer_done=steer_processed, steer_search_used=search_used)

        steer_summary = {}
        for eco, st in by_opening_steer.items():
            steer_summary[eco] = {
                "moves": st["moves"],
                "sharp_moves": st["sharp_moves"],
                "mean_complexity": st["complexity_sum"] / max(1, st["moves"])
            }
            
        # Aggregate
        by_motif = defaultdict(lambda: {"missed": 0, "blind": 0, "confirmed": 0})
        by_opening = defaultdict(lambda: {"moves": 0, "moves_white": 0, "moves_black": 0, "missed": 0, "blind": 0, "blind_rate": 0.0})
        by_concept = defaultdict(lambda: {"missed": 0})
        
        intuitive_blind_count = 0
        attention_blind_count = 0
        
        for game_idx, (game, user_color) in enumerate(games_to_process):
            board = game.board()
            uci_moves = []
            increment = metrics.parse_increment(game.headers.get("TimeControl"))
            prev_user_clock = None
            for node in game.mainline():
                uci_moves.append(node.move.uci())
                if board.turn == user_color:
                    clock = clock_seconds(node.comment)
                    reflex = metrics.is_reflex_move(prev_user_clock, clock, increment, cfg)
                    prev_user_clock = clock
                    if not reflex:
                        opening_match = openings.classify(uci_moves)
                        if opening_match:
                            by_opening[opening_match["eco"]]["moves"] += 1
                            color_key = "moves_white" if user_color == chess.WHITE else "moves_black"
                            by_opening[opening_match["eco"]][color_key] += 1
                board.push(node.move)
                
        for f in findings:
            weight = 2 if f["confirmation"].get("confirmed") else 1
            sev = f["severity"]
            
            if sev == "blind":
                intuitive_blind_count += 1
            if f["attention"].get("blind"):
                attention_blind_count += 1
                
            for m in f["motifs"]:
                by_motif[m][sev] += weight
                if f["confirmation"].get("confirmed"):
                    by_motif[m]["confirmed"] += 1
                    
            eco = f["opening"]["eco"]
            by_opening[eco][sev] += 1   # unweighted: blind_rate must be a true
            #                             move fraction (<=1.0), consistent with
            #                             by_phase/by_clock (audit F2). by_motif's
            #                             weighted counts (below) are a separate,
            #                             intentional display ranking.
            
            for c in f["concepts"]:
                by_concept[c]["missed"] += weight
                
        for eco, st in by_opening.items():
            if st["moves"] > 0:
                st["blind_rate"] = st["blind"] / st["moves"]

        by_phase, by_clock = aggregate_phase_clock(games_to_process, findings, metrics.DEFAULT_CONFIG)

        aggregates = {
            "by_motif": {k: dict(v) for k, v in by_motif.items()},
            "by_opening": {k: dict(v) for k, v in by_opening.items()},
            "by_concept": {k: dict(v) for k, v in by_concept.items()},
            "by_phase": by_phase,
            "by_clock": by_clock,
            "intuitive_blindness_rate": intuitive_blind_count / max(1, moves_processed),
            "attention_blindness_rate": attention_blind_count / max(1, moves_processed)
        }
        
        profile = {
            "version": 1,
            "created": datetime.datetime.utcnow().isoformat(),
            "games_analyzed": games_analyzed,
            "moves_analyzed": moves_processed,
            "decisions": decisions_count,
            "reflex_skipped": reflex_skipped_count,
            "time_scramble_skipped": 0,
            "opening_sidelines_excluded": opening_sidelines_excluded,
            "findings": findings,
            "aggregates": aggregates,
            "steer_findings": steer_findings,
            "steer_summary": steer_summary,
            "steer_budget_exhausted": steer_budget_exhausted
        }
        
        from backend.training import attempts
        profile["regressions"] = attempts.escalate_regressions(profile)

        store.save_profile(profile)
        store.update_job(job_id, status="done")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        store.update_job(job_id, status="error", error=str(e))
