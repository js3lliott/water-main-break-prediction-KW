"""Feature definitions and the panel loader.

Two feature sets, and the distinction is the point of this module:

`FULL` includes the pipe's own break history, which is by far the strongest
predictor available (a 12x rate gradient). But only ~6% of pipe-years belong to
a segment that has ever broken, so a model leaning on it is skilful exactly
where the city already knows the answer -- past breaks are in their work order
system -- and near-silent on the 94% of the network it does not.

`COLD_START` removes every own-history feature. It is the model that has to
work for a pipe with no record, and it leans on the neighbourhood features
instead: breaks on OTHER segments within 250 m, which within never-broken pipes
alone stratify risk 11.5x (2.1 -> 24.2 breaks per 100 km/yr) and hold a 2.3x
gradient after controlling for material and cohort.

Both are trained and both are reported, per stratum. A single headline number
over the whole panel would hide which half of the problem the model solves.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_WAREHOUSE = Path("data/warehouse.duckdb")

TARGET = "broke_in_year"
GRAIN = ["watmainid", "panel_year"]

# Attributes of the pipe itself, knowable without any failure record.
STATIC_NUMERIC = [
    "age_years",
    "install_year",
    "length_m",
    "diameter_mm",
    "criticality",
]
STATIC_CATEGORICAL = [
    "material",
    "install_decade",
    "pressure_zone",
    "ownership",
]
STATIC_BOOLEAN = [
    "is_lined",
    "is_undersized",
    "is_oversized",
    "is_shallow",
    "is_bridge_main",
    "is_cleaned",
]

# The pipe's own failure record. Dominant, and available for ~6% of pipe-years.
OWN_HISTORY = [
    "prior_break_count",
    "prior_break_count_capped",
    "years_since_last_break",
]

# Failures on neighbouring pipes. The cold-start signal.
NEIGHBOURHOOD = [
    "neighbour_breaks_prior_5y",
    "neighbour_breaks_prior_all",
    "neighbour_breaks_per_km_5y",
    "neighbour_pipe_km",
    "neighbour_pipe_count",
]

# Smoothed historical failure rate of the pipe's material-and-vintage cell,
# computed from TRAINING YEARS ONLY and attached per fold (see
# `add_rate_encoding`). This hands the model the material_decade_rate baseline
# as an input so it starts from that bar instead of having to rediscover the
# interaction from a few hundred positives.
RATE_ENCODING = ["material_decade_rate_prior"]

# Location history from a predecessor pipe. Kept separate from OWN_HISTORY --
# these locations were recently re-piped and run BELOW network average
# (1.8 vs 8.7 per 100 km/yr), so merging the two inverts the signal.
PREDECESSOR = ["predecessor_break_count"]

# Excluded on purpose:
#   condition_score  -- provenance unknown, may postdate the breaks it would
#                       predict. Handled as an explicit ablation, not silently.
#   winter features  -- describe weather that has already happened, so they
#                       cannot serve a forward-looking inspection list.
#   *_reported_*     -- denormalised copies of current inventory, not history.

FEATURE_SETS: dict[str, list[str]] = {
    "full": STATIC_NUMERIC
    + STATIC_CATEGORICAL
    + STATIC_BOOLEAN
    + OWN_HISTORY
    + NEIGHBOURHOOD
    + PREDECESSOR,
    "cold_start": STATIC_NUMERIC
    + STATIC_CATEGORICAL
    + STATIC_BOOLEAN
    + NEIGHBOURHOOD
    + PREDECESSOR,
    "full_encoded": STATIC_NUMERIC
    + STATIC_CATEGORICAL
    + STATIC_BOOLEAN
    + OWN_HISTORY
    + NEIGHBOURHOOD
    + PREDECESSOR
    + RATE_ENCODING,
}

CATEGORICAL = set(STATIC_CATEGORICAL)

# Columns carried for evaluation and reporting but never given to a model.
CARRY = [
    "length_km",
    "break_count",
    "has_prior_break",
    "material",
    "install_decade",
    "condition_score",
]


def load_panel(
    warehouse: Path | str = DEFAULT_WAREHOUSE,
    start_year: int = 2005,
    exclude_negligible: bool = True,
) -> pd.DataFrame:
    """Load the complete-year panel.

    Incomplete years are excluded: their outcomes are only partly observed, so
    including them would understate the positive rate. Sub-metre GIS connector
    artifacts are excluded because they distort any length-normalised metric.

    Panel history starts at 2005 by default rather than 1997 -- the
    neighbourhood features need a few years of break history behind them before
    they mean anything.
    """
    negligible = "and not is_negligible_length" if exclude_negligible else ""
    with duckdb.connect(str(warehouse), read_only=True) as con:
        frame = con.sql(f"""
            select * from main_marts.fct_pipe_year
            where is_complete_year
              and panel_year >= {start_year}
              {negligible}
            order by panel_year, watmainid
        """).df()

    frame[TARGET] = frame[TARGET].astype(int)
    for column in CATEGORICAL:
        frame[column] = frame[column].astype("category")
    for column in STATIC_BOOLEAN:
        frame[column] = frame[column].fillna(False).astype(int)

    # No prior break means no "years since" -- represent that as a large
    # sentinel rather than a null the tree has to guess at.
    frame["years_since_last_break"] = frame["years_since_last_break"].fillna(999)
    return frame


def feature_matrix(frame: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    """Select one feature set, leaving categoricals as pandas categories.

    LightGBM consumes those natively, which avoids one-hot columns with
    near-zero support -- a real risk here, where several materials cover under
    60 segments.
    """
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"unknown feature set {feature_set!r}; have {list(FEATURE_SETS)}")
    return frame[FEATURE_SETS[feature_set]].copy()


def add_rate_encoding(
    train: pd.DataFrame,
    frames: list[pd.DataFrame],
    keys: tuple[str, ...] = ("material", "install_decade"),
    smoothing: float = 20.0,
) -> list[pd.DataFrame]:
    """Attach a smoothed material-and-vintage failure rate, fitted on `train`.

    The rate is breaks per km within each cell, shrunk toward the global rate in
    proportion to how little exposure the cell has:

        rate = (breaks + smoothing * global_rate) / (km + smoothing)

    Fitting on the training frame only is what keeps this honest -- an encoding
    computed over all years would carry the outcome of the year being predicted
    straight into a feature, which is the same mistake as the leaky
    condition_score, just self-inflicted.
    """
    global_rate = train["break_count"].sum() / max(train["length_km"].sum(), 1e-9)
    grouped = train.groupby(list(keys), observed=True).agg(
        breaks=("break_count", "sum"), km=("length_km", "sum")
    )
    smoothed = (grouped["breaks"] + smoothing * global_rate) / (grouped["km"] + smoothing)

    out = []
    for frame in frames:
        keyed = pd.MultiIndex.from_frame(frame[list(keys)])
        copy = frame.copy()
        copy["material_decade_rate_prior"] = (
            smoothed.reindex(keyed).fillna(global_rate).to_numpy(dtype=float)
        )
        out.append(copy)
    return out
