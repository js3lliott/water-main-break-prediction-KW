"""The shipped ranker: a fitted lookup table.

Phase 4 evaluated a gradient-boosted classifier against a set of simple
baselines over ten walk-forward years. The classifier lost. On the 90% of the
network with no break history it captured 20.6% of next year's breaks in the
top 5% of length against a lookup table's 27.7%, beating it in one year out of
ten; on pipes with history it captured 6.4% against 10.5%. See
docs/model-card.md.

So this is what ships: the empirical breaks-per-km of each
`(prior_break_count, material, install_decade)` cell, fitted on complete
training years. It matches the best method in every stratum, it is a GROUP BY,
and the engineer who has to act on the list can check it by hand.

The class exists rather than a bare function for three reasons the production
path needs and an evaluation function does not: it can be fitted once and
applied to several frames, it reports the evidence behind every score, and it
carries a version derived from its own contents.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DEFAULT_KEYS = ("prior_break_count_capped", "material", "install_decade")

# Cells are shrunk toward the global rate in proportion to how little exposure
# they carry. 20 km is roughly 2% of the network -- enough that a cell needs
# real evidence before it can rank far from the average.
DEFAULT_SMOOTHING_KM = 20.0


@dataclass
class StratifiedRateRanker:
    """Breaks per km by (prior breaks, material, install decade)."""

    keys: tuple[str, ...] = DEFAULT_KEYS
    smoothing_km: float = DEFAULT_SMOOTHING_KM
    table_: pd.DataFrame = field(default=None, repr=False)
    global_rate_: float = field(default=np.nan)
    trained_years_: tuple[int, ...] = field(default=())

    def fit(self, train: pd.DataFrame) -> StratifiedRateRanker:
        """Fit on complete panel years only.

        Fitting on anything else would put the outcome of the year being
        scored into the score -- the same mistake as the leaky condition_score,
        just self-inflicted.
        """
        if "is_complete_year" in train.columns and not train["is_complete_year"].all():
            raise ValueError(
                "StratifiedRateRanker must be fitted on complete years only; "
                "incomplete years have partially observed outcomes."
            )

        self.global_rate_ = float(train["break_count"].sum() / max(train["length_km"].sum(), 1e-9))
        grouped = train.groupby(list(self.keys), observed=True).agg(
            cell_breaks=("break_count", "sum"),
            cell_exposure_km=("length_km", "sum"),
            cell_pipe_years=("break_count", "size"),
        )
        grouped["cell_rate"] = (grouped["cell_breaks"] + self.smoothing_km * self.global_rate_) / (
            grouped["cell_exposure_km"] + self.smoothing_km
        )

        self.table_ = grouped
        self.trained_years_ = tuple(sorted(train["panel_year"].unique().tolist()))
        return self

    def _lookup(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.table_ is None:
            raise RuntimeError("ranker is not fitted")
        keyed = pd.MultiIndex.from_frame(frame[list(self.keys)])
        return self.table_.reindex(keyed).reset_index(drop=True)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        """Expected breaks per km.

        Per km, not per segment: the inspection budget is measured in
        kilometres, so ranking by total expected breaks would push long pipes up
        the list purely for being long.
        """
        return self._lookup(frame)["cell_rate"].fillna(self.global_rate_).to_numpy(dtype=float)

    def explain(self, frame: pd.DataFrame) -> pd.DataFrame:
        """The evidence behind each score.

        A lookup table needs no SHAP: the explanation is the computation. Each
        row gets its cell, that cell's historical rate, and how much pipe and
        how many breaks that rate rests on -- which also exposes the cells whose
        score is mostly the smoothing prior.
        """
        found = self._lookup(frame)
        out = pd.DataFrame(index=frame.index)
        for key in self.keys:
            out[key] = frame[key].to_numpy()
        out["risk_cell"] = [
            " | ".join(str(v) for v in row) for row in frame[list(self.keys)].to_numpy()
        ]
        out["cell_rate_per_100km"] = 100.0 * found["cell_rate"].fillna(self.global_rate_).to_numpy()
        out["cell_breaks"] = found["cell_breaks"].fillna(0).to_numpy()
        out["cell_exposure_km"] = found["cell_exposure_km"].fillna(0).to_numpy()
        out["cell_pipe_years"] = found["cell_pipe_years"].fillna(0).to_numpy()
        out["cell_is_unseen"] = found["cell_rate"].isna().to_numpy()
        return out

    @property
    def version(self) -> str:
        """Content hash of the fitted table.

        Two runs over identical data produce the same version; a changed cell,
        a changed key set or another training year produces a different one. It
        is what a stored score is stamped with, so a row can always be traced to
        the table that produced it.
        """
        if self.table_ is None:
            raise RuntimeError("ranker is not fitted")
        payload = (
            f"{self.keys}|{self.smoothing_km}|{self.trained_years_}|"
            + self.table_.round(8).to_csv()
        )
        return "rate-" + hashlib.sha256(payload.encode()).hexdigest()[:12]
