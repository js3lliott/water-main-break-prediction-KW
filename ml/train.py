"""Training with rolling-origin temporal validation.

Never a random split. A pipe's 2015 break landing in train while its 2014 break
lands in test would let the model see the future, and the original pipeline's
`train_test_split(random_state=42)` did exactly that.

Folds walk forward one year at a time; the final model trains on everything
through `TRAIN_THROUGH` and is scored once on the held-out years after it.
"""

from __future__ import annotations

import logging

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml import features
from ml.baselines import BASELINES

logger = logging.getLogger(__name__)

TRAIN_THROUGH = 2021
TEST_YEARS = (2022, 2023, 2024, 2025)
CV_VAL_YEARS = (2018, 2019, 2020, 2021)

# Tuned for rare positives rather than for leaderboard scores: shallow trees,
# a high minimum leaf size so a leaf cannot be one break, and heavy subsampling.
LGBM_PARAMS = {
    "objective": "binary",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "max_depth": 6,
    "min_child_samples": 100,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "n_estimators": 600,
    "verbosity": -1,
    "random_state": 42,
}


def fit_lgbm(
    train: pd.DataFrame,
    feature_set: str,
    params: dict | None = None,
    early_stopping_years: int = 3,
) -> lgb.LGBMClassifier:
    """Fit one gradient-boosted classifier.

    Early stopping uses the last `early_stopping_years` of the TRAINING data,
    never the year being scored. Passing the evaluation year here would tune the
    stopping point on the outcome being predicted -- a quieter version of the
    same mistake as a leaky feature.

    The stopping metric is AUC rather than average precision. At a 0.5% base
    rate with 20-40 positives in a single year, AP is so noisy that it can peak
    on the first tree and never recover; an earlier version of this function did
    exactly that and silently trained one-tree "ensembles" that then lost to a
    SQL group-by.
    """
    params = {**LGBM_PARAMS, **(params or {})}

    years = sorted(train["panel_year"].unique())
    if len(years) > early_stopping_years + 2:
        cutoff = years[-early_stopping_years]
        core = train[train["panel_year"] < cutoff]
        holdout = train[train["panel_year"] >= cutoff]
    else:
        core, holdout = train, None

    positives = core[features.TARGET].sum()
    negatives = len(core) - positives
    # Reweight rather than resample: resampling would destroy the calibration
    # the inspection list needs. Full inverse weighting overshoots badly at this
    # base rate, so the square root is used as a middle ground.
    params["scale_pos_weight"] = float(negatives / max(positives, 1)) ** 0.5

    model = lgb.LGBMClassifier(**params)
    x_core = features.feature_matrix(core, feature_set)
    y_core = core[features.TARGET]

    if holdout is not None and holdout[features.TARGET].nunique() > 1:
        model.fit(
            x_core,
            y_core,
            eval_set=[(features.feature_matrix(holdout, feature_set), holdout[features.TARGET])],
            eval_metric="auc",
            callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(0)],
        )
        if (model.best_iteration_ or 0) < 20:
            # Stopping this early means the metric was noise, not convergence.
            # Refit on everything with a fixed, modest budget instead.
            logger.debug("early stopping fired at %s; refitting fixed", model.best_iteration_)
            fixed = {**params, "n_estimators": 300}
            model = lgb.LGBMClassifier(**fixed)
            model.fit(features.feature_matrix(train, feature_set), train[features.TARGET])
    else:
        model.fit(x_core, y_core)
    return model


def predict(model: lgb.LGBMClassifier, frame: pd.DataFrame, feature_set: str) -> np.ndarray:
    return model.predict_proba(features.feature_matrix(frame, feature_set))[:, 1]


def rolling_origin_cv(
    panel: pd.DataFrame,
    feature_set: str,
    val_years: tuple[int, ...] = CV_VAL_YEARS,
) -> pd.DataFrame:
    """Walk-forward validation: train on everything strictly before each val year."""
    rows = []
    for year in val_years:
        train = panel[panel["panel_year"] < year]
        valid = panel[panel["panel_year"] == year]
        if train.empty or valid.empty:
            continue
        model = fit_lgbm(train, feature_set)
        scored = valid.copy()
        scored["score"] = predict(model, valid, feature_set)

        from ml.evaluate import scorecard  # local import avoids a cycle at module load

        card = scorecard(scored)
        card["val_year"] = year
        card["feature_set"] = feature_set
        rows.append(card)
        logger.info(
            "cv %s %s: capture@5%%=%.1f%% pr_auc=%.3f",
            feature_set,
            year,
            100 * card["capture@5%"],
            card["pr_auc"],
        )
    return pd.DataFrame(rows)


def fit_final(
    panel: pd.DataFrame, feature_set: str, train_through: int = TRAIN_THROUGH
) -> tuple[lgb.LGBMClassifier, pd.DataFrame]:
    """Fit on everything through `train_through`; test years stay untouched."""
    train = panel[panel["panel_year"] <= train_through]
    model = fit_lgbm(train, feature_set)
    return model, panel[panel["panel_year"] > train_through]


def score_baselines(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, np.ndarray]:
    """All baselines, each fitted on train and applied to test."""
    return {name: fn(train, test) for name, fn in BASELINES.items()}
