"""
Policy-Prior vs Search Harvest ("Intuition vs Calculation")

Harvests data comparing raw LC0 policy-head prior (nodes=1) vs searched best move
(nodes=20000) vs player's actual move from PGN games.

Pure data generator and reporter. No prose, no interpretations.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Union

import chess
import chess.pgn

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.engine_manager import LC0Engine
from backend.neural_vision import NeuralVision
from backend.training import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("policy_prior_harvest")

DEFAULT_PGN = ROOT_DIR / "games_of_derdiedasdie" / "lichess_derdiedasdie_2026-07-21.pgn"
DEFAULT_ENGINE = ROOT_DIR / "engine" / "lc0.exe"
DEFAULT_WEIGHTS = ROOT_DIR / "engine" / "BT3-768x15x24h-swa-2790000.pb.gz"
DEFAULT_ONNX = ROOT_DIR / "engine" / "bt3.onnx"
OUTPUT_DIR = ROOT_DIR / "data" / "policy_prior"
OUTPUT_FILE = OUTPUT_DIR / "harvest.json"


def extract_candidates(pgn_path: Path, username: str = "derdiedasdie") -> list[dict]:
    """
    Extract candidate positions from PGN where user is to move,
    ply is 16..80 inclusive, and >= 10 pieces on board.
    """
    candidates = []
    if not pgn_path.exists():
        raise FileNotFoundError(f"PGN file not found: {pgn_path}")

    with open(pgn_path, "r", encoding="utf-8", errors="replace") as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break

            headers = game.headers
            white_player = headers.get("White", "")
            black_player = headers.get("Black", "")
            site = headers.get("Site", "")

            user_color = None
            if username.lower() in white_player.lower():
                user_color = chess.WHITE
            elif username.lower() in black_player.lower():
                user_color = chess.BLACK
            else:
                continue

            board = game.board()
            ply = 0
            for move in game.mainline_moves():
                ply += 1
                if 16 <= ply <= 80 and board.turn == user_color:
                    if len(board.piece_map()) >= 10:
                        candidates.append({
                            "game_site": site,
                            "ply": ply,
                            "fen": board.fen(),
                            "user_color": "white" if user_color == chess.WHITE else "black",
                            "played_uci": move.uci(),
                            "played_san": board.san(move),
                        })
                board.push(move)
    return candidates


# A mate must outrank every possible centipawn score, and LC0's cp is not
# bounded by 10000 — this harvest observed a plain eval of 12772, which under
# the old mapping made "merely winning" score better than "forced mate" and
# produced a negative move-loss. So cp is clamped strictly below the mate band,
# and mates are graded by distance (M1 beats M5).
CP_CEILING = 9000
MATE_BASE = 10000


def parse_eval(score_val: Union[int, float, str, None]) -> int:
    """Engine score to integer centipawns, White's point of view.

    Plain evals are clamped to +-CP_CEILING. Mates map into a band above that,
    graded so a faster mate scores higher: M1 -> 9999, M5 -> 9995.
    """
    if score_val is None:
        return 0
    if isinstance(score_val, (int, float)):
        return max(-CP_CEILING, min(CP_CEILING, int(score_val)))
    if isinstance(score_val, str):
        s = score_val.strip()
        if s.startswith("M"):
            try:
                moves = int(s[1:])
            except ValueError:
                return -MATE_BASE if "-" in s else MATE_BASE
            # Distance grading, floored so a very long mate never dips into
            # the plain-cp range.
            magnitude = max(CP_CEILING + 1, MATE_BASE - abs(moves))
            return magnitude if moves >= 0 else -magnitude
        try:
            return max(-CP_CEILING, min(CP_CEILING, int(float(s))))
        except ValueError:
            return 0
    return 0


async def run_harvest(
    target_n: int = 150,
    seed: int = 20260815,
    search_nodes: int = 20000,
    prior_nodes: int = 1,
    pgn_path: Path = DEFAULT_PGN,
    engine_path: Path = DEFAULT_ENGINE,
    weights_path: Path = DEFAULT_WEIGHTS,
    output_file: Path = OUTPUT_FILE,
):
    """Harvest policy-prior vs search data with resume capability."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading candidate positions from {pgn_path}...")
    candidates = extract_candidates(pgn_path)
    print(f"Loaded {len(candidates)} candidate positions.")

    rng = random.Random(seed)
    sampled = rng.sample(candidates, k=min(target_n, len(candidates)))
    print(f"Sampled {len(sampled)} positions using seed {seed}.")

    # Load existing records if output file exists
    existing_records = []
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing_records = data.get("records", [])
        except Exception as e:
            print(f"Warning: could not read existing harvest file: {e}")
            existing_records = []

    records_dict = {(r["game_site"], r["ply"]): r for r in existing_records}
    print(f"Found {len(records_dict)} already harvested positions.")

    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT_DIR), text=True
        ).strip()
    except Exception:
        git_commit = "unknown"

    engine = LC0Engine(
        engine_path=str(engine_path),
        weights_path=str(weights_path),
    )

    try:
        await engine.start()
        print("Engine started successfully on BT3 weights.")

        start_time = time.time()
        for idx, item in enumerate(sampled):
            key = (item["game_site"], item["ply"])
            if key in records_dict:
                continue

            fen = item["fen"]
            user_color = item["user_color"]
            played_uci = item["played_uci"]
            played_san = item["played_san"]

            t0 = time.time()

            # 1. Prior distribution (nodes=1)
            prior_list = await engine.get_policy_distribution(fen, nodes=prior_nodes)
            prior_list.sort(key=lambda x: x["p"], reverse=True)

            top_10 = [
                {
                    "uci": m["uci"],
                    "san": m["san"],
                    "p": round(float(m["p"]), 4),
                    "n": int(m.get("n", 0)),
                }
                for m in prior_list[:10]
            ]

            prior_top1_uci = prior_list[0]["uci"] if prior_list else None

            # 2. Search position FEN (nodes=20000)
            search_res = await engine.analyze(fen, nodes=search_nodes)
            raw_searched_eval = search_res.get("evaluation", 0)
            searched_eval_cp_white = parse_eval(raw_searched_eval)
            searched_eval_cp = (
                searched_eval_cp_white if user_color == "white" else -searched_eval_cp_white
            )

            best_moves = search_res.get("best_moves", [])
            searched_best_uci = best_moves[0]["move"] if best_moves else None

            # Rank & p of searched best
            prior_rank_searched = None
            prior_p_searched = None
            if searched_best_uci is not None:
                for rank_idx, m in enumerate(prior_list):
                    if m["uci"] == searched_best_uci:
                        prior_rank_searched = rank_idx + 1
                        prior_p_searched = round(float(m["p"]), 4)
                        break

            # Rank & p of played move
            prior_rank_played = None
            prior_p_played = None
            for rank_idx, m in enumerate(prior_list):
                if m["uci"] == played_uci:
                    prior_rank_played = rank_idx + 1
                    prior_p_played = round(float(m["p"]), 4)
                    break

            # 3. Search position AFTER played move (nodes=20000)
            board = chess.Board(fen)
            board.push(chess.Move.from_uci(played_uci))
            fen_after = board.fen()

            if board.is_checkmate():
                played_eval_cp = 10000
            elif board.is_stalemate() or board.is_insufficient_material():
                played_eval_cp = 0
            else:
                search_after_res = await engine.analyze(fen_after, nodes=search_nodes)
                raw_played_eval = search_after_res.get("evaluation", 0)
                played_eval_cp_white = parse_eval(raw_played_eval)
                played_eval_cp = (
                    played_eval_cp_white if user_color == "white" else -played_eval_cp_white
                )

            record = {
                "game_site": item["game_site"],
                "ply": item["ply"],
                "fen": fen,
                "user_color": user_color,
                "played_uci": played_uci,
                "played_san": played_san,
                "prior": top_10,
                "prior_top1_uci": prior_top1_uci,
                "searched_best_uci": searched_best_uci,
                "searched_eval_cp": searched_eval_cp,
                "played_eval_cp": played_eval_cp,
                "prior_rank_of_searched_best": prior_rank_searched,
                "prior_p_of_searched_best": prior_p_searched,
                "prior_rank_of_played": prior_rank_played,
                "prior_p_of_played": prior_p_played,
            }

            records_dict[key] = record

            # Build ordered list preserving sample order
            current_records = [
                records_dict[(c["game_site"], c["ply"])]
                for c in sampled
                if (c["game_site"], c["ply"]) in records_dict
            ]

            out_meta = {
                "weights_file": weights_path.name,
                "prior_nodes": prior_nodes,
                "search_nodes": search_nodes,
                "target_n": target_n,
                "harvested_n": len(current_records),
                "seed": seed,
                "git_commit": git_commit,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "mate_mapping": "+-10000 cp",
            }

            payload = {
                "meta": out_meta,
                "records": current_records,
            }
            store._write_json_atomic(str(output_file), payload)

            elapsed = time.time() - t0
            print(
                f"[{len(current_records)}/{target_n}] {item['game_site']} ply {item['ply']} ({user_color}) | "
                f"elapsed: {elapsed:.2f}s | searched: {searched_best_uci} (eval: {searched_eval_cp}) | "
                f"played: {played_uci} (eval: {played_eval_cp})",
                flush=True,
            )

        total_wall_time = time.time() - start_time
        print(f"\nHarvest complete: {len(records_dict)} records written to {output_file}.")
        print(f"Total wall-clock time: {total_wall_time:.2f}s ({total_wall_time / 3600:.2f}h).")

    finally:
        await engine.stop()


