"""Score the forecast year and write the inspection list back to the warehouse.

    python -m ml.score

Produces `main_scores.fct_pipe_risk_score`: one row per pipe for the year
ahead, ranked, with the evidence behind each score and a running kilometre
budget so the list can be cut at whatever length the city can actually inspect.

Two scores are written per pipe. `score_per_100km` comes from the
StratifiedRateRanker and is the one to act on. `challenger_score` comes from the
LightGBM model, which phase 4 found does not beat the lookup table -- it is kept
so the comparison keeps running on new data rather than being settled once in a
document. If the challenger starts winning, that is worth knowing.

The table is written by this module, not by dbt, and lives in its own schema to
keep that ownership boundary visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ml import features, train
from ml.ranker import StratifiedRateRanker

logger = logging.getLogger("ml.score")

SCORE_SCHEMA = "main_scores"
SCORE_TABLE = "fct_pipe_risk_score"
FQ_TABLE = f"{SCORE_SCHEMA}.{SCORE_TABLE}"

# Budgets the app surfaces, as a share of total network length.
BUDGET_GRID = (0.01, 0.02, 0.05, 0.10)


def load_scoring_frames(warehouse: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Complete years for fitting, the forecast year for scoring."""
    with duckdb.connect(str(warehouse), read_only=True) as con:
        panel = con.sql("""
            select * from main_marts.fct_pipe_year
            where is_complete_year and panel_year >= 2005 and not is_negligible_length
        """).df()
        # Negligible-length segments are excluded from the list for the same
        # reason they are excluded from fitting: they are sub-metre GIS
        # connector artifacts, not pipe anyone can inspect. Leaving them in put
        # 80 cm stubs at the top of the first list this produced, because they
        # share a cell rate with real pipe and win the shortest-first tiebreak.
        forecast = con.sql("""
            select * from main_marts.fct_pipe_year
            where is_forecast_year and not is_negligible_length
        """).df()

    for frame in (panel, forecast):
        frame[features.TARGET] = frame[features.TARGET].astype(int)
        for column in features.CATEGORICAL:
            frame[column] = frame[column].astype("category")
        for column in features.STATIC_BOOLEAN:
            frame[column] = frame[column].fillna(False).astype(int)
        frame["years_since_last_break"] = frame["years_since_last_break"].fillna(999)

    # Categories must match between fit and predict or LightGBM silently
    # reindexes them and the challenger scores garbage.
    for column in features.CATEGORICAL:
        union = panel[column].cat.categories.union(forecast[column].cat.categories)
        panel[column] = panel[column].cat.set_categories(union)
        forecast[column] = forecast[column].cat.set_categories(union)

    return panel, forecast


def build_inspection_list(
    ranker: StratifiedRateRanker,
    forecast: pd.DataFrame,
    challenger_scores: np.ndarray | None,
    challenger_version: str | None,
) -> pd.DataFrame:
    """Rank the forecast year and attach the running budget."""
    scores = ranker.predict(forecast)
    out = pd.DataFrame(
        {
            "watmainid": forecast["watmainid"].to_numpy(),
            "target_year": forecast["panel_year"].to_numpy(),
            "length_km": forecast["length_km"].to_numpy(),
            "score_per_100km": 100.0 * scores,
            # Rate x length. Not the ranking quantity -- ranking on it would
            # favour long pipes under a length budget -- but it is what lets the
            # app say "these 47 km are expected to produce N breaks".
            "expected_breaks": scores * forecast["length_km"].to_numpy(),
        }
    )
    out = pd.concat([out, ranker.explain(forecast).reset_index(drop=True)], axis=1)

    if challenger_scores is not None:
        out["challenger_score"] = challenger_scores
        out["challenger_rank"] = (
            pd.Series(challenger_scores).rank(ascending=False, method="first").astype(int)
        )
    else:
        out["challenger_score"] = np.nan
        out["challenger_rank"] = pd.NA

    # Ties are pervasive by construction -- 111 cells across ~15,500 segments --
    # so most of the list is ordered by the tiebreak, not the score. Shortest
    # first matches how capture@k is measured in ml.evaluate, which keeps the
    # published 30% figure true of the list this actually produces.
    #
    # It does mean a precise rank within a cell carries no information. The app
    # should show the cell and its rate, not imply that #204 is riskier than
    # #205.
    out = out.sort_values(["score_per_100km", "length_km"], ascending=[False, True])
    out["rank"] = np.arange(1, len(out) + 1)
    out["cumulative_km"] = out["length_km"].cumsum()
    out["cumulative_expected_breaks"] = out["expected_breaks"].cumsum()
    out["pct_of_network_km"] = out["cumulative_km"] / out["length_km"].sum()

    out["method_version"] = ranker.version
    out["challenger_version"] = challenger_version
    out["scored_at"] = pd.Timestamp.now(tz="UTC")
    return out.reset_index(drop=True)


