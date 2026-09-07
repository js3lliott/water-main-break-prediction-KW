"""Cached loaders for the app's parquet bundle.

The app reads generated parquet, never the warehouse. That keeps it deployable
to Streamlit Community Cloud from a clone, and it means a slow query cannot make
the UI feel broken.

Pages import this as `import data_access`, not `from app import data_access`.
Streamlit puts the entry script's own directory on sys.path, and Community Cloud
does not install the repo as a package -- so the plain import is the one that
works both locally and deployed.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

# Kitchener city hall, near enough for an opening view.
CENTRE_LAT, CENTRE_LON = 43.4516, -80.4925


@st.cache_data(show_spinner=False)
def load(name: str) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.parquet"
    if not path.exists():
        st.error(
            f"Missing `{path.name}`. Regenerate the bundle with `python -m app.export_app_data`."
        )
        st.stop()
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def pipes_with_scores() -> pd.DataFrame:
    """One row per pipe: inventory attributes joined to the latest risk score.

    Sub-metre GIS connector artifacts are dropped here rather than filtered in
    each page. They are not inspectable assets, and leaving them in put 80 cm
    stubs at the top of the first inspection list this project produced.
    """
    pipes = load("pipes")
    scores = load("scores")

    # The score table repeats the cell keys (material, install_decade) and
    # length_km. Dropping them here rather than letting pandas suffix them keeps
    # a single authority for pipe attributes -- dim_pipe -- and avoids the
    # material_x / material_y columns that broke the first render of this page.
    duplicated = [c for c in ("material", "install_decade", "length_km") if c in scores.columns]
    merged = pipes.merge(scores.drop(columns=duplicated), on="watmainid", how="inner")

    overlap = [c for c in merged.columns if c.endswith(("_x", "_y"))]
    if overlap:
        raise ValueError(f"unresolved column collision in the app bundle: {overlap}")

    return merged[~merged["is_negligible_length"].astype(bool)].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def parse_paths(frame: pd.DataFrame, wkt_column: str = "geometry_wkt") -> pd.DataFrame:
    """Turn LINESTRING / MULTILINESTRING WKT into pydeck PathLayer coordinates.

    A MULTILINESTRING is a pipe recorded in disjoint parts. Naively stripping the
    parentheses concatenates those parts into one path, which draws a straight
    line across the gap between them -- the inventory has three of these, and
    they render as long spurious streaks across the map.

    Each part therefore becomes its own row. Parsed with a regex rather than
    shapely so the deployed app carries no geometry dependency for what is
    ultimately a text format.
    """
    out = frame.copy()

    def to_parts(wkt: str | None) -> list[list[list[float]]]:
        if not isinstance(wkt, str) or "(" not in wkt:
            return []
        parts = []
        # Innermost parenthesised groups: one per line for MULTILINESTRING,
        # exactly one for LINESTRING.
        for group in re.findall(r"\(([^()]*)\)", wkt):
            points = []
            for pair in group.split(","):
                bits = pair.split()
                if len(bits) >= 2:
                    points.append([float(bits[0]), float(bits[1])])
            if len(points) >= 2:
                parts.append(points)
        return parts

    out["path"] = out[wkt_column].map(to_parts)
    out = out[out["path"].map(len) > 0]
    # One row per line part; a multi-part pipe keeps its attributes on each.
    return out.explode("path").reset_index(drop=True)


def risk_colour(rate: pd.Series) -> list[list[int]]:
    """Sequential blue-to-rust ramp keyed to the rate, on a sqrt scale.

    Sqrt rather than linear because the rate distribution is heavily
    right-skewed -- a linear ramp renders almost the whole network as the same
    pale colour and hides the gradient that matters.
    """
    top = max(float(rate.quantile(0.98)), 1e-9)
    t = np.sqrt(np.clip(rate.to_numpy(dtype=float) / top, 0, 1))
    # #2C7FB8 (calm blue) -> #AB4318 (corrosion rust)
    r = (44 + t * (171 - 44)).astype(int)
    g = (127 + t * (67 - 127)).astype(int)
    b = (184 + t * (24 - 184)).astype(int)
    alpha = (110 + t * 145).astype(int)
    return np.stack([r, g, b, alpha], axis=1).tolist()


def cell_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to risk cells.

    The cell is the unit that carries information. Within one, every segment
    shares a rate, so a per-segment rank is an artifact of the tiebreak -- an
    empirical check across eight years put the two opposite tiebreaks 0.9
    points apart on capture@5%, inside the noise.
    """
    return (
        frame.groupby("risk_cell", observed=True)
        .agg(
            segments=("watmainid", "size"),
            km=("length_km", "sum"),
            rate_per_100km=("score_per_100km", "first"),
            expected_breaks=("expected_breaks", "sum"),
            evidence_breaks=("cell_breaks", "first"),
            evidence_km=("cell_exposure_km", "first"),
        )
        .reset_index()
        .sort_values("rate_per_100km", ascending=False)
    )


def data_vintage() -> dict[str, str]:
    scores = load("scores")
    breaks = load("breaks")
    return {
        "target_year": str(int(scores["target_year"].iloc[0])),
        "scored_at": pd.Timestamp(scores["scored_at"].iloc[0]).strftime("%Y-%m-%d"),
        "method_version": str(scores["method_version"].iloc[0]),
        "latest_break": pd.Timestamp(breaks["incident_date"].max()).strftime("%Y-%m-%d"),
    }