def compute_metrics(records: list[dict]) -> dict:
    """Compute all 6 required metric groups without commentary."""
    total = len(records)
    if total == 0:
        return {}

    # 1. Overturn rate
    overturns = sum(1 for r in records if r["prior_top1_uci"] != r["searched_best_uci"])
    overturn_rate = overturns / total

    # 2. Rank histogram of prior_rank_of_searched_best
    rank_hist = {
        "1": 0,
        "2": 0,
        "3": 0,
        "4-5": 0,
        "6-10": 0,
        ">10": 0,
        "null": 0,
    }
    for r in records:
        rank = r.get("prior_rank_of_searched_best")
        if rank is None:
            rank_hist["null"] += 1
        elif rank == 1:
            rank_hist["1"] += 1
        elif rank == 2:
            rank_hist["2"] += 1
        elif rank == 3:
            rank_hist["3"] += 1
        elif 4 <= rank <= 5:
            rank_hist["4-5"] += 1
        elif 6 <= rank <= 10:
            rank_hist["6-10"] += 1
        else:
            rank_hist[">10"] += 1

    # 3. Prior mass on searched best
    all_p_searched = [
        r["prior_p_of_searched_best"]
        for r in records
        if r["prior_p_of_searched_best"] is not None
    ]
    overturned_p = [
        r["prior_p_of_searched_best"]
        for r in records
        if r["prior_top1_uci"] != r["searched_best_uci"]
        and r["prior_p_of_searched_best"] is not None
    ]
    retained_p = [
        r["prior_p_of_searched_best"]
        for r in records
        if r["prior_top1_uci"] == r["searched_best_uci"]
        and r["prior_p_of_searched_best"] is not None
    ]

    mean_all_p = statistics.mean(all_p_searched) if all_p_searched else 0.0
    median_all_p = statistics.median(all_p_searched) if all_p_searched else 0.0
    mean_overturned_p = statistics.mean(overturned_p) if overturned_p else 0.0
    median_overturned_p = statistics.median(overturned_p) if overturned_p else 0.0
    mean_retained_p = statistics.mean(retained_p) if retained_p else 0.0
    median_retained_p = statistics.median(retained_p) if retained_p else 0.0

    # 4. His agreement with each
    played_agree_prior = sum(1 for r in records if r["played_uci"] == r["prior_top1_uci"]) / total
    played_agree_searched = (
        sum(1 for r in records if r["played_uci"] == r["searched_best_uci"]) / total
    )

    # 5. Blunder subset (eval_loss_cp >= 100) vs non-blunder (< 100)
    blunder_records = []
    non_blunder_records = []
    for r in records:
        loss = max(0, r["searched_eval_cp"] - r["played_eval_cp"])
        if loss >= 100:
            blunder_records.append(r)
        else:
            non_blunder_records.append(r)

    blunder_n = len(blunder_records)
    blunder_agree_prior = (
        sum(1 for r in blunder_records if r["played_uci"] == r["prior_top1_uci"]) / blunder_n
        if blunder_n > 0
        else 0.0
    )
    blunder_p_played = [
        r["prior_p_of_played"] for r in blunder_records if r["prior_p_of_played"] is not None
    ]
    blunder_mean_p_played = statistics.mean(blunder_p_played) if blunder_p_played else 0.0

    non_blunder_n = len(non_blunder_records)
    non_blunder_agree_prior = (
        sum(1 for r in non_blunder_records if r["played_uci"] == r["prior_top1_uci"])
        / non_blunder_n
        if non_blunder_n > 0
        else 0.0
    )
    non_blunder_p_played = [
        r["prior_p_of_played"] for r in non_blunder_records if r["prior_p_of_played"] is not None
    ]
    non_blunder_mean_p_played = (
        statistics.mean(non_blunder_p_played) if non_blunder_p_played else 0.0
    )

    # 6. Sanity counts
    null_ranks_searched = rank_hist["null"]
    null_ranks_played = sum(1 for r in records if r.get("prior_rank_of_played") is None)

    return {
        "total": total,
        "overturns": overturns,
        "overturn_rate": overturn_rate,
        "rank_hist": rank_hist,
        "mean_all_p": mean_all_p,
        "median_all_p": median_all_p,
        "mean_overturned_p": mean_overturned_p,
        "median_overturned_p": median_overturned_p,
        "mean_retained_p": mean_retained_p,
        "median_retained_p": median_retained_p,
        "played_agree_prior": played_agree_prior,
        "played_agree_searched": played_agree_searched,
        "blunder_n": blunder_n,
        "blunder_agree_prior": blunder_agree_prior,
        "blunder_mean_p_played": blunder_mean_p_played,
        "non_blunder_n": non_blunder_n,
        "non_blunder_agree_prior": non_blunder_agree_prior,
        "non_blunder_mean_p_played": non_blunder_mean_p_played,
        "null_ranks_searched": null_ranks_searched,
        "null_ranks_played": null_ranks_played,
    }


