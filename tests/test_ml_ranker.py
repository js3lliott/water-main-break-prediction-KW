"""Tests for the shipped ranker and the scoring pipeline.

The ranker is a lookup table, so most of what can go wrong is not arithmetic
but discipline: fitting on the wrong rows, silently scoring a cell it has never
seen, or producing a version that does not move when the table does.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.ranker import StratifiedRateRanker
from ml.score import build_inspection_list


def _train(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "prior_break_count_capped",
            "material",
            "install_decade",
            "break_count",
            "length_km",
            "panel_year",
            "is_complete_year",
        ],
    )


BASE = _train(
    [
        (0, "CI", "1950s", 40, 100.0, 2020, True),
        (0, "PVC", "2000s", 1, 100.0, 2020, True),
        (3, "CI", "1950s", 60, 50.0, 2020, True),
    ]
)


def test_fit_refuses_incomplete_years():
    """An incomplete year has partly observed outcomes; fitting on it would put
    the answer into the score."""
    bad = BASE.copy()
    bad.loc[0, "is_complete_year"] = False
    with pytest.raises(ValueError, match="complete years only"):
        StratifiedRateRanker().fit(bad)


def test_rate_ordering_follows_the_data():
    ranker = StratifiedRateRanker(smoothing_km=0.0).fit(BASE)
    test = BASE[["prior_break_count_capped", "material", "install_decade"]]
    scores = ranker.predict(test)
    # 60/50 > 40/100 > 1/100
    assert scores[2] > scores[0] > scores[1]


def test_smoothing_shrinks_thin_cells_toward_the_global_rate():
    """A cell holding a few hundred metres must not outrank one built on
    kilometres just because its numerator happened to be non-zero."""
    thin = pd.concat([BASE, _train([(1, "CPP", "1980s", 1, 0.1, 2020, True)])], ignore_index=True)
    unsmoothed = StratifiedRateRanker(smoothing_km=0.0).fit(thin)
    smoothed = StratifiedRateRanker(smoothing_km=20.0).fit(thin)
    cell = pd.DataFrame(
        {"prior_break_count_capped": [1], "material": ["CPP"], "install_decade": ["1980s"]}
    )
    assert unsmoothed.predict(cell)[0] == pytest.approx(10.0)  # 1 break / 0.1 km
    assert smoothed.predict(cell)[0] < 1.0


def test_unseen_cell_falls_back_to_the_global_rate():
    ranker = StratifiedRateRanker().fit(BASE)
    unseen = pd.DataFrame(
        {"prior_break_count_capped": [0], "material": ["HDPE"], "install_decade": ["2020s"]}
    )
    assert ranker.predict(unseen)[0] == pytest.approx(ranker.global_rate_)
    assert bool(ranker.explain(unseen)["cell_is_unseen"].iloc[0]) is True


def test_version_is_stable_for_identical_data_and_moves_when_the_table_does():
    a = StratifiedRateRanker().fit(BASE)
    b = StratifiedRateRanker().fit(BASE.copy())
    assert a.version == b.version

    changed = BASE.copy()
    changed.loc[0, "break_count"] = 999
    assert StratifiedRateRanker().fit(changed).version != a.version


def test_explain_reports_the_evidence_behind_a_score():
    ranker = StratifiedRateRanker().fit(BASE)
    out = ranker.explain(BASE)
    assert out.loc[2, "risk_cell"] == "3 | CI | 1950s"
    assert out.loc[2, "cell_breaks"] == 60
    assert out.loc[2, "cell_exposure_km"] == pytest.approx(50.0)


def test_inspection_list_is_ranked_and_cumulative():
    ranker = StratifiedRateRanker(smoothing_km=0.0).fit(BASE)
    forecast = BASE.copy()
    forecast["watmainid"] = [1, 2, 3]
    forecast["panel_year"] = 2027

    out = build_inspection_list(ranker, forecast, None, None)

    assert list(out["rank"]) == [1, 2, 3]
    assert out["score_per_100km"].is_monotonic_decreasing
    assert out["cumulative_km"].is_monotonic_increasing
    assert out["cumulative_km"].iloc[-1] == pytest.approx(forecast["length_km"].sum())
    assert out["pct_of_network_km"].iloc[-1] == pytest.approx(1.0)
    # The worst cell (60 breaks / 50 km) must lead.
    assert out["watmainid"].iloc[0] == 3


def test_expected_breaks_is_rate_times_length_not_the_ranking_key():
    """Ranking on expected breaks would push long pipe up the list purely for
    being long, which is wrong under a budget measured in kilometres.

    The forecast frame is built separately from the training frame so the
    lengths being scored are not the lengths the rates were fitted on -- which
    is also how the real pipeline works.
    """
    ranker = StratifiedRateRanker(smoothing_km=0.0).fit(BASE)
    # Fitted rates: (0, CI, 1950s) = 0.4/km, (3, CI, 1950s) = 1.2/km.
    forecast = pd.DataFrame(
        {
            "watmainid": [1, 2],
            "panel_year": [2027, 2027],
            "prior_break_count_capped": [0, 3],
            "material": ["CI", "CI"],
            "install_decade": ["1950s", "1950s"],
            # 0.4 x 100 km = 40 expected, against 1.2 x 10 km = 12.
            "length_km": [100.0, 10.0],
        }
    )
    out = build_inspection_list(ranker, forecast, None, None).set_index("watmainid")

    assert out.loc[1, "expected_breaks"] > out.loc[2, "expected_breaks"]
    # ...and yet the short, high-rate segment ranks first, because the budget
    # is spent in kilometres.
    assert out.loc[2, "rank"] < out.loc[1, "rank"]


def test_challenger_scores_are_carried_but_do_not_reorder_the_list():
    ranker = StratifiedRateRanker(smoothing_km=0.0).fit(BASE)
    forecast = BASE.copy()
    forecast["watmainid"] = [1, 2, 3]
    forecast["panel_year"] = 2027
    challenger = np.array([9.0, 9.0, 0.0])  # exactly opposite to the ranker

    out = build_inspection_list(ranker, forecast, challenger, "lgbm-test")
    assert out["watmainid"].iloc[0] == 3, "the challenger must not drive the ranking"
    assert out["challenger_version"].iloc[0] == "lgbm-test"
    assert set(out["challenger_rank"]) == {1, 2, 3}
