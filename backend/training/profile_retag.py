from __future__ import annotations

import copy
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import chess
import chess.pgn

from backend.tactics import MotifDetector
from backend.training import eco_backfill

logger = logging.getLogger("chess_speak_out_loud")

EVAL_TIER_TAGS = {"crushing", "advantage", "equality"}


def retag_profile(
    profile: Dict[str, Any], pgn_path: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Re-tag a stored profile offline using corrected MotifDetector.analyze_pv.

    Pure function: input profile dict in, new retagged dict out (no disk I/O).

    1. Backfills pre_fen and setup_uci for each finding by matching fen_before against PGN game plies.
    2. Re-runs MotifDetector.analyze_pv(pre_fen, setup_uci, pv_san, cp=0).
    3. Strips unrecoverable eval-tier tags {"crushing", "advantage", "equality"}.
    4. Recomputes aggregates["by_motif"].
    5. Migrates steer keys (had_tal_move -> had_sharp_move, tal_move -> sharp_move, tal_moves -> sharp_moves).

    Returns (retagged_profile, report_summary).
    """
    retagged = copy.deepcopy(profile)
    player_name = str(retagged.get("player_name", "derdiedasdie")).lower()
    games_analyzed = retagged.get("games_analyzed", 0)

    # 1. Build game_map & fast FEN lookup table from PGN corpus
    games_to_process: List[Tuple[chess.pgn.Game, str]] = []
    if os.path.exists(pgn_path):
        with open(pgn_path, "r", encoding="utf-8", errors="replace") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                white = game.headers.get("White", "").lower()
                black = game.headers.get("Black", "").lower()
                user_color = None
                if player_name in white:
                    user_color = "white"
                elif player_name in black:
                    user_color = "black"
                if user_color is not None:
                    games_to_process.append((game, user_color))
                    if games_analyzed > 0 and len(games_to_process) >= games_analyzed:
                        break

    game_map: Dict[int, Dict[str, Any]] = {}
    fen_lookup: Dict[Tuple[int, str, bool], Tuple[str, str]] = {}
    header_game_map: Dict[Tuple[str, str, str], int] = {}

    for idx, (game, color) in enumerate(games_to_process):
        gw = game.headers.get("White", "").strip().lower()
        gb = game.headers.get("Black", "").strip().lower()
        gd = game.headers.get("Date", "").strip()
        header_game_map[(gw, gb, gd)] = idx

        board = game.board()
        uci_moves = []
        for node in game.mainline():
            pre_fen_candidate = board.fen()
            move_uci = node.move.uci()
            uci_moves.append(move_uci)
            board.push(node.move)
            # Map (game_idx, board_fen, turn) -> (pre_fen, setup_uci)
            fen_lookup[(idx, board.board_fen(), board.turn)] = (pre_fen_candidate, move_uci)

        game_map[idx] = {
            "game": game,
            "user_color": color,
            "uci_moves": uci_moves,
        }

    def find_game_idx_by_headers(item_game_headers: dict) -> Optional[int]:
        w = str(item_game_headers.get("white", "?")).strip().lower()
        b = str(item_game_headers.get("black", "?")).strip().lower()
        d = str(item_game_headers.get("date", "?")).strip()
        for (gw, gb, gd), g_idx in header_game_map.items():
            if gw == w and gb == b and (d == "?" or gd == "?" or gd == d):
                return g_idx
        return None

    before_motif_counts = defaultdict(int)
    after_motif_counts = defaultdict(int)

    findings = retagged.get("findings", [])
    for f in findings:
        for m in f.get("motifs", []):
            before_motif_counts[m] += 1

    resolved_count = 0
    unresolved_count = 0
    missed_sacrifices: List[Dict[str, Any]] = []

    # 2. Backfill pre_fen + setup_uci & re-tag each finding
    for item in findings:
        item_id = item.get("id", "")
        idx = eco_backfill.parse_game_idx_from_id(item_id)
        matched_idx = None

        if idx is not None and idx in game_map:
            entry = game_map[idx]
            item_game = item.get("game", {})
            iw = str(item_game.get("white", "")).strip().lower()
            ib = str(item_game.get("black", "")).strip().lower()
            gw = entry["game"].headers.get("White", "").strip().lower()
            gb = entry["game"].headers.get("Black", "").strip().lower()
            if (iw and gw and iw != gw) or (ib and gb and ib != gb):
                matched_idx = find_game_idx_by_headers(item_game)
            else:
                matched_idx = idx
        else:
            matched_idx = find_game_idx_by_headers(item.get("game", {}))

        setup_uci: Optional[str] = None
        pre_fen: Optional[str] = None
        resolved = False

        if matched_idx is not None and item.get("fen_before"):
            target_fen = item["fen_before"]
            target_board = chess.Board(target_fen)
            lookup_key = (matched_idx, target_board.board_fen(), target_board.turn)
            if lookup_key in fen_lookup:
                pre_fen, setup_uci = fen_lookup[lookup_key]
                resolved = True

        item["pre_fen"] = pre_fen
        item["setup_uci"] = setup_uci

        pv_san = item.get("pv_san", [])
        if resolved and pre_fen and setup_uci and pv_san:
            resolved_count += 1
            raw_tags = MotifDetector.analyze_pv(pre_fen, setup_uci, pv_san, cp=0)
            cleaned_motifs = sorted([m for m in raw_tags if m not in EVAL_TIER_TAGS])
            item["motifs"] = cleaned_motifs
        else:
            unresolved_count += 1
            item["motifs"] = []

        for m in item["motifs"]:
            after_motif_counts[m] += 1

        if "sacrifice" in item["motifs"]:
            sac_san = pv_san[0] if pv_san else ""
            missed_sacrifices.append({
                "id": item.get("id"),
                "white": item.get("game", {}).get("white"),
                "black": item.get("game", {}).get("black"),
                "date": item.get("game", {}).get("date"),
                "move_number": item.get("move_number", item.get("ply")),
                "ply": item.get("ply"),
                "sac_san": sac_san,
                "pv_san": pv_san,
                "fen_before": item.get("fen_before"),
            })

    # 3. Recompute aggregates["by_motif"]
    by_motif = defaultdict(lambda: {"missed": 0, "blind": 0, "confirmed": 0})
    for f in findings:
        weight = 2 if f.get("confirmation", {}).get("confirmed") else 1
        sev = f.get("severity", "missed")
        for m in f.get("motifs", []):
            by_motif[m][sev] += weight
            if f.get("confirmation", {}).get("confirmed"):
                by_motif[m]["confirmed"] += 1

    if "aggregates" not in retagged:
        retagged["aggregates"] = {}
    retagged["aggregates"]["by_motif"] = dict(by_motif)

    # 4. Migrate keys: had_tal_move -> had_sharp_move, tal_move -> sharp_move, tal_moves -> sharp_moves
    steer_findings = retagged.get("steer_findings", [])
    for sf in steer_findings:
        if "had_tal_move" in sf:
            sf["had_sharp_move"] = sf.pop("had_tal_move")
        if "tal_move" in sf:
            sf["sharp_move"] = sf.pop("tal_move")

    if "aggregates" in retagged and "tal_moves" in retagged["aggregates"]:
        retagged["aggregates"]["sharp_moves"] = retagged["aggregates"].pop("tal_moves")

    steer_summary = retagged.get("steer_summary", {})
    if isinstance(steer_summary, dict):
        for entry in steer_summary.values():
            if isinstance(entry, dict) and "tal_moves" in entry:
                entry["sharp_moves"] = entry.pop("tal_moves")

    summary_report = {
        "resolved_count": resolved_count,
        "unresolved_count": unresolved_count,
        "before_motif_counts": dict(before_motif_counts),
        "after_motif_counts": dict(after_motif_counts),
        "missed_sacrifices": missed_sacrifices,
    }

    return retagged, summary_report