def print_report(output_file: Path = OUTPUT_FILE):
    """Print the 6 metric tables and 5 spot-check JSON records."""
    if not output_file.exists():
        print(f"Error: Output file not found at {output_file}")
        return

    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    records = data.get("records", [])

    print("================================================================================")
    print("                      POLICY-PRIOR VS SEARCH HARVEST REPORT                     ")
    print("================================================================================")
    print(f"Weights file      : {meta.get('weights_file', 'unknown')}")
    print(f"Prior nodes       : {meta.get('prior_nodes', 'unknown')}")
    print(f"Search nodes      : {meta.get('search_nodes', 'unknown')}")
    print(f"Sample seed       : {meta.get('seed', 'unknown')}")
    print(f"Target N          : {meta.get('target_n', 'unknown')}")
    print(f"Harvested N       : {len(records)}")
    print(f"Git commit        : {meta.get('git_commit', 'unknown')}")
    print(f"Timestamp         : {meta.get('timestamp', 'unknown')}")
    print(f"Mate mapping      : {meta.get('mate_mapping', 'unknown')}")
    print("================================================================================\n")

    m = compute_metrics(records)
    if not m:
        print("No records found to compute metrics.")
        return

    # Table 1: Overturn Rate
    print("1. OVERTURN RATE")
    print("--------------------------------------------------------------------------------")
    print(f"Total positions   : {m['total']}")
    print(f"Overturned (prior != searched): {m['overturns']}")
    print(f"Overturn rate     : {m['overturn_rate']:.4f} ({m['overturn_rate'] * 100:.2f}%)")
    print("--------------------------------------------------------------------------------\n")

    # Table 2: Rank Histogram of Searched Best Move
    print("2. RANK HISTOGRAM (prior rank of searched best move)")
    print("--------------------------------------------------------------------------------")
    print(f"{'Rank Category':<15} | {'Count':<8} | {'Fraction':<10}")
    print("--------------------------------------------------------------------------------")
    for cat, count in m["rank_hist"].items():
        pct = (count / m["total"]) * 100 if m["total"] > 0 else 0.0
        print(f"{cat:<15} | {count:<8} | {pct:.2f}%")
    print("--------------------------------------------------------------------------------\n")

    # Table 3: Prior Mass on Searched Best Move
    print("3. PRIOR MASS ON SEARCHED BEST MOVE")
    print("--------------------------------------------------------------------------------")
    print(f"{'Subset':<20} | {'Mean prior p':<15} | {'Median prior p':<15}")
    print("--------------------------------------------------------------------------------")
    print(f"{'All positions':<20} | {m['mean_all_p']:<15.4f} | {m['median_all_p']:<15.4f}")
    print(f"{'Overturned':<20} | {m['mean_overturned_p']:<15.4f} | {m['median_overturned_p']:<15.4f}")
    print(f"{'Retained':<20} | {m['mean_retained_p']:<15.4f} | {m['median_retained_p']:<15.4f}")
    print("--------------------------------------------------------------------------------\n")

    # Table 4: Agreement with Player
    print("4. PLAYER AGREEMENT")
    print("--------------------------------------------------------------------------------")
    print(f"Agreement with Prior Top-1 (played == prior_top1)   : {m['played_agree_prior']:.4f} ({m['played_agree_prior'] * 100:.2f}%)")
    print(f"Agreement with Searched Best (played == searched_best): {m['played_agree_searched']:.4f} ({m['played_agree_searched'] * 100:.2f}%)")
    print("--------------------------------------------------------------------------------\n")

    # Table 5: Blunder Subset vs Non-Blunder Subset
    print("5. BLUNDER SUBSET VS NON-BLUNDER SUBSET (eval_loss_cp >= 100)")
    print("--------------------------------------------------------------------------------")
    print(f"{'Subset':<18} | {'N':<6} | {'Agree Prior Top-1':<20} | {'Mean Prior p of Played':<22}")
    print("--------------------------------------------------------------------------------")
    print(f"{'Blunders (>=100)':<18} | {m['blunder_n']:<6} | {m['blunder_agree_prior'] * 100:<19.2f}% | {m['blunder_mean_p_played']:<22.4f}")
    print(f"{'Non-Blunders':<18} | {m['non_blunder_n']:<6} | {m['non_blunder_agree_prior'] * 100:<19.2f}% | {m['non_blunder_mean_p_played']:<22.4f}")
    print("--------------------------------------------------------------------------------\n")

    # Table 6: Sanity Counts
    print("6. SANITY COUNTS")
    print("--------------------------------------------------------------------------------")
    print(f"Positions harvested                 : {m['total']}")
    print(f"Null ranks for searched best move   : {m['null_ranks_searched']}")
    print(f"Null ranks for played move          : {m['null_ranks_played']}")
    print("================================================================================\n")

    # 5 Sample Raw JSON Records
    print("5 SAMPLE RAW JSON RECORDS (deterministic seed 20260815):")
    print("--------------------------------------------------------------------------------")
    rng = random.Random(20260815)
    sample_size = min(5, len(records))
    samples = rng.sample(records, k=sample_size)
    for idx, sample in enumerate(samples, 1):
        print(f"\n--- Sample Record #{idx} ---")
        print(json.dumps(sample, indent=2))
    print("================================================================================")


