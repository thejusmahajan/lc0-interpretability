"""
NORMATIVE metric definitions for the Elite Training System.

This file is the single mathematical source of truth for:
  - Policy Divergence          (intuitive blindness)
  - Attention Engagement       (structural blindness)
  - Saliency Concentration     (hidden-gem detection)
  - Quietness / Sharpness      (repertoire + gem gating)

All functions are PURE: no engine calls, no I/O, no torch. Inputs are the
already-extracted data structures produced by the existing oracles:

  policy   : list[dict] from LC0Engine.get_policy_distribution(fen, nodes=1)
             each entry {"uci","san","from","to","p", ...}, sorted desc by p,
             p is a fraction in [0, 1]. Empty list in mock mode.
  saliency : dict[str, float] square-name -> [0,1] from
             NeuralVision.saliency_absolute(fen)  (ABSOLUTE frame — never use
             NeuralVision.saliency() for game analysis; it is only
             frame-correct for white-to-move positions).
  eval_cp  : LC0Engine.analyze()["evaluation"] — int centipawns from WHITE's
             point of view, or a mate string like "M5" / "M-3".

OWNERSHIP: leader-owned. Workers must NOT edit this file. If a threshold
needs tuning, change only TrainingConfig defaults and record why in
WORKLOG_TRAINING.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Optional

import chess


@dataclass(frozen=True)
class TrainingConfig:
    """Calibration constants. Initial values are reasoned defaults, not
    gospel — tune only with evidence, and log the change."""

    # --- Policy Divergence (Engine 1) ---
    # D = p_best - p_played. "missed": intuition preferred something much
    # stronger. "blind": the played move was essentially never considered.
    divergence_min: float = 0.15
    blind_prior_max: float = 0.05

    # --- Attention Blindness (Engine 1) ---
    # engagement = max saliency over the squares a move interacts with.
    attention_hot: float = 0.60   # best move engages at least this...
    attention_cold: float = 0.25  # ...while played move engages at most this

    # --- Stage-B confirmation (Engine 1) ---
    # A finding is "confirmed" when playing the best move instead is worth at
    # least this many centipawns (from the mover's point of view).
    confirm_swing_cp: int = 90

    # --- Quiet positions / hidden gems (Engine 3) ---
    quiet_eval_cp: int = 30       # |white-POV eval| <= this => "quiet"
    gem_top_prior: float = 0.35   # network strongly "feels" one move
    gem_top4_mass: float = 0.45   # attention concentrated on few squares

    # --- Drills / repertoire soundness (Engines 2 & 3) ---
    forced_swing_cp: int = 150    # corpus drill solutions must swing >= this
    sound_eval_cp: int = 50       # repertoire lines must stay within +/- this
    alt_solution_margin: float = 0.05  # priors within this of best = accepted

    # --- Repertoire sharpness (Engine 2) ---
    max_draw_pct: float = 45.0    # WDL draw% above this = too drawish to train

    # --- Engine time budgets, seconds (user-tuned 2026-07-20: doubled
    # from 3.0/1.5/0.8/3.0/2.0 — "2 or 3 seconds won't be enough") ---
    confirm_best_seconds: float = 6.0      # stage B best-move eval (multipv=2)
    confirm_played_seconds: float = 3.0    # stage B played-move eval
    gem_screen_seconds: float = 1.6        # gems quick quietness screen
    gem_confirm_seconds: float = 6.0       # gems confirmation eval
    repertoire_eval_seconds: float = 4.0   # repertoire soundness gate

    # --- Engine NODE budgets (optional, override the *_seconds above) ---
    # On a fast GPU backend the *_seconds limits explore absurdly deep (6s at
    # 133k nps = 800k nodes) and waste wall-clock. Setting a node budget makes
    # search depth hardware-INDEPENDENT: the same node count = the same analysis
    # quality on CPU or GPU, only the wall time differs. None = use *_seconds
    # (unchanged default; local CPU behavior is untouched). The GPU notebook
    # sets these to ~match the node depth the *_seconds limits bought on CPU.
    confirm_best_nodes: Optional[int] = None    # overrides confirm_best_seconds when set
    confirm_played_nodes: Optional[int] = None  # overrides confirm_played_seconds when set
    repertoire_eval_nodes: Optional[int] = None  # overrides repertoire_eval_seconds when set
    gem_screen_nodes: Optional[int] = None       # overrides gem_screen_seconds when set
    gem_confirm_nodes: Optional[int] = None       # overrides gem_confirm_seconds when set

    # --- Time-scramble filter (diagnosis) ---
    # ~~Moves played with less than this many seconds on the mover's clock~~
    # SUPERSEDED 2026-09-03 by min_think_seconds -- see below. Retained because
    # is_time_scramble() still reads it and older profiles were built with it.
    min_clock_seconds: float = 20.0

    # --- Think-time filter (diagnosis) -- 2026-09-03 ---
    # A move is a *decision* worth diagnosing when the player actually spent time
    # on it. min_clock_seconds gated on the clock REMAINING, which is the wrong
    # variable: in a 2+1 game a move played in one second with 60s left was kept,
    # while a move genuinely deliberated for eight seconds with 15s left was
    # thrown away. The stated intent was always to exclude flag-fall panic; time
    # SPENT is the correct expression of that intent.
    #
    # Measured over the user's 9,000-game corpus, his own moves:
    #   120+1 bullet  252,365 moves  median 2.0s  25.5% >= 5s
    #   300+3 blitz     6,623 moves  median 4.0s  48.2% >= 5s
    #   60+0            3,995 moves  median 1.0s   4.5% >= 5s
    # So bullet is NOT to be discarded: ~64,000 of those bullet moves are real
    # decisions, far more than the blitz corpus contains in total. Filter on
    # think time, never on time control.
    min_think_seconds: float = 5.0

    # --- Tactical steering / "Tal engine" (Epoch II, TS1) ---
    # User dials (2026-07-20): a steer move may cost ~0.5+ pawn vs best, and a
    # slight objective minus is acceptable, but never an objectively lost move.
    steer_max_loss_cp: int = 60       # max cp below best (mover POV) a steer may cost
    steer_min_eval_cp: int = -60      # absolute floor (mover POV): "minus ok, not lost"
    steer_top_k: int = 4              # candidate moves scored per node (caller uses)
    steer_bt3_budget: int = 200       # max saliency forwards per steering pass (caller enforces)
    steer_search_budget: int = 4000   # max engine.analyze calls (cache MISSES) per steering
                                      # run — the real cost cap. A run stops when hit; the
                                      # steer EPD cache makes the next run resume for free.
    steer_highlight_complexity: float = 0.6  # record a non-Tal node when the best move's own
                                             # complexity is at least this (the "sharp anyway" case)
    # complexity component weights (need not sum to 1 — score is normalized by
    # the weights actually used, so dropping the attention term still works):
    steer_w_decisiveness: float = 0.40   # WDL: low draw share = decisive
    steer_w_narrowness: float = 0.30     # only-move: gap best vs 2nd-best reply
    steer_w_policy_trap: float = 0.20    # sole saving reply has a low policy prior
    steer_w_attention: float = 0.10      # saliency diffusion (fires-everywhere = hard)
    steer_narrow_full_cp: int = 200   # reply eval-gap that saturates narrowness at 1.0
    steer_complexity_edge: float = 0.10  # a "Tal move" must beat best's complexity by this

    # --- Phase-aware mistake gating (Track A correctness, TS1) ---
    # In the opening a policy-divergent but objectively sound sideline is a
    # style choice, not a mistake — only confirmed eval loss counts there.
    opening_max_ply: int = 16


DEFAULT_CONFIG = TrainingConfig()


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------

def parse_increment(time_control: Optional[str]) -> float:
    """Increment in seconds from a PGN TimeControl header ("120+1" -> 1.0).

    Returns 0.0 for anything unparseable, including "-" (correspondence) and
    "?" (unknown), because treating an unknown increment as zero *under*-states
    think time, which errs toward discarding a move rather than admitting a
    reflex one.
    """
    if not time_control or "+" not in time_control:
        return 0.0
    try:
        return float(time_control.split("+", 1)[1])
    except (ValueError, IndexError):
        return 0.0


def think_seconds(prev_clock: Optional[float], clock: Optional[float],
                  increment: float = 0.0) -> Optional[float]:
    """Seconds the mover actually spent, from consecutive clocks of the SAME player.

    think = prev_clock - clock + increment

    Both clocks must belong to the same player and be consecutive; passing the
    opponent's clock produces a meaningless number. None when either clock is
    missing (the first move of a game has no predecessor), which callers must
    treat as "unknown", never as zero.

    A negative result is impossible in a well-formed PGN and indicates a clock
    adjustment, a berserk, or a parsing error; it is clamped to None rather than
    silently becoming a small positive think time.
    """
    if prev_clock is None or clock is None:
        return None
    spent = prev_clock - clock + increment
    if spent < 0.0:
        return None
    return spent


def is_reflex_move(prev_clock: Optional[float], clock: Optional[float],
                   increment: float = 0.0,
                   cfg: "TrainingConfig" = None) -> bool:
    """True when the move was played too fast to be a considered decision.

    Replaces is_time_scramble(). **Unknown think time is NOT a reflex move** --
    a PGN without [%clk] is analysed in full, exactly as before, rather than
    being silently discarded.
    """
    cfg = cfg or DEFAULT_CONFIG
    spent = think_seconds(prev_clock, clock, increment)
    if spent is None:
        return False
    return spent < cfg.min_think_seconds


def policy_prior(policy: list[dict], uci: str) -> float:
    """Prior P(s, a) for a move, 0.0 if it does not appear in the list."""
    for entry in policy:
        if entry.get("uci") == uci:
            return float(entry.get("p", 0.0))
    return 0.0


def policy_rank(policy: list[dict], uci: str) -> Optional[int]:
    """1-based rank of a move in the (desc-sorted) policy list, None if absent."""
    for i, entry in enumerate(policy):
        if entry.get("uci") == uci:
            return i + 1
    return None


def policy_uci(board_before: chess.Board, move: chess.Move) -> str:
    """A move's UCI in the LC0 policy frame.

    LC0 encodes castling as king-takes-rook ("e1h1"); python-chess's
    Move.uci() gives the standard frame ("e1g1"). Policy lookups MUST go
    through this helper or castling moves get prior 0.0 and produce false
    "blind" findings. Idempotent for non-castling moves.
    """
    return board_before.uci(move, chess960=True)


def accepted_ucis(board_before: chess.Board, uci: str) -> list[str]:
    """Every UCI spelling of the same legal move — castling has two
    (standard "e1g1" and LC0/chess960 "e1h1"), everything else one.
    Drill answer checks must accept all spellings, because chessground
    reports whichever square the user dropped the king on. Returns the
    input unchanged (as a single-item list) if it is not legal here."""
    try:
        move = board_before.parse_uci(uci)
    except ValueError:
        return [uci]
    return sorted({
        board_before.uci(move, chess960=False),
        board_before.uci(move, chess960=True),
    })


def eval_cp_number(evaluation) -> Optional[int]:
    """Normalize an LC0 evaluation to white-POV centipawns.

    Mate scores ("M5" / "M-3") map to +/-10000 so magnitude comparisons
    still work; returns None for unparseable input.
    """
    if isinstance(evaluation, (int, float)):
        return int(evaluation)
    if isinstance(evaluation, str) and evaluation.lstrip("-").startswith("M"):
        # engine_manager formats mate as "M<n>" with n signed for the side
        try:
            n = int(evaluation.replace("M", ""))
            return 10000 if n > 0 else -10000
        except ValueError:
            return None
    return None


def move_interaction_squares(board_before: chess.Board, move: chess.Move) -> set[str]:
    """The squares a move 'interacts with': from-square, to-square, the
    captured pawn's square for en passant, and every square the moved piece
    attacks AFTER the move is made."""
    squares: set[int] = {move.from_square, move.to_square}
    if board_before.is_en_passant(move):
        # captured pawn sits behind the to-square
        offset = -8 if board_before.turn == chess.WHITE else 8
        squares.add(move.to_square + offset)
    after = board_before.copy(stack=False)
    after.push(move)
    squares |= set(after.attacks(move.to_square))
    return {chess.square_name(sq) for sq in squares}


# ----------------------------------------------------------------------
# Engine 1 — Policy Divergence (intuitive blindness)
# ----------------------------------------------------------------------

def policy_divergence(
    policy: list[dict],
    played_uci: str,
    cfg: TrainingConfig = DEFAULT_CONFIG,
) -> Optional[dict]:
    """Compare the player's move against LC0's raw policy prior.

    Returns None when the policy list is empty (mock mode) — callers must
    skip the move, never treat it as a finding. Otherwise:
      {"p_played","p_best","best_uci","best_san","divergence",
       "rank_played","severity"}  where severity is:
        "blind"  — divergence >= divergence_min AND p_played <= blind_prior_max
                    (pattern recognition never surfaced the idea)
        "missed" — divergence >= divergence_min (considered, undervalued)
        None     — no significant divergence
    """
    if not policy:
        return None
    best = policy[0]
    p_best = float(best.get("p", 0.0))
    p_played = policy_prior(policy, played_uci)
    divergence = p_best - p_played

    severity: Optional[str] = None
    if played_uci != best.get("uci") and divergence >= cfg.divergence_min:
        severity = "blind" if p_played <= cfg.blind_prior_max else "missed"

    return {
        "p_played": p_played,
        "p_best": p_best,
        "best_uci": best.get("uci"),
        "best_san": best.get("san"),
        "divergence": divergence,
        "rank_played": policy_rank(policy, played_uci),
        "severity": severity,
    }


# ----------------------------------------------------------------------
# Engine 1 — Attention Blindness (structural blindness)
# ----------------------------------------------------------------------

def attention_engagement(saliency: dict[str, float], squares: set[str]) -> float:
    """Max saliency over a set of squares (0.0 for an empty set)."""
    return max((saliency.get(sq, 0.0) for sq in squares), default=0.0)


def attention_blindness(
    saliency: dict[str, float],
    board_before: chess.Board,
    played: chess.Move,
    best: chess.Move,
    cfg: TrainingConfig = DEFAULT_CONFIG,
) -> dict:
    """Structural blindness: the network's attention is concentrated where
    the best move operates, and the played move ignores that region.

      {"engagement_played","engagement_best","hot_squares","blind"}
    hot_squares = squares with saliency >= attention_hot, for display.
    """
    e_played = attention_engagement(
        saliency, move_interaction_squares(board_before, played))
    e_best = attention_engagement(
        saliency, move_interaction_squares(board_before, best))
    return {
        "engagement_played": e_played,
        "engagement_best": e_best,
        "hot_squares": sorted(
            sq for sq, v in saliency.items() if v >= cfg.attention_hot),
        "blind": e_best >= cfg.attention_hot and e_played <= cfg.attention_cold,
    }


# ----------------------------------------------------------------------
# Engine 1 — Stage-B confirmation
# ----------------------------------------------------------------------

def confirmation_swing(
    eval_best_cp,
    eval_played_cp,
    mover_is_white: bool,
    cfg: TrainingConfig = DEFAULT_CONFIG,
) -> Optional[dict]:
    """Eval swing (mover's POV, centipawns) between best-move and played-move
    continuations. Both inputs are white-POV evals of the position AFTER the
    respective move. Returns None if either eval is unparseable."""
    b = eval_cp_number(eval_best_cp)
    p = eval_cp_number(eval_played_cp)
    if b is None or p is None:
        return None
    swing = (b - p) if mover_is_white else (p - b)
    return {"swing_cp": swing, "confirmed": swing >= cfg.confirm_swing_cp}


# ----------------------------------------------------------------------
# Engine 3 — quietness, concentration, hidden gems
# ----------------------------------------------------------------------

def is_quiet(evaluation, cfg: TrainingConfig = DEFAULT_CONFIG) -> bool:
    """Near-0.00 position; mate scores are never quiet."""
    cp = eval_cp_number(evaluation)
    return cp is not None and abs(cp) <= cfg.quiet_eval_cp


def saliency_concentration(saliency: dict[str, float]) -> dict:
    """How concentrated the attention mass is.

      top4_mass — fraction of total saliency mass held by the 4 hottest
                  squares (0.0 when the map is empty/all-zero)
      top_squares — those squares, hottest first
    """
    vals = sorted(saliency.values(), reverse=True)
    total = sum(vals)
    if total <= 0:
        return {"top4_mass": 0.0, "top_squares": []}
    top_squares = sorted(saliency, key=saliency.get, reverse=True)[:4]
    return {"top4_mass": sum(vals[:4]) / total, "top_squares": top_squares}


def is_hidden_gem(
    evaluation,
    policy: list[dict],
    saliency: dict[str, float],
    cfg: TrainingConfig = DEFAULT_CONFIG,
) -> dict:
    """A quiet position with latent tension: eval ~0.00, but attention is
    concentrated AND the network strongly prefers one move.

      {"gem": bool, "quiet": bool, "top_prior": float, "top4_mass": float,
       "top_squares": [...]}
    """
    quiet = is_quiet(evaluation, cfg)
    top_prior = float(policy[0]["p"]) if policy else 0.0
    conc = saliency_concentration(saliency)
    return {
        "gem": (quiet
                and top_prior >= cfg.gem_top_prior
                and conc["top4_mass"] >= cfg.gem_top4_mass),
        "quiet": quiet,
        "top_prior": top_prior,
        "top4_mass": conc["top4_mass"],
        "top_squares": conc["top_squares"],
    }


# ----------------------------------------------------------------------
# Engine 2 — sharpness
# ----------------------------------------------------------------------

def sharpness_from_wdl(wdl, cfg: TrainingConfig = DEFAULT_CONFIG) -> Optional[dict]:
    """wdl = [wins, draws, losses] per-mille (LC0 UCI_ShowWDL, white POV).

      {"draw_pct": float, "sharp": bool}  — sharp when the draw share is
    below max_draw_pct. Returns None when wdl is missing."""
    if not wdl or len(wdl) != 3:
        return None
    total = sum(wdl)
    if total <= 0:
        return None
    draw_pct = 100.0 * wdl[1] / total
    return {"draw_pct": draw_pct, "sharp": draw_pct < cfg.max_draw_pct}


def alt_solutions(policy: list[dict], cfg: TrainingConfig = DEFAULT_CONFIG) -> list[str]:
    """UCIs of moves whose prior is within alt_solution_margin of the best —
    all accepted as correct answers in drills (the best move is included)."""
    if not policy:
        return []
    p_best = float(policy[0].get("p", 0.0))
    return [e["uci"] for e in policy
            if p_best - float(e.get("p", 0.0)) <= cfg.alt_solution_margin]


# ----------------------------------------------------------------------
# Tactical steering — the "Tal engine" (Epoch II, TS1). LEADER-OWNED.
#
# Pure math over oracle outputs. The engine calls that gather per-candidate
# multipv / policy / saliency happen in the callers (pipeline, select_
# repertoire); these functions never touch the engine. See TRAINING_ROADMAP.md
# "Epoch II — Tactical Steering" for the design.
# ----------------------------------------------------------------------

def _move_uci(entry: dict) -> Optional[str]:
    """best_moves entries carry the uci under 'move' (plan §2); tolerate 'uci'."""
    return entry.get("move") or entry.get("uci")


def tactical_complexity(
    analysis: dict,
    policy: list[dict],
    saliency: Optional[dict[str, float]] = None,
    cfg: TrainingConfig = DEFAULT_CONFIG,
) -> dict:
    """How much tactical danger a position holds *for the side to move* — the
    Tal sense. Call it on the position AFTER a candidate move (opponent to
    move): a high score means the opponent is likely to go wrong.

    Inputs (all from the analyzed position):
      analysis — engine.analyze(...): needs "wdl":[w,d,l] and
                 "best_moves":[{"move","score",...}, ...]. Scores are WHITE-POV cp
                 (as engine_manager emits them via PovScore.white()), ordered
                 best-first for the side to move. narrowness therefore uses the
                 magnitude |s0 - s1| — the mover-POV gap regardless of color.
      policy   — get_policy_distribution(...): [{"uci","p"}, ...].
      saliency — saliency_absolute(...), or None to skip the attention term
                 (e.g. BT3 budget exhausted) — weights renormalize.

    Returns {"score":0..1, "decisiveness","narrowness","policy_trap",
             "attention"}. Components are each 0..1; score is their
    weight-normalized combination.
    """
    # Decisiveness: win+loss share of the WDL (low draw = sharp).
    sharp = sharpness_from_wdl(analysis.get("wdl"), cfg)
    decisiveness = (1.0 - sharp["draw_pct"] / 100.0) if sharp else 0.0

    # Only-move narrowness: eval gap between the best and 2nd-best reply.
    best_moves = analysis.get("best_moves") or []
    gap_cp = 0.0
    best_reply_uci = _move_uci(best_moves[0]) if best_moves else None
    if len(best_moves) >= 2:
        s0 = eval_cp_number(best_moves[0].get("score"))
        s1 = eval_cp_number(best_moves[1].get("score"))
        if s0 is not None and s1 is not None:
            # scores are white-POV, best-first for the mover; the mover-POV gap
            # is the magnitude (for black-to-move, s0 < s1, so max(0,s0-s1)=0
            # would wrongly zero narrowness/policy_trap — audit F1).
            gap_cp = abs(s0 - s1)
    narrowness = min(gap_cp / cfg.steer_narrow_full_cp, 1.0) if cfg.steer_narrow_full_cp else 0.0

    # Policy trap: the sole saving reply carries a LOW prior — a human is
    # unlikely to find it. Only a trap where the reply is also narrow (else
    # many moves hold and low prior is meaningless), so scale by narrowness.
    if best_reply_uci is not None:
        p_saving = policy_prior(policy, best_reply_uci)
        policy_trap = (1.0 - p_saving) * narrowness
    else:
        policy_trap = 0.0

    # Attention diffusion: fires-everywhere boards are hard to read.
    use_attention = saliency is not None and len(saliency) > 0
    attention = (1.0 - saliency_concentration(saliency)["top4_mass"]) if use_attention else 0.0

    terms = [
        (cfg.steer_w_decisiveness, decisiveness),
        (cfg.steer_w_narrowness, narrowness),
        (cfg.steer_w_policy_trap, policy_trap),
    ]
    if use_attention:
        terms.append((cfg.steer_w_attention, attention))
    wsum = sum(w for w, _ in terms) or 1.0
    score = sum(w * v for w, v in terms) / wsum

    return {
        "score": score,
        "decisiveness": decisiveness,
        "narrowness": narrowness,
        "policy_trap": policy_trap,
        "attention": attention,
    }


def steer_candidates(
    candidates: list[dict],
    best_eval_cp: int,
    cfg: TrainingConfig = DEFAULT_CONFIG,
) -> dict:
    """Pick the sharpest *sound* move at a node the user is to move from.

    candidates — one dict per legal candidate move already evaluated by the
      caller: {"uci","san","eval_cp"(mover POV, of the position after the
      move),"complexity"(0..1 from tactical_complexity)}.
    best_eval_cp — mover-POV eval of the objective-best move at this node.

    A candidate is *playable* when it costs at most steer_max_loss_cp vs best
    AND its own eval stays >= steer_min_eval_cp (never objectively lost).
    Returns:
      {"playable": [playable candidates, complexity desc],
       "objective_best": <playable candidate with the highest eval_cp>,
       "sharp_move": <highest-complexity playable candidate>,
       "had_sharp_move": bool}
    had_sharp_move is True only when the sharpest playable move is a *different*
    move than the objective best and beats its complexity by
    steer_complexity_edge — i.e. steering actually buys danger over just
    playing the best move.
    """
    playable = [
        c for c in candidates
        if best_eval_cp - c["eval_cp"] <= cfg.steer_max_loss_cp
        and c["eval_cp"] >= cfg.steer_min_eval_cp
    ]
    if not playable:
        return {"playable": [], "objective_best": None,
                "sharp_move": None, "had_sharp_move": False}

    playable.sort(key=lambda c: c["complexity"], reverse=True)
    objective_best = max(playable, key=lambda c: c["eval_cp"])
    sharp_move = playable[0]
    had_sharp_move = (
        sharp_move["uci"] != objective_best["uci"]
        and sharp_move["complexity"] - objective_best["complexity"]
        >= cfg.steer_complexity_edge
    )
    return {"playable": playable, "objective_best": objective_best,
            "sharp_move": sharp_move, "had_sharp_move": had_sharp_move}


def is_opening_mistake(
    ply: int,
    divergence_severity: Optional[str],
    swing_cp: Optional[int],
    cfg: TrainingConfig = DEFAULT_CONFIG,
) -> bool:
    """Phase-aware Track A gate. In the opening (ply <= opening_max_ply) a
    move counts as a mistake ONLY if objectively unsound (confirmed swing >=
    confirm_swing_cp) — a policy-divergent but sound pet sideline is style,
    not error. Past the opening, policy severity ("blind"/"missed") stands.

    Keeps the diagnosis from telling the user to abandon the very repertoire
    Epoch II means to repair and polish.
    """
    if ply <= cfg.opening_max_ply:
        return swing_cp is not None and swing_cp >= cfg.confirm_swing_cp
    return divergence_severity in ("blind", "missed")


# ======================================================================
# Tutor-style comparison primitives  (Epoch III, Track T — leader)
# ----------------------------------------------------------------------
# Lifted from lila `modules/tutor` (TutorNumber / TutorCompare): represent
# every metric as a (value, count) pair, reduce a reference set to a
# count-weighted mean, and grade the gap by a *meaningful* divisor so only
# material differences surface. Ranking scales the gap by how well-sampled
# and how impactful the dimension is. Pure math; no I/O, no engine.
# ======================================================================


@dataclass(frozen=True)
class ValueCount:
    """A metric value together with the sample size behind it. Keeping the
    count lets the ranking discount thin evidence (a 1-game 100%-blind
    opening must not outrank a well-sampled real weakness)."""

    value: float
    count: int


def weighted_mean(items: Iterable[ValueCount]) -> Optional[ValueCount]:
    """Count-weighted mean of ValueCounts -> a single reference whose count is
    the pooled sample size. None when there is no sample at all."""
    total_val = 0.0
    total_n = 0
    for vc in items:
        total_val += vc.value * vc.count
        total_n += vc.count
    if total_n == 0:
        return None
    return ValueCount(total_val / total_n, total_n)


def grade(mine: float, ref: float, divisor: float,
          reverse: bool = False) -> float:
    """Signed effect size of `mine` vs a reference, normalized by `divisor`
    (the gap that counts as one full 'grade' — e.g. lila uses 150 Elo for
    ratings, a percent scale for rates). Positive = the user is *better*.
    `reverse=True` for metrics where lower is better (blind rate, time-trouble
    rate), so a lower value still grades positive."""
    if divisor <= 0:
        raise ValueError("divisor must be positive")
    g = (mine - ref) / divisor
    return -g if reverse else g


def importance(grade_value: float, count: int, weight: float = 1.0) -> float:
    """Ranking key (lila: grade * sqrt(count * position_weight)). Combines the
    magnitude of the gap with how well-sampled and how impactful the dimension
    is. Always >= 0 — use grade_value's sign for direction (strength vs
    weakness)."""
    return abs(grade_value) * sqrt(max(0, count) * max(0.0, weight))


@dataclass(frozen=True)
class DimComparison:
    """One dimension graded against the user's own baseline (self-relative)."""

    dim: str
    value: float
    count: int
    ref_value: float   # count-weighted mean of the OTHER dimensions
    grade: float       # signed effect size; > 0 = stronger than own baseline
    importance: float  # ranking key: |grade| * sqrt(count * weight)


