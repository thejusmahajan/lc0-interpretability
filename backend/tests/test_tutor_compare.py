"""Track T (Tutor-style comparison) — T1 primitives: ValueCount, weighted_mean,
grade, importance. Lifted from lila modules/tutor (TutorNumber)."""
import math

import pytest

from backend.training import metrics as m


def test_weighted_mean_is_count_weighted():
    # 0.2 over 90 samples vs 0.9 over 10 -> pooled mean pulled toward 0.2
    vc = m.weighted_mean([m.ValueCount(0.2, 90), m.ValueCount(0.9, 10)])
    assert vc.count == 100
    assert vc.value == pytest.approx((0.2 * 90 + 0.9 * 10) / 100)  # 0.27


def test_weighted_mean_empty_is_none():
    assert m.weighted_mean([]) is None
    assert m.weighted_mean([m.ValueCount(0.5, 0)]) is None  # zero total count


def test_grade_sign_and_divisor_scaling():
    # mine better than ref by exactly one divisor -> +1.0
    assert m.grade(mine=0.30, ref=0.20, divisor=0.10) == pytest.approx(1.0)
    # worse -> negative; larger divisor -> smaller magnitude
    assert m.grade(0.20, 0.30, 0.10) == pytest.approx(-1.0)
    assert m.grade(0.30, 0.20, 0.20) == pytest.approx(0.5)


def test_grade_reverse_for_lower_is_better():
    # a LOWER blind rate than the reference should grade POSITIVE under reverse
    assert m.grade(0.10, 0.30, 0.20, reverse=True) == pytest.approx(1.0)
    # and a higher blind rate grades negative
    assert m.grade(0.50, 0.30, 0.20, reverse=True) == pytest.approx(-1.0)


def test_grade_rejects_nonpositive_divisor():
    with pytest.raises(ValueError):
        m.grade(0.3, 0.2, 0.0)


def test_importance_scales_with_sqrt_count_and_is_unsigned():
    # abs(grade) * sqrt(count * weight)
    assert m.importance(-2.0, count=9, weight=1.0) == pytest.approx(2.0 * 3.0)
    # 4x the sample -> 2x the importance (sqrt)
    base = m.importance(1.0, count=25)
    quad = m.importance(1.0, count=100)
    assert quad == pytest.approx(2 * base)
    # weight multiplies under the sqrt
    assert m.importance(1.0, 100, weight=0.0) == 0.0
    assert m.importance(1.0, 100, weight=35) == pytest.approx(math.sqrt(100 * 35))


def test_importance_ranks_wellsampled_over_thin_extreme():
    # the small-sample distortion the raw-count sort suffers from: a 1-game
    # 100%-blind opening must NOT outrank a well-sampled moderate weakness.
    thin = m.importance(m.grade(1.0, 0.2, 0.5, reverse=True), count=1)      # extreme, n=1
    solid = m.importance(m.grade(0.45, 0.2, 0.5, reverse=True), count=200)  # moderate, n=200
    assert solid > thin


# --- T2: DimAvg comparison + mixed_bag -------------------------------------

def test_compare_to_dim_avg_flags_the_outlier_weakness():
    # blind rate (lower is better). Three openings ~0.1, one at 0.40 -> the 0.40
    # one is the weakness: graded negative, ranked first by importance.
    points = [
        ("A40", m.ValueCount(0.10, 100)),
        ("A46", m.ValueCount(0.12, 90)),
        ("D02", m.ValueCount(0.11, 80)),
        ("C61", m.ValueCount(0.40, 60)),  # the leak
    ]
    comps = m.compare_to_dim_avg(points, divisor=0.10, reverse=True)
    assert comps[0].dim == "C61"
    assert comps[0].grade < 0  # weaker than the user's own baseline
    # its reference EXCLUDES itself: mean of the other three
    assert comps[0].ref_value == pytest.approx(
        (0.10 * 100 + 0.12 * 90 + 0.11 * 80) / 270, abs=1e-9)


def test_compare_to_dim_avg_reverse_flips_direction():
    points = [("x", m.ValueCount(0.5, 50)), ("y", m.ValueCount(0.1, 50))]
    fwd = {c.dim: c.grade for c in m.compare_to_dim_avg(points, 0.1)}
    rev = {c.dim: c.grade for c in m.compare_to_dim_avg(points, 0.1, reverse=True)}
    # higher-is-better: x (0.5) is the strength; reverse: x becomes the weakness
    assert fwd["x"] > 0 and rev["x"] < 0
    assert fwd["y"] < 0 and rev["y"] > 0


def test_compare_ranks_by_importance_not_raw_gap():
    # a thin dim with a big gap must NOT outrank a well-sampled moderate one
    points = [
        ("baseline1", m.ValueCount(0.20, 200)),
        ("baseline2", m.ValueCount(0.20, 200)),
        ("thin_extreme", m.ValueCount(0.60, 1)),
        ("solid_mod", m.ValueCount(0.35, 200)),
    ]
    comps = m.compare_to_dim_avg(points, divisor=0.10, reverse=True)
    ranks = [c.dim for c in comps]
    assert ranks.index("solid_mod") < ranks.index("thin_extreme")


def _cmp(dim, grade, imp):
    return m.DimComparison(dim=dim, value=0.0, count=100, ref_value=0.0,
                           grade=grade, importance=imp)