def drift_report(con: duckdb.DuckDBPyConnection, new: pd.DataFrame) -> dict | None:
    """Compare this run's score distribution to the previous one.

    A ranker refitted on a year of new data should move a little. A large jump
    means something upstream changed -- a join fanned out, a material got
    recoded, an extract came back short -- and the scores should not be trusted
    until someone has looked.
    """
    exists = con.sql(f"""
        select count(*) as n from information_schema.tables
        where table_schema = '{SCORE_SCHEMA}' and table_name = '{SCORE_TABLE}'
    """).fetchone()[0]
    if not exists:
        return None

    previous = con.sql(f"""
        select score_per_100km from {FQ_TABLE}
        where scored_at = (select max(scored_at) from {FQ_TABLE})
    """).df()
    if previous.empty:
        return None

    quantiles = [0.5, 0.9, 0.99]
    old_q = previous["score_per_100km"].quantile(quantiles)
    new_q = new["score_per_100km"].quantile(quantiles)
    report = {
        f"p{int(q * 100)}": {
            "previous": round(float(old_q.loc[q]), 3),
            "current": round(float(new_q.loc[q]), 3),
            "pct_change": round(
                100 * (new_q.loc[q] - old_q.loc[q]) / max(abs(old_q.loc[q]), 1e-9), 1
            ),
        }
        for q in quantiles
    }
    report["n_previous"] = int(len(previous))
    report["n_current"] = int(len(new))
    worst = max(abs(report[f"p{int(q * 100)}"]["pct_change"]) for q in quantiles)
    report["max_abs_pct_change"] = float(worst)
    # Plain bool, not numpy.bool_, or json.dumps refuses it.
    report["flagged"] = bool(worst > 25.0)
    return report


def write_scores(warehouse: Path, scores: pd.DataFrame) -> dict | None:
    """Append this run to the score table, keeping prior runs for comparison."""
    with duckdb.connect(str(warehouse)) as con:
        con.sql(f"create schema if not exists {SCORE_SCHEMA}")
        drift = drift_report(con, scores)
        con.register("new_scores", scores)
        exists = con.sql(f"""
            select count(*) from information_schema.tables
            where table_schema = '{SCORE_SCHEMA}' and table_name = '{SCORE_TABLE}'
        """).fetchone()[0]
        if exists:
            con.sql(f"insert into {FQ_TABLE} select * from new_scores")
        else:
            con.sql(f"create table {FQ_TABLE} as select * from new_scores")
        con.unregister("new_scores")
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the forecast year.")
    parser.add_argument("--warehouse", type=Path, default=features.DEFAULT_WAREHOUSE)
    parser.add_argument("--output-dir", type=Path, default=Path("ml/results"))
    parser.add_argument(
        "--no-challenger", action="store_true", help="skip the LightGBM comparison score"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    panel, forecast = load_scoring_frames(args.warehouse)
    if forecast.empty:
        logger.error("no forecast-year rows; rebuild the warehouse with `make transform`")
        return 1
    target_year = int(forecast["panel_year"].iloc[0])
    logger.info(
        "fitting on %s complete pipe-years (%s-%s), scoring %s",
        f"{len(panel):,}",
        int(panel["panel_year"].min()),
        int(panel["panel_year"].max()),
        target_year,
    )

    ranker = StratifiedRateRanker().fit(panel)
    logger.info("ranker %s: %s cells", ranker.version, len(ranker.table_))

    challenger_scores, challenger_version = None, None
    if not args.no_challenger:
        model = train.fit_lgbm(panel, "full")
        challenger_scores = train.predict(model, forecast, "full")
        challenger_version = (
            "lgbm-"
            + hashlib.sha256(
                json.dumps(model.get_params(), sort_keys=True, default=str).encode()
            ).hexdigest()[:12]
        )
        logger.info("challenger %s: %s trees", challenger_version, model.n_estimators_)

    scores = build_inspection_list(ranker, forecast, challenger_scores, challenger_version)
    drift = write_scores(args.warehouse, scores)

    total_km = scores["length_km"].sum()
    print(f"\n===== INSPECTION LIST FOR {target_year} =====")
    print(f"network: {len(scores):,} segments, {total_km:.0f} km\n")
    rows = []
    total_expected = scores["expected_breaks"].sum()
    for budget in BUDGET_GRID:
        cut = scores[scores["pct_of_network_km"] <= budget]
        caught = cut["expected_breaks"].sum()
        rows.append(
            {
                "budget": f"{budget:.0%}",
                "km": round(cut["length_km"].sum(), 1),
                "segments": len(cut),
                "expected_breaks": round(caught, 1),
                "share_of_expected": f"{caught / total_expected:.0%}",
            }
        )
    print(pd.DataFrame(rows).to_string(index=False))

    # Within a cell every segment carries the same rate, so a per-segment rank
    # is arbitrary -- an empirical check across eight years put the two opposite
    # tiebreaks 0.9 points apart, inside the noise. The cell is the unit that
    # carries information, so that is what gets shown.
    print("\n===== RISK CELLS, WORST FIRST =====")
    cells = (
        scores.groupby("risk_cell", observed=True)
        .agg(
            segments=("watmainid", "size"),
            km=("length_km", "sum"),
            rate_per_100km=("score_per_100km", "first"),
            expected_breaks=("expected_breaks", "sum"),
            evidence_breaks=("cell_breaks", "first"),
        )
        .sort_values("rate_per_100km", ascending=False)
        .head(10)
        .round(2)
    )
    print(cells.to_string())

    print("\n===== TOP 10 SEGMENTS (length in metres) =====")
    top = scores.head(10)[["rank", "watmainid", "risk_cell", "score_per_100km"]].copy()
    top["length_m"] = (scores.head(10)["length_km"] * 1000).round(0)
    print(top.round(2).to_string(index=False))

    if drift:
        print("\n===== SCORE DRIFT vs PREVIOUS RUN =====")
        print(json.dumps(drift, indent=2))
        if drift["flagged"]:
            logger.warning("score distribution moved >25%%; check upstream before acting")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    scores.to_csv(args.output_dir / f"inspection_list_{target_year}.csv", index=False)
    logger.info("wrote %s rows to %s", f"{len(scores):,}", FQ_TABLE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
