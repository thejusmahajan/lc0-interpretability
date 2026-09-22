"""Guards for Phi's probability calibration (phi_net/calibrate.py), 2026-09-03.

Phi's raw sigmoid is over-spread: on the held-out test split the 0.7-0.8 bin
predicted 0.749 against an actual rate of 0.654. The UI renders that as
"Risk: 75%", which is a coach overstating its confidence.

The load-bearing property is that isotonic regression is **rank-preserving**, so
calibration cannot change the steering order -- only the number displayed.
"""

import numpy as np

from phi_net.calibrate import (apply_calibration, decile_table,
                               expected_calibration_error, fit_isotonic)


def test_isotonic_output_is_non_decreasing():
    rng = np.random.default_rng(0)
    x = rng.random(500)
    y = (rng.random(500) < x).astype(float)
    _, fitted = fit_isotonic(x, y)
    assert np.all(np.diff(fitted) >= -1e-12)


def test_calibration_preserves_order():
    """The property everything else rests on: if Phi ranked A above B, it still
    does after calibration. Steering order is therefore untouched."""
    rng = np.random.default_rng(1)
    x = rng.random(400)
    y = (rng.random(400) < x).astype(float)
    knots_x, knots_y = fit_isotonic(x, y)
    probe = np.sort(rng.random(100))
    out = apply_calibration(probe, knots_x, knots_y)
    assert np.all(np.diff(out) >= -1e-12)


def test_calibration_fixes_a_systematically_overconfident_model():
    """Reproduces Phi's actual defect in miniature: predictions pushed toward the
    extremes relative to the true rate."""
    rng = np.random.default_rng(2)
    true_p = rng.random(4000)
    y = (rng.random(4000) < true_p).astype(float)
    over = np.clip(true_p + 0.35 * (true_p - 0.5), 0.0, 1.0)   # over-spread

    ece_before = expected_calibration_error(decile_table(y, over))
    knots_x, knots_y = fit_isotonic(over, y)
    ece_after = expected_calibration_error(decile_table(y, apply_calibration(over, knots_x, knots_y)))

    assert ece_after < ece_before / 2, f"{ece_before:.4f} -> {ece_after:.4f}"


def test_apply_clips_outside_the_fitted_range():
    knots_x, knots_y = fit_isotonic(np.array([0.3, 0.5, 0.7]), np.array([0.0, 1.0, 1.0]))
    out = apply_calibration(np.array([0.0, 1.0]), knots_x, knots_y)
    assert out[0] == knots_y[0] and out[1] == knots_y[-1]


def test_decile_table_covers_every_row():
    rng = np.random.default_rng(3)
    p = rng.random(1000)
    y = (rng.random(1000) < p).astype(float)
    assert sum(r["n"] for r in decile_table(y, p)) == 1000