def compare_to_dim_avg(
    points: "list[tuple[str, ValueCount]]",
    divisor: float,
    weight: float = 1.0,
    reverse: bool = False,
) -> "list[DimComparison]":
    """Grade each dimension against the user's OWN baseline — the count-weighted
    mean of the *other* dimensions (lila TutorCompare's DimAvg reference). Needs
    no peer dataset. Returns comparisons sorted by importance, most notable
    first. `reverse=True` for lower-is-better metrics (blind rate, time trouble)
    so that grade > 0 still means 'stronger than your baseline'.

    Excluding the dimension itself from its reference keeps a single dominant
    dimension from diluting its own baseline."""
    out: list[DimComparison] = []
    for i, (dim, vc) in enumerate(points):
        others = [p for j, (_, p) in enumerate(points) if j != i]
        ref = weighted_mean(others)
        if ref is None:
            continue
        g = grade(vc.value, ref.value, divisor, reverse=reverse)
        out.append(DimComparison(
            dim=dim, value=vc.value, count=vc.count, ref_value=ref.value,
            grade=g, importance=importance(g, vc.count, weight)))
    out.sort(key=lambda c: c.importance, reverse=True)
    return out


def mixed_bag(comparisons: "list[DimComparison]", n: int) -> "list[DimComparison]":
    """Balanced selection (lila): the top weaknesses and top strengths by
    importance, up to n total, weaknesses first (they are what to train).
    `comparisons` is expected pre-sorted by importance desc (as
    compare_to_dim_avg returns)."""
    if n <= 0:
        return []
    weaknesses = [c for c in comparisons if c.grade < 0]
    strengths = [c for c in comparisons if c.grade > 0]
    w = weaknesses[:max(n // 2, n - len(strengths))]
    s = strengths[:n - len(w)]
    return w + s


# --- T3: game-phase classifier + a ranking assembled from the profile -------
# The phase classifier is the pure building block for a future 'phase' ranking
# dimension (per-phase aggregation belongs in the pipeline). weakness_ranking
# turns the dimensions the profile ALREADY carries into a ranked "what to work
# on" via the T2 comparison — no new inputs required.

# blind-rate gap that counts as one full 'grade' (10 percentage points).
WEAKNESS_BLIND_DIVISOR = 0.10


def classify_phase(board_or_fen) -> str:
    """opening / middlegame / endgame, from ply + non-pawn material. Pure.

    endgame: few pieces left (<= 6 non-pawn, non-king pieces total);
    opening: within the first 12 full moves and not already an endgame;
    else middlegame."""
    board = (chess.Board(board_or_fen)
             if isinstance(board_or_fen, str) else board_or_fen)
    non_pawn = 0
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        non_pawn += len(board.pieces(pt, chess.WHITE))
        non_pawn += len(board.pieces(pt, chess.BLACK))
    if non_pawn <= 6:
        return "endgame"
    if board.fullmove_number <= 12:
        return "opening"
    return "middlegame"


def rank_dimension(by_dict: dict, n: int = 6,
                   divisor: float = WEAKNESS_BLIND_DIVISOR) -> "list[DimComparison]":
    """Rank ANY {key: {"blind_rate", "moves"}} aggregate (by_opening / by_phase /
    by_clock) by self-relative blindness: each bucket's blind_rate graded against
    the user's own baseline (the other buckets), weighted by move count so thin
    buckets don't dominate. Returns a mixed_bag (weaknesses first). blind_rate is
    lower-is-better, so reverse."""
    points = [
        (key, ValueCount(float(st.get("blind_rate", 0.0)), int(st.get("moves", 0))))
        for key, st in (by_dict or {}).items()
        if int(st.get("moves", 0)) > 0
    ]
    if not points:
        return []
    return mixed_bag(compare_to_dim_avg(points, divisor=divisor, reverse=True), n)


def weakness_ranking(profile: dict, n: int = 6,
                     divisor: float = WEAKNESS_BLIND_DIVISOR) -> "list[DimComparison]":
    """The openings ranking (kept for the existing endpoint)."""
    agg = (profile or {}).get("aggregates", {})
    return rank_dimension(agg.get("by_opening", {}), n, divisor)


def weakness_ranking_all(profile: dict, n: int = 6,
                         divisor: float = WEAKNESS_BLIND_DIVISOR) -> "dict":
    """Rank every dimension the profile carries — openings, game phase, and clock
    pressure — so 'what to work on' spans more than just openings. Missing
    dimensions (older profiles without by_phase/by_clock) come back as []."""
    agg = (profile or {}).get("aggregates", {})
    return {
        "openings": rank_dimension(agg.get("by_opening", {}), n, divisor),
        "phase": rank_dimension(agg.get("by_phase", {}), n, divisor),
        "clock": rank_dimension(agg.get("by_clock", {}), n, divisor),
    }
