"""Tests for the ranking metrics.

`capture@k` is the number the whole project reports, so it is worth pinning
against cases whose answer can be worked out by hand. The stratification tests
matter just as much: the phase 4 result turned entirely on the `all` row
disagreeing with both stratum rows, and a bug that collapsed the strata would
have hidden that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml import baselines, evaluate


def _frame(scores, breaks, lengths=None, has_prior=None) -> pd.DataFrame:
    n = len(scores)
    return pd.DataFrame(
        {
            "score": scores,
            "break_count": breaks,
            "broke_in_year": [1 if b else 0 for b in breaks],
            "length_km": lengths if lengths is not None else [1.0] * n,
            "has_prior_break": has_prior if has_prior is not None else [False] * n,
        }
    )


def test_perfect_ranking_captures_everything_early():
    frame = _frame(scores=list(range(10))[::-1], breaks=[1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    curve = evaluate.capture_at_k(frame, k_grid=(0.1, 0.2)).set_index("k")
    assert curve.loc[0.1, "captured"] == pytest.approx(0.5)
    assert curve.loc[0.2, "captured"] == pytest.approx(1.0)


def test_worst_ranking_captures_nothing_early():
    frame = _frame(scores=list(range(10)), breaks=[1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    curve = evaluate.capture_at_k(frame, k_grid=(0.2,)).set_index("k")
    assert curve.loc[0.2, "captured"] == pytest.approx(0.0)


def test_capture_is_length_weighted_not_segment_weighted():
    """One 10 km main ahead of nine 1 km stubs consumes the whole 5% budget.

    Ranking by segment count would call this a hit; ranking by length must not,
    because the crew has to dig the whole main.
    """
    frame = _frame(
        scores=[100] + list(range(9)),
        breaks=[1] + [0] * 9,
        lengths=[10.0] + [1.0] * 9,
    )
    curve = evaluate.capture_at_k(frame, k_grid=(0.05,)).set_index("k")
    # 5% of 19 km is 0.95 km -- not even the first segment fits.
    assert curve.loc[0.05, "captured"] == pytest.approx(0.0)


def test_lift_over_random_is_relative_to_budget():
    frame = _frame(scores=list(range(20))[::-1], breaks=[1] + [0] * 19)
    card = evaluate.scorecard(frame)
    # The single break sits in the top 5% of length, so capture is 1.0.
    assert card["capture@5%"] == pytest.approx(1.0)
    assert card["lift@5%"] == pytest.approx(20.0)


def test_stratified_scorecard_splits_on_break_history():
    frame = _frame(
        scores=[9, 8, 7, 6],
        breaks=[1, 0, 1, 0],
        has_prior=[True, True, False, False],
    )
    card = evaluate.stratified_scorecard(frame)
    assert set(card.index) == {"all", "has_prior_break", "no_prior_break"}
    assert card.loc["all", "n_breaks"] == 2
    assert card.loc["has_prior_break", "n_breaks"] == 1
    assert card.loc["no_prior_break", "n_breaks"] == 1


def test_stratum_with_no_positives_reports_counts_not_a_fake_auc():
    frame = _frame(scores=[3, 2, 1], breaks=[0, 0, 0])
    card = evaluate.scorecard(frame)
    assert card["n_breaks"] == 0
    assert np.isnan(card["pr_auc"])


def test_empirical_rate_baseline_is_fitted_on_train_only():
    """A baseline computed on the evaluation year would cheat exactly like a
    leaky feature. Cells unseen in training must fall back to the global rate."""
    train = pd.DataFrame(
        {
            "material": ["CI", "CI", "PVC", "PVC"],
            "install_decade": ["1950s"] * 2 + ["2000s"] * 2,
            "break_count": [10, 10, 0, 0],
            "length_km": [50.0, 50.0, 50.0, 50.0],
        }
    )
    test = pd.DataFrame(
        {
            "material": ["CI", "PVC", "DI"],
            "install_decade": ["1950s", "2000s", "1990s"],
        }
    )
    scores = baselines.material_decade_rate_score(train, test)
    assert scores[0] > scores[1], "cast iron cell must outrank the PVC cell"
    # The unseen DI cell falls back to the global rate: 20 breaks / 200 km.
    assert scores[2] == pytest.approx(0.1)


def test_prior_breaks_baseline_is_degenerate_on_never_broken_pipes():
    """The reason the scorecard is stratified: this baseline carries no
    information at all where every value is zero."""
    test = pd.DataFrame({"prior_break_count": [0, 0, 0], "age_years": [10, 50, 90]})
    scores = baselines.prior_breaks_score(pd.DataFrame(), test)
    # Ordering collapses to the age tiebreak alone.
    assert list(scores) == [10, 50, 90]
