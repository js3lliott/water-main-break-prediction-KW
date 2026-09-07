"""Evaluation for a ranked inspection list.

The headline metric is deliberately not AUC. At a 0.5% positive rate ROC-AUC
flatters everything, and neither it nor PR-AUC answers the question the city
actually asks, which is:

    "If we can inspect N kilometres of pipe next year, how many of next year's
     breaks do we catch?"

So the primary metric is `breaks captured at k% of network length` -- rank
every segment by score, walk down the list accumulating kilometres, and read
off the share of that year's breaks contained in the top k%. It is expressed in
length rather than segment count because a 300 m main and a 12 m stub are not
equivalent units of work.

Everything is reported per stratum. A single number over the whole panel is
misleading here: pipes that have broken before are 6% of pipe-years and 56% of
breaks, so a model that only re-finds them scores well overall while saying
almost nothing about the 94% of the network the city has no failure record for.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

# Inspection budgets worth quoting. 1-10% of ~930 km is 9-93 km of pipe, which
# spans the range a mid-sized municipality might actually renew in a year.
DEFAULT_K_GRID = (0.01, 0.02, 0.05, 0.10, 0.20)

STRATA = {
    "all": lambda df: pd.Series(True, index=df.index),
    "has_prior_break": lambda df: df["has_prior_break"].astype(bool),
    "no_prior_break": lambda df: ~df["has_prior_break"].astype(bool),
}


def capture_at_k(
    frame: pd.DataFrame,
    score: str = "score",
    k_grid: tuple[float, ...] = DEFAULT_K_GRID,
    length_col: str = "length_km",
    outcome_col: str = "break_count",
) -> pd.DataFrame:
    """Share of breaks contained in the top k% of network length.

    Ties are broken by length ascending, so a model that cannot separate two
    segments is credited with inspecting the cheaper one first. That is the
    conservative choice: it neither rewards nor punishes indifference.
    """
    if frame.empty or frame[outcome_col].sum() == 0:
        return pd.DataFrame({"k": k_grid, "captured": np.nan, "km": np.nan})

    ranked = frame.sort_values([score, length_col], ascending=[False, True])
    cum_km = ranked[length_col].cumsum()
    cum_breaks = ranked[outcome_col].cumsum()
    total_km = ranked[length_col].sum()
    total_breaks = ranked[outcome_col].sum()

    rows = []
    for k in k_grid:
        budget = total_km * k
        # Segments fully inside the budget; searchsorted gives the cut point.
        idx = int(np.searchsorted(cum_km.to_numpy(), budget, side="right"))
        captured = cum_breaks.iloc[idx - 1] / total_breaks if idx > 0 else 0.0
        rows.append({"k": k, "captured": captured, "km": budget, "n_segments": idx})
    return pd.DataFrame(rows)


def scorecard(
    frame: pd.DataFrame,
    score: str = "score",
    target: str = "broke_in_year",
    k_grid: tuple[float, ...] = DEFAULT_K_GRID,
) -> dict[str, float]:
    """Metrics for one stratum."""
    out: dict[str, float] = {
        "n_pipe_years": len(frame),
        "n_breaks": int(frame[target].sum()),
        "positive_rate": float(frame[target].mean()) if len(frame) else np.nan,
        "km": float(frame["length_km"].sum()),
    }

    if frame[target].nunique() < 2:
        # A stratum with no positives (or all positives) admits no ranking
        # metric. Report the counts and leave the rest missing rather than
        # emitting a misleading 0.5.
        out.update({"pr_auc": np.nan, "roc_auc": np.nan, "brier": np.nan})
    else:
        out["pr_auc"] = float(average_precision_score(frame[target], frame[score]))
        out["roc_auc"] = float(roc_auc_score(frame[target], frame[score]))
        # Only meaningful for a calibrated probability, not a bare ranking.
        if frame[score].between(0, 1).all():
            out["brier"] = float(brier_score_loss(frame[target], frame[score]))
        else:
            out["brier"] = np.nan

    curve = capture_at_k(frame, score=score, k_grid=k_grid)
    for _, row in curve.iterrows():
        out[f"capture@{row.k:.0%}"] = float(row.captured)

    # Lift over random at the 5% budget: random capture is k, by construction.
    five = out.get("capture@5%", np.nan)
    out["lift@5%"] = five / 0.05 if five == five else np.nan
    return out


def stratified_scorecard(
    frame: pd.DataFrame,
    score: str = "score",
    target: str = "broke_in_year",
    k_grid: tuple[float, ...] = DEFAULT_K_GRID,
) -> pd.DataFrame:
    """The headline table: one row per stratum.

    `no_prior_break` is the row that matters operationally. It covers the
    segments the city has no failure record for, which is where a model earns
    its keep -- and where ranking by break history is by definition useless,
    because every value is zero.
    """
    rows = {}
    for name, mask_fn in STRATA.items():
        subset = frame[mask_fn(frame)]
        if subset.empty:
            continue
        rows[name] = scorecard(subset, score=score, target=target, k_grid=k_grid)
    return pd.DataFrame(rows).T


def calibration_table(
    frame: pd.DataFrame, score: str = "score", target: str = "broke_in_year", bins: int = 10
) -> pd.DataFrame:
    """Predicted probability against observed frequency, by score decile.

    A stated 3% risk has to mean 3%, or the inspection list cannot be budgeted
    against -- "how many breaks will these 40 km produce" is unanswerable from
    an uncalibrated ranking.
    """
    work = frame[[score, target]].copy()
    work["bucket"] = pd.qcut(work[score].rank(method="first"), bins, labels=False)
    return (
        work.groupby("bucket")
        .agg(
            n=(target, "size"),
            predicted=(score, "mean"),
            observed=(target, "mean"),
        )
        .reset_index()
    )


def compare(scorecards: dict[str, pd.DataFrame], stratum: str = "all") -> pd.DataFrame:
    """Line up several models/baselines on one stratum for side-by-side reading."""
    rows = {}
    for name, card in scorecards.items():
        if stratum in card.index:
            rows[name] = card.loc[stratum]
    return pd.DataFrame(rows).T
