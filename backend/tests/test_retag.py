from __future__ import annotations

import os
import tempfile
import chess
import chess.pgn
import pytest

from backend.training.profile_retag import retag_profile, EVAL_TIER_TAGS


def create_synthetic_pgn(games_data: list[dict]) -> str:
    """Helper to create a temporary PGN file for synthetic test games.
    
    Each game_dict has: {"white": str, "black": str, "date": str, "san_moves": list[str]}
    """
    tmp_pgn = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".pgn")
    for gd in games_data:
        game = chess.pgn.Game()
        game.headers["White"] = gd.get("white", "derdiedasdie")
        game.headers["Black"] = gd.get("black", "Opponent")
        game.headers["Date"] = gd.get("date", "2026.07.21")
        board = game.board()
        node = game
        for san_move in gd["san_moves"]:
            move = board.parse_san(san_move)
            node = node.add_variation(move)
            board.push(move)
        exporter = chess.pgn.FileExporter(tmp_pgn)
        game.accept(exporter)
    tmp_pgn.close()
    return tmp_pgn.name


def test_retag_real_sacrifice_motif():
    """1. Synthetic finding with a real material sac line -> motifs include 'sacrifice' and exclude eval tier tags."""
    game_moves = [
        'e4', 'e6', 'd4', 'd5', 'Nc3', 'Nf6', 'e5', 'Nfd7', 'f4', 'c5',
        'Nf3', 'Nc6', 'Be3', 'cxd4', 'Nxd4', 'Bc5', 'Qd2', 'O-O', 'O-O-O', 'a6',
        'h4', 'Nxd4', 'Bxd4', 'b5', 'Rh3', 'b4', 'Na4', 'Bxd4', 'Qxd4', 'a5',
        'h5', 'Ba6', 'Bxa6', 'Rxa6', 'h6', 'g6', 'f5', 'gxf5', 'Rg3+', 'Kh8',
        'Rg7', 'Qe8', 'Re1', 'Rg8', 'Re3', 'Rxg7', 'hxg7+', 'Kxg7', 'Rg3+', 'Kh8'
    ]
    pgn_path = create_synthetic_pgn([{"white": "derdiedasdie", "black": "Opponent", "date": "2026.07.21", "san_moves": game_moves}])
    
    board = chess.Board()
    for m in game_moves:
        board.push_san(m)
    fen_before = board.fen()
    
    # White knight sac line: 51. Qh4 Qf8 52. Nc5 Nxc5 53. Qf6+
    finding = {
        "id": "g000-p051",
        "game": {"white": "derdiedasdie", "black": "Opponent", "date": "2026.07.21"},
        "user_color": "white",
        "ply": 51,
        "fen_before": fen_before,
        "pv_san": ["Qh4", "Qf8", "Nc5", "Nxc5", "Qf6+"],
        "motifs": ["advantage", "veryLong"]
    }
    
    profile = {
        "player_name": "derdiedasdie",
        "games_analyzed": 1,
        "findings": [finding],
        "aggregates": {"by_motif": {}}
    }
    
    try:
        retagged, summary = retag_profile(profile, pgn_path)
        retagged_finding = retagged["findings"][0]
        
        assert summary["resolved_count"] == 1
        assert "sacrifice" in retagged_finding["motifs"]
        assert not any(tag in retagged_finding["motifs"] for tag in EVAL_TIER_TAGS)
    finally:
        os.remove(pgn_path)


def test_retag_material_winning_line_no_sacrifice():
    """2. Synthetic finding whose line WINS material -> motifs do NOT include 'sacrifice'."""
    game_moves = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d4", "exd4", "cxd4", "Bb4+", "Bd2", "Bxd2+", "Nbxd2", "d5", "exd5", "Nxd5", "Qb3", "Nce7", "O-O", "O-O", "Rfe1", "c6"]
    pgn_path = create_synthetic_pgn([{"white": "derdiedasdie", "black": "Opponent", "date": "2026.07.21", "san_moves": game_moves}])
    
    board = chess.Board()
    for m in game_moves:
        board.push_san(m)
    fen_before = board.fen()
    
    finding = {
        "id": "g000-p024",
        "game": {"white": "derdiedasdie", "black": "Opponent", "date": "2026.07.21"},
        "user_color": "white",
        "ply": 24,
        "fen_before": fen_before,
        "pv_san": ["a4", "Nb6", "Bxf7+", "Rxf7"],
        "motifs": ["advantage"]
    }
    
    profile = {
        "player_name": "derdiedasdie",
        "games_analyzed": 1,
        "findings": [finding],
        "aggregates": {"by_motif": {}}
    }
    
    try:
        retagged, _ = retag_profile(profile, pgn_path)
        retagged_finding = retagged["findings"][0]
        
        assert "sacrifice" not in retagged_finding["motifs"]
    finally:
        os.remove(pgn_path)


def test_retag_strips_eval_tier_tags():
    """3. Eval-tier strip: assert no re-tagged finding carries crushing/advantage/equality."""
    game_moves = ["e4", "e5", "Nf3", "Nc6"]
    pgn_path = create_synthetic_pgn([{"white": "derdiedasdie", "black": "Opponent", "date": "2026.07.21", "san_moves": game_moves}])
    
    board = chess.Board()
    for m in game_moves:
        board.push_san(m)
    fen_before = board.fen()
    
    finding = {
        "id": "g000-p004",
        "game": {"white": "derdiedasdie", "black": "Opponent", "date": "2026.07.21"},
        "user_color": "white",
        "ply": 4,
        "fen_before": fen_before,
        "pv_san": ["Bc4", "Bc5"],
        "motifs": ["advantage", "equality", "crushing", "quietMove"]
    }
    
    profile = {
        "player_name": "derdiedasdie",
        "games_analyzed": 1,
        "findings": [finding],
        "aggregates": {"by_motif": {}}
    }
    
    try:
        retagged, _ = retag_profile(profile, pgn_path)
        motifs = retagged["findings"][0]["motifs"]
        for bad_tag in ["crushing", "advantage", "equality"]:
            assert bad_tag not in motifs
    finally:
        os.remove(pgn_path)


def test_retag_key_migration():
    """4. Key migration: profile with had_tal_move/tal_moves -> migrated to had_sharp_move/sharp_moves."""
    profile = {
        "player_name": "derdiedasdie",
        "findings": [],
        "steer_findings": [
            {
                "id": "s-001-p010",
                "had_tal_move": True,
                "tal_move": {"uci": "e2e4", "complexity": 0.8}
            }
        ],
        "aggregates": {
            "by_motif": {},
            "tal_moves": 15
        },
        "steer_summary": {
            "C60": {"moves": 10, "tal_moves": 4}
        }
    }
    
    retagged, _ = retag_profile(profile, pgn_path="")
    
    sf = retagged["steer_findings"][0]
    assert sf.get("had_sharp_move") is True
    assert "had_tal_move" not in sf
    assert sf.get("sharp_move") == {"uci": "e2e4", "complexity": 0.8}
    assert "tal_move" not in sf
    
    assert retagged["aggregates"].get("sharp_moves") == 15
    assert "tal_moves" not in retagged["aggregates"]
    
    assert retagged["steer_summary"]["C60"].get("sharp_moves") == 4
    assert "tal_moves" not in retagged["steer_summary"]["C60"]