def test_mixed_bag_balances_weaknesses_and_strengths():
    comps = [_cmp("w1", -1, 10), _cmp("s1", 1, 9), _cmp("w2", -1, 8),
             _cmp("s2", 1, 7), _cmp("w3", -1, 6)]
    bag = m.mixed_bag(comps, 4)
    assert [c.dim for c in bag] == ["w1", "w2", "s1", "s2"]  # 2 + 2, weaknesses first


def test_mixed_bag_fills_from_weaknesses_when_strengths_short():
    comps = [_cmp("w1", -1, 10), _cmp("w2", -1, 9), _cmp("w3", -1, 8),
             _cmp("s1", 1, 7)]
    bag = m.mixed_bag(comps, 4)
    assert len(bag) == 4
    assert sum(1 for c in bag if c.grade < 0) == 3  # only one strength existed


def test_mixed_bag_empty_for_nonpositive_n():
    assert m.mixed_bag([_cmp("w1", -1, 10)], 0) == []


# --- T3: phase classifier + weakness_ranking assembler ---------------------

def test_classify_phase_opening_middlegame_endgame():
    import chess
    assert m.classify_phase(chess.Board().fen()) == "opening"  # startpos
    # bare kings + a couple pawns -> endgame (<= 6 non-pawn pieces)
    assert m.classify_phase("8/5k2/8/8/8/2K5/4P3/8 w - - 0 40") == "endgame"
    # full material, move 20 -> middlegame
    mid = "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQ1RK1 w - - 8 20"
    assert m.classify_phase(mid) == "middlegame"


def test_weakness_ranking_surfaces_the_leaky_opening():
    profile = {"aggregates": {"by_opening": {
        "A40": {"blind_rate": 0.10, "moves": 200},
        "A46": {"blind_rate": 0.12, "moves": 180},
        "D02": {"blind_rate": 0.11, "moves": 160},
        "C61": {"blind_rate": 0.40, "moves": 120},   # the leak
    }}}
    ranked = m.weakness_ranking(profile, n=4)
    assert ranked[0].dim == "C61"
    assert ranked[0].grade < 0  # weaker than the user's own baseline


def test_weakness_ranking_ignores_thin_lines_and_empty():
    # a thin (1-move) extreme must not top a well-sampled moderate weakness
    profile = {"aggregates": {"by_opening": {
        "BIG1": {"blind_rate": 0.20, "moves": 200},
        "BIG2": {"blind_rate": 0.20, "moves": 200},
        "THIN": {"blind_rate": 0.90, "moves": 1},
        "SOLID": {"blind_rate": 0.35, "moves": 200},
    }}}
    ranked = m.weakness_ranking(profile, n=4)
    dims = [c.dim for c in ranked]
    assert dims.index("SOLID") < dims.index("THIN")
    assert m.weakness_ranking({}, n=4) == []
    assert m.weakness_ranking({"aggregates": {"by_opening": {}}}) == []


# --- T-gen: rank_dimension (generic) + weakness_ranking_all -----------------

def test_rank_dimension_generic_phase_dict():
    by_phase = {
        "opening":    {"blind_rate": 0.14, "moves": 8000},
        "middlegame": {"blind_rate": 0.12, "moves": 7000},
        "endgame":    {"blind_rate": 0.07, "moves": 2000},
    }
    ranked = m.rank_dimension(by_phase, n=3)
    assert [c.dim for c in ranked][0] == "opening"      # worst vs own baseline
    assert ranked[0].grade < 0
    # endgame is the relative strength
    assert next(c for c in ranked if c.dim == "endgame").grade > 0
    assert m.rank_dimension({}) == []


def test_weakness_ranking_all_spans_dimensions():
    profile = {"aggregates": {
        "by_opening": {"A40": {"blind_rate": 0.30, "moves": 100},
                       "D02": {"blind_rate": 0.10, "moves": 100}},
        "by_phase":   {"opening": {"blind_rate": 0.14, "moves": 8000},
                       "endgame": {"blind_rate": 0.07, "moves": 2000}},
        "by_clock":   {"fast": {"blind_rate": 0.10, "moves": 4000},
                       "normal": {"blind_rate": 0.13, "moves": 12000}},
    }}
    allr = m.weakness_ranking_all(profile)
    assert set(allr.keys()) == {"openings", "phase", "clock"}
    assert allr["openings"][0].dim == "A40"
    assert {c.dim for c in allr["phase"]} == {"opening", "endgame"}
    assert {c.dim for c in allr["clock"]} == {"fast", "normal"}
    # backward-compat: weakness_ranking still returns just the openings list
    assert m.weakness_ranking(profile)[0].dim == "A40"


def test_weakness_ranking_all_missing_dims_are_empty():
    # an older profile without by_phase/by_clock (2 openings so there IS a
    # baseline to compare against — a single-bucket dimension has none).
    profile = {"aggregates": {"by_opening": {
        "A40": {"blind_rate": 0.3, "moves": 50},
        "D02": {"blind_rate": 0.1, "moves": 50},
    }}}
    allr = m.weakness_ranking_all(profile)
    assert allr["phase"] == [] and allr["clock"] == []
    assert len(allr["openings"]) == 2
    assert m.weakness_ranking_all({}) == {"openings": [], "phase": [], "clock": []}


def test_single_bucket_dimension_has_no_baseline():
    # self-relative ranking needs >= 2 buckets; one alone can't be graded.
    assert m.rank_dimension({"only": {"blind_rate": 0.5, "moves": 100}}) == []
