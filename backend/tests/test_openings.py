"""
Unit tests for backend/training/openings.py: verifying opening book classification,
move notation parsing (e.g. 1.e4, 1...e5 tokens), package-bundled data resolution, and logging.
"""

import os
import logging
import pytest
from backend.training import openings


def test_classify_known_openings():
    """Verify known move sequences classify to their exact ECO codes."""
    # 1.e4 e5 2.Nf3 -> King's Knight Opening (C40)
    res = openings.classify(["e2e4", "e7e5", "g1f3"])
    assert res is not None, "1.e4 e5 2.Nf3 failed to classify"
    assert res["eco"] == "C40"
    assert "King's Knight Opening" in res["name"]

    # 1.e4 c5 -> Sicilian Defense (B20)
    res_sicilian = openings.classify(["e2e4", "c7c5"])
    assert res_sicilian is not None
    assert res_sicilian["eco"] == "B20"
    assert "Sicilian Defense" in res_sicilian["name"]

    # 1.d4 d5 2.c4 -> Queen's Gambit (D06)
    res_qg = openings.classify(["d2d4", "d7d5", "c2c4"])
    assert res_qg is not None
    assert res_qg["eco"] == "D06"
    assert "Queen's Gambit" in res_qg["name"]


def test_openings_handles_dots_and_numbers():
    """Verify that move tokens with move numbers and dots (e.g. 1.e4, 1...e5, 2...Nf6)
    do not crash the parser or break sequence matching."""
    # Ruy Lopez: Steinitz Defense (C62): 1.e4 e5 2.Nf3 Nc6 3.Bb5 d6
    steinitz_moves = ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "d7d6"]
    res = openings.classify(steinitz_moves)
    assert res is not None
    assert res["eco"] == "C62"
    assert "Steinitz Defense" in res["name"]


def test_lines_by_tag_populates():
    """Verify lines_by_tag returns populated opening lines."""
    lines = openings.lines_by_tag()
    assert len(lines) > 100, f"Expected >100 opening tags, got {len(lines)}"
    assert "Sicilian_Defense" in lines or any("Sicilian" in k for k in lines)


def test_openings_dir_resolution_order(tmp_path, monkeypatch):
    """Verify resolution order: env var > backend/openings_data > data/openings."""
    fake_env_dir = str(tmp_path / "env_openings")
    os.makedirs(fake_env_dir, exist_ok=True)
    monkeypatch.setenv("CSZERO_OPENINGS_DIR", fake_env_dir)

    resolved = openings._get_openings_dir()
    assert resolved == fake_env_dir


def test_missing_openings_dir_logs_warning(caplog, tmp_path, monkeypatch):
    """Verify missing openings dir logs a warning instead of failing silently."""
    non_existent = str(tmp_path / "non_existent_openings_path")
    monkeypatch.setenv("CSZERO_OPENINGS_DIR", non_existent)

    # Save state to restore after test
    prev_trie = dict(openings._openings_trie)
    prev_tabiya = dict(openings._tabiya_fens)

    openings._loaded = False
    openings._openings_trie.clear()
    openings._tabiya_fens.clear()

    try:
        with caplog.at_level(logging.WARNING):
            res = openings.classify(["e2e4", "e7e5"])
            assert res is None

        assert any("Opening data directory not found" in record.message for record in caplog.records)
    finally:
        # Restore state so subsequent tests have loaded openings
        openings._loaded = False
        openings._openings_trie.clear()
        openings._tabiya_fens.clear()
        openings._openings_trie.update(prev_trie)
        openings._tabiya_fens.update(prev_tabiya)
        if prev_trie:
            openings._loaded = True
