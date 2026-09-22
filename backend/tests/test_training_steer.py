"""TS1 — tactical-complexity metric, steering selection, phase-aware gating.

Pure math over hand-built oracle outputs; no engine, no board.
"""

from backend.training import metrics

CFG = metrics.DEFAULT_CONFIG


# ---------------------------------------------------------------- complexity

def _analysis(wdl, gap_cp, best_uci="e2e4"):
    """A minimal engine.analyze() shape: a decisive/drawish WDL and two
    replies whose score gap is `gap_cp` (side-to-move POV)."""
    return {
        "wdl": wdl,
        "best_moves": [
            {"move": best_uci, "score": 100},
            {"move": "d2d4", "score": 100 - gap_cp},
        ],
    }


def test_complexity_sharp_narrow_trap_scores_high():
    # Decisive WDL (little draw), wide reply gap (only-move), and the saving
    # reply has a tiny prior -> maximal danger.
    analysis = _analysis([600, 50, 350], gap_cp=200, best_uci="g1f3")
    policy = [{"uci": "b1c3", "p": 0.7}, {"uci": "g1f3", "p": 0.03}]
    c = metrics.tactical_complexity(analysis, policy, saliency=None, cfg=CFG)
    assert c["decisiveness"] > 0.9
    assert c["narrowness"] == 1.0            # 200cp gap saturates
    assert c["policy_trap"] > 0.9            # (1 - 0.03) * 1.0
    assert c["score"] > 0.9


def test_complexity_drawish_calm_scores_low():
    # High draw share, no reply gap -> calm.
    analysis = _analysis([100, 800, 100], gap_cp=0)
    policy = [{"uci": "e2e4", "p": 0.5}]
    c = metrics.tactical_complexity(analysis, policy, cfg=CFG)
    assert c["decisiveness"] < 0.25
    assert c["narrowness"] == 0.0
    assert c["policy_trap"] == 0.0           # scaled by narrowness (0)
    assert c["score"] < 0.2


def test_complexity_renormalizes_without_saliency():
    analysis = _analysis([600, 50, 350], gap_cp=200, best_uci="g1f3")
    policy = [{"uci": "g1f3", "p": 0.03}]
    no_sal = metrics.tactical_complexity(analysis, policy, saliency=None, cfg=CFG)
    # Attention term absent -> weights renormalize over the other three; a
    # fully-diffuse map (attention≈1) with the default weight pulls score up.
    diffuse = {chr(97 + i) + "1": 0.1 for i in range(8)}  # 8 equal squares
    with_sal = metrics.tactical_complexity(analysis, policy, saliency=diffuse, cfg=CFG)
    assert no_sal["attention"] == 0.0
    assert with_sal["attention"] > 0.4
    assert abs(no_sal["score"] - with_sal["score"]) > 1e-6


def test_policy_trap_needs_narrowness():
    # Low prior on the best reply but NO reply gap -> not a trap (many moves
    # hold, so failing to find "the" move costs nothing).
    analysis = _analysis([600, 50, 350], gap_cp=0, best_uci="g1f3")
    policy = [{"uci": "g1f3", "p": 0.02}]
    c = metrics.tactical_complexity(analysis, policy, cfg=CFG)
    assert c["policy_trap"] == 0.0


# ------------------------------------------------------------ steering picks

def _cand(uci, eval_cp, complexity):
    return {"uci": uci, "san": uci, "eval_cp": eval_cp, "complexity": complexity}


def test_steer_picks_sharper_within_bound():
    # best = +80 (calm); a +30 move (loss 50 <= 60) is much sharper -> sharp move.
    cands = [_cand("a1a2", 80, 0.2), _cand("b1b2", 30, 0.8)]
    r = metrics.steer_candidates(cands, best_eval_cp=80, cfg=CFG)
    assert r["had_sharp_move"] is True
    assert r["sharp_move"]["uci"] == "b1b2"
    assert r["objective_best"]["uci"] == "a1a2"


def test_steer_rejects_move_over_loss_bound():
    # The sharp move costs 90cp (> 60) -> not playable; no sharp move.
    cands = [_cand("a1a2", 80, 0.2), _cand("b1b2", -10, 0.9)]
    r = metrics.steer_candidates(cands, best_eval_cp=80, cfg=CFG)
    assert [c["uci"] for c in r["playable"]] == ["a1a2"]
    assert r["had_sharp_move"] is False


def test_steer_allows_slight_minus_but_not_lost():
    # A -50 move is within the floor (-60) and the loss bound -> playable.
    cands = [_cand("a1a2", 5, 0.2), _cand("b1b2", -50, 0.85)]
    r = metrics.steer_candidates(cands, best_eval_cp=5, cfg=CFG)
    assert r["had_sharp_move"] is True and r["sharp_move"]["uci"] == "b1b2"
    # A -70 move (below the -60 floor) is rejected even if the loss is small.
    lost = [_cand("a1a2", -15, 0.2), _cand("b1b2", -70, 0.9)]
    r2 = metrics.steer_candidates(lost, best_eval_cp=-15, cfg=CFG)
    assert [c["uci"] for c in r2["playable"]] == ["a1a2"]


def test_steer_no_tal_move_when_best_is_already_sharpest():
    cands = [_cand("a1a2", 80, 0.8), _cand("b1b2", 40, 0.3)]
    r = metrics.steer_candidates(cands, best_eval_cp=80, cfg=CFG)
    assert r["had_sharp_move"] is False
    assert r["sharp_move"]["uci"] == "a1a2"


# --------------------------------------------------------- phase-aware gate

def test_opening_mistake_needs_confirmed_swing():
    # ply 8, opening: policy-blind but no eval loss -> NOT a mistake (style).
    assert metrics.is_opening_mistake(8, "blind", swing_cp=10, cfg=CFG) is False
    # ...unless it is objectively unsound.
    assert metrics.is_opening_mistake(8, "blind", swing_cp=150, cfg=CFG) is True


def test_middlegame_mistake_uses_policy_severity():
    assert metrics.is_opening_mistake(40, "missed", swing_cp=None, cfg=CFG) is True
    assert metrics.is_opening_mistake(40, None, swing_cp=None, cfg=CFG) is False


def test_complexity_narrowness_holds_for_black_to_move():
    # Audit F1 guard: best_moves scores are WHITE-POV. For a black-to-move
    # position, black's best reply has a LOWER white-POV score than the 2nd, so
    # the mover-POV gap is the magnitude. The old max(0, s0 - s1) wrongly zeroed
    # narrowness/policy_trap for every black-to-move analysis (i.e. every
    # position after a White user's candidate move).
    import pytest
    analysis = {
        "wdl": [350, 50, 600],  # decisive
        "best_moves": [
            {"move": "e7e5", "score": -200},   # black's best  (white-POV -200)
            {"move": "d7d5", "score": -50},    # black's 2nd   (white-POV  -50)
        ],
    }
    policy = [{"uci": "b8c6", "p": 0.7}, {"uci": "e7e5", "p": 0.03}]
    c = metrics.tactical_complexity(analysis, policy, saliency=None, cfg=CFG)
    assert c["narrowness"] == pytest.approx(0.75)   # |−200 − (−50)| = 150 / 200
    assert c["policy_trap"] > 0.6                    # (1 − 0.03) * 0.75