async def run_cross_check(
    output_file: Path = OUTPUT_FILE,
    engine_path: Path = DEFAULT_ENGINE,
    weights_path: Path = DEFAULT_WEIGHTS,
    onnx_path: Path = DEFAULT_ONNX,
    n_check: int = 20,
):
    """Checkpoint 5: Cross-check engine policy against ONNX NeuralVision.evaluate_batch."""
    if not output_file.exists():
        print(f"Error: harvest file {output_file} not found. Run harvest first.")
        return

    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    if not records:
        print("No records found.")
        return

    check_records = records[:n_check]
    fens = [r["fen"] for r in check_records]

    print(f"Running ONNX evaluate_batch on {len(fens)} positions...")
    nv = NeuralVision(onnx_path=str(onnx_path))
    onnx_results = nv.evaluate_batch(fens)

    print(f"Starting engine for BT3 prior extraction on {len(fens)} positions...")
    engine = LC0Engine(
        engine_path=str(engine_path),
        weights_path=str(weights_path),
    )

    engine_priors = []
    try:
        await engine.start()
        for idx, fen in enumerate(fens, 1):
            prior_list = await engine.get_policy_distribution(fen, nodes=1)
            prior_list.sort(key=lambda x: x["p"], reverse=True)
            engine_priors.append(prior_list)
    finally:
        await engine.stop()

    print("\n================================================================================")
    print("           CHECKPOINT 5: ONNX VS LC0 ENGINE POLICY CROSS-CHECK                  ")
    print("================================================================================")

    top1_agreements = 0
    anomalies = []

    for i, (fen, rec, eng_p, onnx_res) in enumerate(
        zip(fens, check_records, engine_priors, onnx_results), 1
    ):
        eng_top3 = eng_p[:3]
        eng_top3_str = ", ".join(f"{m['uci']}:{m['p']:.3f}" for m in eng_top3)

        onnx_p = onnx_res.get("policy", [])
        onnx_top3 = onnx_p[:3]
        onnx_top3_str = ", ".join(f"{m['uci']}:{m['p']:.3f}" for m in onnx_top3)

        val = onnx_res.get("value", 0.0)
        wdl = onnx_res.get("wdl", [0.0, 0.0, 0.0])

        eng_top1 = eng_top3[0]["uci"] if eng_top3 else None
        onnx_top1 = onnx_top3[0]["uci"] if onnx_top3 else None

        agree = eng_top1 == onnx_top1
        if agree:
            top1_agreements += 1

        max_onnx_p = onnx_top3[0]["p"] if onnx_top3 else 0.0
        is_extreme_wdl = wdl in ([0, 0, 1], [1, 0, 0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0])
        is_flat_policy = max_onnx_p < 0.05

        if is_extreme_wdl or is_flat_policy:
            anomalies.append({
                "index": i,
                "fen": fen,
                "wdl": wdl,
                "value": val,
                "max_p": max_onnx_p,
            })

        print(f"[{i:02d}] FEN: {fen}")
        print(f"     LC0 Prior Top-3 : {eng_top3_str}")
        print(f"     ONNX Prior Top-3: {onnx_top3_str} | value: {val:+.3f} | wdl: {wdl}")
        print(f"     Top-1 Match     : {'YES' if agree else 'NO (LC0=' + str(eng_top1) + ', ONNX=' + str(onnx_top1) + ')'}\n")

    print("--------------------------------------------------------------------------------")
    print(f"Top-1 Agreement: {top1_agreements}/{len(fens)} ({top1_agreements / len(fens) * 100:.1f}%)")
    print(f"Extreme WDL / Flat Policy Anomalies (wdl in [[0,0,1],[1,0,0]] or max_p < 0.05): {len(anomalies)}")
    for a in anomalies:
        print(f"  - Pos #{a['index']}: FEN={a['fen']} | wdl={a['wdl']} | val={a['value']} | max_p={a['max_p']:.4f}")
    print("================================================================================\n")


