"""Ranking baselines the model has to beat.

Phase 3 found that ranking by age is not merely weak but wrong at the top:
cast iron hazard peaks at the 1950s-60s cohort, so age-ranking puts 1920s pipe
first when mid-century pipe is roughly twice as risky. The top of the list is
the only part anyone acts on, so `material_decade_rate` -- the empirical
failure rate of each material-and-vintage cell, learned from training years
only -- is the honest bar.

Every baseline is fitted on training data and applied to the test year, exactly
like a model. A baseline computed on the test year would be cheating in the
same way a leaky feature is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RNG_SEED = 42


def random_score(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Floor. Captures k% of breaks at k% of length, by construction."""
    return np.random.default_rng(RNG_SEED).random(len(test))


def age_score(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Oldest first -- the intuitive heuristic, and the one phase 3 undermined."""
    return test["age_years"].to_numpy(dtype=float)


def prior_breaks_score(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Most-broken first, ties broken by age.

    Strong overall and completely degenerate on never-broken pipes, where every
    value is zero. That contrast is the whole reason the scorecard is stratified.
    """
    return test["prior_break_count"].to_numpy(dtype=float) * 1000 + test["age_years"].to_numpy(
        dtype=float
    )


def _empirical_rate(
    train: pd.DataFrame, test: pd.DataFrame, keys: list[str], min_km: float = 5.0
) -> np.ndarray:
    """Break rate per km for each cell of `keys`, learned on train, applied to test.

    Cells with less than `min_km` of training exposure fall back to the global
    rate rather than to a number computed from a few hundred metres of pipe.
    """
    grouped = train.groupby(keys, observed=True).agg(
        breaks=("break_count", "sum"), km=("length_km", "sum")
    )
    global_rate = train["break_count"].sum() / max(train["length_km"].sum(), 1e-9)
    rates = np.where(grouped["km"] >= min_km, grouped["breaks"] / grouped["km"], global_rate)
    lookup = pd.Series(rates, index=grouped.index)

    keyed = pd.MultiIndex.from_frame(test[keys]) if len(keys) > 1 else pd.Index(test[keys[0]])
    return lookup.reindex(keyed).fillna(global_rate).to_numpy(dtype=float)


def decade_rate_score(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Rank by the historical failure rate of the pipe's installation decade."""
    return _empirical_rate(train, test, ["install_decade"])


def material_decade_rate_score(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Rank by the historical rate of the material-and-vintage cell.

    The bar the model has to clear. It encodes phase 3's finding directly and
    needs no fitting beyond a group-by.
    """
    return _empirical_rate(train, test, ["material", "install_decade"])


def condition_score_score(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Rank by the inventory's own condition score, worst first.

    *** THIS BASELINE LEAKS. It is retained as a leakage demonstration, is
    excluded from HONEST_BASELINES, and must never be quoted as a result. ***

    It outscores every model and every legitimate baseline -- 62% of breaks in
    the top 5% of network length among never-broken pipes -- which is what
    prompted the check. condition_score turns out to be a near-deterministic
    function of break count:

        breaks   0     1     2     3     4     5     6
        score    9.02  6.35  5.68  5.05  5.01  4.80  4.48

    and among pipes that had never broken as of 2022, those that went on to
    break in 2022-25 already carry a mean score of 7.17 against 9.02 for those
    that did not. The inventory snapshot is from September 2026, so the score
    was marked down in response to breaks that had not yet happened at
    prediction time. It is the outcome wearing a feature's clothes.

    Fixing this needs point-in-time condition scores, which is exactly what
    snap_water_mains starts accumulating -- but it can only do so from its first
    run forward, so this baseline stays unusable for historical evaluation.
    """
    scored = train.dropna(subset=["condition_score"])
    if scored.empty:
        return np.zeros(len(test))
    # Negative correlation with breaks means higher score = better condition.
    sign = -1.0 if scored["condition_score"].corr(scored["break_count"]) < 0 else 1.0
    filled = test["condition_score"].fillna(train["condition_score"].median())
    return sign * filled.to_numpy(dtype=float)


# Baselines that use only information available before the panel year begins.
HONEST_BASELINES = {
    "random": random_score,
    "age": age_score,
    "decade_rate": decade_rate_score,
    "material_decade_rate": material_decade_rate_score,
    "prior_breaks": prior_breaks_score,
}

# Reported separately and always labelled. See condition_score_score.
LEAKING_BASELINES = {
    "condition_score_LEAKS": condition_score_score,
}


def stratified_rate_score(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Empirical rate per km by (prior breaks, material, install decade).

    The unification of the two rules that actually work. Break history dominates
    for the ~6% of pipe-years that have any, and material-and-vintage carries the
    other 94%; keying on all three lets one lookup table serve both without a
    hand-written branch.

    Still just a group-by fitted on training years. That is the point -- it is
    auditable by the engineer who has to act on the list, and a colleague can
    reproduce it in SQL.
    """
    return _empirical_rate(train, test, ["prior_break_count_capped", "material", "install_decade"])


HONEST_BASELINES["stratified_rate"] = stratified_rate_score

BASELINES = {**HONEST_BASELINES, **LEAKING_BASELINES}
