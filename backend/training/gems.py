"""Hidden-gem detector (Engine 3).

A "hidden gem" is a quiet position (eval ~0.00) with latent tension: the
network strongly prefers one move AND its attention is concentrated on few
squares. Pure orchestration — every judgment comes from
`backend.training.metrics`; every oracle call matches TRAINING_SYSTEM_PLAN §2.

The scan is a filter funnel, cheapest test first, so the BT3 budget
(`max_bt3` saliency forwards, ~1.5s each on CPU) is spent only on survivors:
dedupe → policy gate → quiet gate → attention gate (BT3) → confirmation.

OWNERSHIP: Claude worker (C1). See CLAUDE_TRAINING_TASKS.md.
"""

from __future__ import annotations

import chess

from backend.tactics import MotifDetector
from backend.training import metrics
from backend.training.metrics import DEFAULT_CONFIG, TrainingConfig


def gem_candidates_from_profile(profile: dict) -> list[str]:
    """Candidate FENs from a diagnosis profile.

    Non-flagged user positions are not stored in the profile, so the only
    positions available are each finding's pre-move position. The scan funnel
    does all further filtering; callers may pass any FEN list instead."""
    if not profile:
        return []
    return [f["fen_before"] for f in profile.get("findings", [])
            if f.get("fen_before")]


async def scan_for_gems(
    fens: list[str],
    engine,
    vision,
    cfg: TrainingConfig = DEFAULT_CONFIG,
    max_bt3: int = 100,
) -> list[dict]:
    """Scan candidate FENs and return confirmed hidden gems.

    Funnel order is normative (cheapest first); BT3 forwards are counted and
    the scan stops once `max_bt3` have been spent. Empty policy (engine in
    mock mode) skips the fen — mock data must never reach an output artifact.
    """
    gems: list[dict] = []
    seen_epds: set[str] = set()
    bt3_used = 0

    for fen in fens:
        if bt3_used >= max_bt3:
            break

        try:
            board = chess.Board(fen)
        except ValueError:
            continue
        epd = board.epd()
        if epd in seen_epds:
            continue
        seen_epds.add(epd)

        # 1. Policy gate (cheapest engine call)
        policy = await engine.get_policy_distribution(fen, nodes=1)
        if not policy:  # mock mode
            continue
        if float(policy[0].get("p", 0.0)) < cfg.gem_top_prior:
            continue

        # 2. Quiet gate
        quick = await engine.analyze(fen, depth=None, multipv=1,
                                     time_limit=cfg.gem_screen_seconds,
                                     nodes=cfg.gem_screen_nodes)
        evaluation = quick["evaluation"]
        if not metrics.is_quiet(evaluation, cfg):
            continue

        # 3. Attention gate — the budgeted BT3 forward
        saliency = vision.saliency_absolute(fen)
        bt3_used += 1
        gem_stats = metrics.is_hidden_gem(evaluation, policy, saliency, cfg)
        if not gem_stats["gem"]:
            continue

        # 4. Confirmation search
        confirm = await engine.analyze(fen, depth=None, multipv=2,
                                       time_limit=cfg.gem_confirm_seconds,
                                       nodes=cfg.gem_confirm_nodes)
        pv_san = confirm["pv_lines"][0].split() if confirm["pv_lines"] else []
        top = policy[0]
        alt_solution_ucis = sorted({
            u for a in metrics.alt_solutions(policy, cfg)
            for u in metrics.accepted_ucis(board, a)
        })

        gems.append({
            "fen": fen,
            "side_to_move": "white" if board.turn == chess.WHITE else "black",
            "policy": policy,
            "saliency": saliency,
            "gem_stats": gem_stats,
            "solution_uci": top["uci"],
            "alt_solution_ucis": alt_solution_ucis,
            "solution_san": top.get("san"),
            "pv_san": pv_san,
            "eval_cp": confirm["evaluation"],
            "motifs": sorted(MotifDetector.analyze_pv(fen, pv_san)),
        })

    return gems
