import os
import re
import logging
import chess
import chess.pgn
from typing import Dict, Any, List, Tuple, Optional
from backend.training import openings, metrics, pipeline

logger = logging.getLogger("chess_speak_out_loud")


def parse_game_idx_from_id(item_id: str) -> Optional[int]:
    """Extract game index integer from finding ID string (e.g. 'g005-p012' -> 5, 's-005-p012' -> 5)."""
    if not item_id or not isinstance(item_id, str):
        return None
    m = re.search(r'^[gs]-?(\d+)-p', item_id)
    if m:
        return int(m.group(1))
    return None


def backfill_ecos(profile: Dict[str, Any], pgn_path: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Enrich profile findings and steer_findings with real ECO codes and names from PGN.
    
    Returns (enriched_profile, summary_dict) where summary_dict is:
    {"openings": [{"eco": str, "name": str, "count": int}, ...], "unresolved": int, "discrepancies": int}
    """
    import copy
    enriched = copy.deepcopy(profile)
    player_name = str(enriched.get("player_name", "derdiedasdie")).lower()
    games_analyzed = enriched.get("games_analyzed", 0)

    games_to_process: List[Tuple[chess.pgn.Game, str]] = []  # (game, user_color)

    if os.path.exists(pgn_path):
        with open(pgn_path, "r", encoding="utf-8", errors="replace") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                white = game.headers.get("White", "")
                black = game.headers.get("Black", "")

                user_color = None
                if player_name in white.lower():
                    user_color = "white"
                elif player_name in black.lower():
                    user_color = "black"

                if user_color is not None:
                    games_to_process.append((game, user_color))
                    if games_analyzed > 0 and len(games_to_process) >= games_analyzed:
                        break

    game_map: Dict[int, Dict[str, Any]] = {}
    eco_counts: Dict[str, Dict[str, Any]] = {}

    for idx, (game, color) in enumerate(games_to_process):
        board = game.board()
        uci_moves = []
        for node in game.mainline():
            uci_moves.append(node.move.uci())
            board.push(node.move)

        classification = openings.classify(uci_moves)
        if classification:
            opening_data = {"eco": classification["eco"], "name": classification["name"]}
            eco = classification["eco"]
            if eco not in eco_counts:
                eco_counts[eco] = {"eco": eco, "name": classification["name"], "count": 0}
            eco_counts[eco]["count"] += 1
        else:
            opening_data = {"eco": "???", "name": "Unknown"}

        game_map[idx] = {
            "game": game,
            "user_color": color,
            "opening": opening_data,
            "uci_moves": uci_moves,
        }

    def find_game_by_headers(item_game_headers: dict) -> Optional[Dict[str, Any]]:
        w = str(item_game_headers.get("white", "?")).strip().lower()
        b = str(item_game_headers.get("black", "?")).strip().lower()
        d = str(item_game_headers.get("date", "?")).strip()
        for entry in game_map.values():
            g = entry["game"]
            gw = g.headers.get("White", "").strip().lower()
            gb = g.headers.get("Black", "").strip().lower()
            gd = g.headers.get("Date", "").strip()
            if gw == w and gb == b and (d == "?" or gd == "?" or gd == d):
                return entry
        return None

    def classify_position(entry: Dict[str, Any], ply: int) -> Dict[str, str]:
        uci_moves = entry["uci_moves"][:ply] if ply > 0 else entry["uci_moves"]
        classification = openings.classify(uci_moves)
        if classification:
            return {"eco": classification["eco"], "name": classification["name"]}
        return {"eco": "???", "name": "Unknown"}

    discrepancies = 0
    unresolved = 0

    findings = enriched.get("findings", [])
    steer_findings = enriched.get("steer_findings", [])

    for item in findings:
        item_id = item.get("id", "")
        idx = parse_game_idx_from_id(item_id)
        ply = item.get("ply", 0)
        matched_entry = None

        if idx is not None and idx in game_map:
            entry = game_map[idx]
            item_game = item.get("game", {})
            iw = str(item_game.get("white", "")).strip().lower()
            ib = str(item_game.get("black", "")).strip().lower()
            gw = entry["game"].headers.get("White", "").strip().lower()
            gb = entry["game"].headers.get("Black", "").strip().lower()

            if (iw and gw and iw != gw) or (ib and gb and ib != gb):
                logger.warning(f"Alignment mismatch for {item_id}: item '{iw}' vs '{ib}' != PGN '{gw}' vs '{gb}'")
                discrepancies += 1
                matched_entry = find_game_by_headers(item_game)
            else:
                matched_entry = entry
        else:
            matched_entry = find_game_by_headers(item.get("game", {}))

        if matched_entry:
            item["opening"] = classify_position(matched_entry, ply)
        else:
            item["opening"] = {"eco": "???", "name": "Unknown"}

        if item["opening"]["eco"] == "???":
            unresolved += 1

    for item in steer_findings:
        item_id = item.get("id", "")
        idx = parse_game_idx_from_id(item_id)
        ply = item.get("ply", 0)
        matched_entry = None

        if idx is not None and idx in game_map:
            entry = game_map[idx]
            item_game = item.get("game", {})
            iw = str(item_game.get("white", "")).strip().lower()
            ib = str(item_game.get("black", "")).strip().lower()
            gw = entry["game"].headers.get("White", "").strip().lower()
            gb = entry["game"].headers.get("Black", "").strip().lower()

            if (iw and gw and iw != gw) or (ib and gb and ib != gb):
                logger.warning(f"Alignment mismatch for steer {item_id}: item '{iw}' vs '{ib}' != PGN '{gw}' vs '{gb}'")
                discrepancies += 1
                matched_entry = find_game_by_headers(item_game)
            else:
                matched_entry = entry
        else:
            matched_entry = find_game_by_headers(item.get("game", {}))

        if matched_entry:
            item["opening"] = classify_position(matched_entry, ply)
        else:
            item["opening"] = {"eco": "???", "name": "Unknown"}

        if item["opening"]["eco"] == "???":
            unresolved += 1


    # Recompute aggregates.by_opening
    by_opening: Dict[str, Dict[str, Any]] = {}

    for idx, entry in game_map.items():
        game = entry["game"]
        user_color = entry["user_color"]
        board = game.board()
        uci_moves = []

        for node in game.mainline():
            uci_moves.append(node.move.uci())
            if (board.turn == chess.WHITE and user_color == "white") or (board.turn == chess.BLACK and user_color == "black"):
                if not pipeline.is_time_scramble(node.comment):
                    opening_match = openings.classify(uci_moves)
                    if opening_match:
                        eco = opening_match["eco"]
                        if eco not in by_opening:
                            by_opening[eco] = {
                                "moves": 0, "moves_white": 0, "moves_black": 0,
                                "missed": 0, "blind": 0, "blind_rate": 0.0
                            }
                        by_opening[eco]["moves"] += 1
                        color_key = "moves_white" if user_color == "white" else "moves_black"
                        by_opening[eco][color_key] += 1
            board.push(node.move)

    for f in findings:
        eco = f.get("opening", {}).get("eco", "???")
        sev = f.get("severity")
        if eco not in by_opening:
            by_opening[eco] = {
                "moves": 0, "moves_white": 0, "moves_black": 0,
                "missed": 0, "blind": 0, "blind_rate": 0.0
            }
        if sev in ("missed", "blind"):
            by_opening[eco][sev] += 1

    for eco, st in by_opening.items():
        if st["moves"] > 0:
            st["blind_rate"] = round(st["blind"] / st["moves"], 4)

    if "aggregates" not in enriched:
        enriched["aggregates"] = {}
    enriched["aggregates"]["by_opening"] = by_opening

    openings_summary = sorted(
        list(eco_counts.values()),
        key=lambda x: x["count"],
        reverse=True
    )
    summary = {
        "openings": openings_summary,
        "unresolved": unresolved,
        "discrepancies": discrepancies,
    }

    return enriched, summary
