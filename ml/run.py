"""Run the phase 4 evaluation and write the report.

    python -m ml.run

Evaluation is walk-forward across ten years rather than a single held-out
window. With roughly 20-40 breaks per year in the stratum that matters, one
window is far too noisy to separate a model from a baseline -- an early version
of this script showed the model beating the baseline on the 2022-2025 window
and losing to it across ten years.

Everything is reported per stratum. The `all` row is the number people quote
and the least informative: pipes with break history are 6% of pipe-years and
over half the breaks, so a model that only re-finds them looks strong overall
while adding nothing the city's work-order system does not already tell them.
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import pandas as pd

from ml import evaluate, features, train
from ml.baselines import BASELINES

warnings.filterwarnings("ignore")
logger = logging.getLogger("ml")

WALK_FORWARD_YEARS = (2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
MODELS = ("full", "cold_start", "full_encoded")
PRIMARY_METRIC = "capture@5%"
REFERENCE = "baseline:material_decade_rate"


def walk_forward(panel: pd.DataFrame, years: tuple[int, ...] = WALK_FORWARD_YEARS) -> pd.DataFrame:
    """Score every model and baseline on each year, training only on prior years."""
    records = []
    for year in years:
        raw_train = panel[panel["panel_year"] < year]
        raw_valid = panel[panel["panel_year"] == year]
        if raw_train.empty or raw_valid.empty:
            continue

        # The rate encoding must be fitted on training years only.
        enc_train, enc_valid = features.add_rate_encoding(raw_train, [raw_train, raw_valid])

        scored: dict[str, pd.Series] = {}
        for feature_set in MODELS:
            model = train.fit_lgbm(enc_train, feature_set)
            scored[f"model:{feature_set}"] = train.predict(model, enc_valid, feature_set)
        for name, fn in BASELINES.items():
            scored[f"baseline:{name}"] = fn(raw_train, raw_valid)

        for name, values in scored.items():
            frame = raw_valid.copy()
            frame["score"] = values
            card = evaluate.stratified_scorecard(frame)
            for stratum in card.index:
                records.append(
                    {
                        "year": year,
                        "method": name,
                        "stratum": stratum,
                        **card.loc[stratum].to_dict(),
                    }
                )
        logger.info("walk-forward %s done", year)

    return pd.DataFrame(records)


def summarise(folds: pd.DataFrame, stratum: str) -> pd.DataFrame:
    """Mean/median primary metric per method, plus how often it beats the reference."""
    subset = folds[folds["stratum"] == stratum]
    wide = subset.pivot_table(index="year", columns="method", values=PRIMARY_METRIC)
    if REFERENCE not in wide.columns:
        return pd.DataFrame()

    rows = {}
    for method in wide.columns:
        wins = int((wide[method] > wide[REFERENCE]).sum())
        rows[method] = {
            "mean": wide[method].mean(),
            "median": wide[method].median(),
            "min": wide[method].min(),
            "max": wide[method].max(),
            f"years_beating_{REFERENCE.split(':')[-1]}": wins,
            "n_years": int(wide[method].notna().sum()),
        }
    return pd.DataFrame(rows).T.sort_values("mean", ascending=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 walk-forward evaluation.")
    parser.add_argument("--warehouse", type=Path, default=features.DEFAULT_WAREHOUSE)
    parser.add_argument("--output-dir", type=Path, default=Path("ml/results"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    pd.set_option("display.width", 240)

    panel = features.load_panel(args.warehouse)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "panel %s rows, %.3f%% positive", f"{len(panel):,}", 100 * panel[features.TARGET].mean()
    )

    folds = walk_forward(panel)
    folds.to_csv(args.output_dir / "walk_forward_folds.csv", index=False)

    for stratum in ("all", "has_prior_break", "no_prior_break"):
        table = summarise(folds, stratum)
        header = f"{PRIMARY_METRIC} across {len(WALK_FORWARD_YEARS)} years"
        print(f"\n===== {header} -- stratum: {stratum} =====")
        print(table.round(3).to_string())
        table.to_csv(args.output_dir / f"walk_forward_{stratum}.csv")

    print("\nNOTE: condition_score_LEAKS is a leakage demonstration, not a result.")
    logger.info("results written to %s", args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