def main():
    parser = argparse.ArgumentParser(description="Policy-Prior vs Search Harvest")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # harvest subcommand
    harvest_parser = subparsers.add_parser("harvest", help="Run policy-prior vs search harvest")
    harvest_parser.add_argument("--n", type=int, default=150, help="Target number of positions (default 150)")
    harvest_parser.add_argument("--seed", type=int, default=20260815, help="Sampling seed (default 20260815)")
    harvest_parser.add_argument("--search-nodes", type=int, default=20000, help="Search node limit (default 20000)")
    harvest_parser.add_argument("--prior-nodes", type=int, default=1, help="Prior node limit (default 1)")
    harvest_parser.add_argument("--pgn", type=Path, default=DEFAULT_PGN, help="PGN file path")
    harvest_parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS, help="Weights path")
    harvest_parser.add_argument("--output", type=Path, default=OUTPUT_FILE, help="Output JSON path")

    # report subcommand
    report_parser = subparsers.add_parser("report", help="Generate metrics report from harvest file")
    report_parser.add_argument("--output", type=Path, default=OUTPUT_FILE, help="Harvest JSON path")

    # cross_check subcommand
    cross_parser = subparsers.add_parser("cross_check", help="Cross-check LC0 vs ONNX policy")
    cross_parser.add_argument("--output", type=Path, default=OUTPUT_FILE, help="Harvest JSON path")
    cross_parser.add_argument("--n", type=int, default=20, help="Number of positions to check (default 20)")
    cross_parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS, help="Weights path")
    cross_parser.add_argument("--onnx", type=Path, default=DEFAULT_ONNX, help="ONNX path")

    args = parser.parse_args()

    if args.command == "harvest":
        asyncio.run(
            run_harvest(
                target_n=args.n,
                seed=args.seed,
                search_nodes=args.search_nodes,
                prior_nodes=args.prior_nodes,
                pgn_path=args.pgn,
                weights_path=args.weights,
                output_file=args.output,
            )
        )
    elif args.command == "report":
        print_report(output_file=args.output)
    elif args.command == "cross_check":
        asyncio.run(
            run_cross_check(
                output_file=args.output,
                weights_path=args.weights,
                onnx_path=args.onnx,
                n_check=args.n,
            )
        )


if __name__ == "__main__":
    main()
