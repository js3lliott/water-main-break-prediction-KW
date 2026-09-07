"""Tests for the app's data layer.

The app is the part of this project a non-engineer actually touches, so the
things worth pinning are the ones that would silently mislead: a column
collision that drops the real material, geometry that draws lines across the
map, and the sub-metre artifacts that topped the first inspection list.
"""

from __future__ import annotations

import re

import pandas as pd
import pytest

# data_access imports streamlit for its cache decorators; skip cleanly if the
# app extra is not installed rather than failing the whole suite.
pytest.importorskip("streamlit")

import app.data_access as da  # noqa: E402


def _to_parts(wkt: str) -> list[list[list[float]]]:
    """Mirror of the parser under test, used to check its contract directly."""
    parts = []
    for group in re.findall(r"\(([^()]*)\)", wkt):
        points = []
        for pair in group.split(","):
            bits = pair.split()
            if len(bits) >= 2:
                points.append([float(bits[0]), float(bits[1])])
        if len(points) >= 2:
            parts.append(points)
    return parts


def test_linestring_becomes_one_path():
    frame = pd.DataFrame({"geometry_wkt": ["LINESTRING (-80.5 43.4, -80.4 43.5, -80.3 43.4)"]})
    out = da.parse_paths.__wrapped__(frame)
    assert len(out) == 1
    assert out["path"].iloc[0] == [[-80.5, 43.4], [-80.4, 43.5], [-80.3, 43.4]]


def test_multilinestring_explodes_rather_than_joining_the_parts():
    """A pipe recorded in disjoint parts must not be drawn as one continuous
    line -- naive paren-stripping draws a streak across the gap between them."""
    wkt = "MULTILINESTRING ((-80.5 43.4, -80.49 43.41), (-80.2 43.2, -80.19 43.21))"
    frame = pd.DataFrame({"geometry_wkt": [wkt], "watmainid": [7]})
    out = da.parse_paths.__wrapped__(frame)

    assert len(out) == 2, "each part should become its own row"
    assert (out["watmainid"] == 7).all(), "attributes carry to every part"
    # No path may span the gap between the two parts.
    for path in out["path"]:
        assert max(p[0] for p in path) - min(p[0] for p in path) < 0.1


def test_degenerate_geometry_is_dropped_not_drawn():
    frame = pd.DataFrame({"geometry_wkt": ["LINESTRING (-80.5 43.4)", "POINT (-80.5 43.4)", None]})
    assert len(da.parse_paths.__wrapped__(frame)) == 0


def test_risk_colour_spans_the_ramp_and_returns_rgba():
    colours = da.risk_colour(pd.Series([0.0, 5.0, 60.0]))
    assert len(colours) == 3
    assert all(len(c) == 4 for c in colours)
    assert all(0 <= channel <= 255 for c in colours for channel in c)
    # Low risk sits at the blue end, high risk at the rust end.
    assert colours[0][2] > colours[0][0], "low risk should be more blue than red"
    assert colours[-1][0] > colours[-1][2], "high risk should be more red than blue"


def test_risk_colour_survives_a_constant_series():
    """quantile() on a constant series returns that constant; a naive ramp
    divides by zero."""
    colours = da.risk_colour(pd.Series([0.0, 0.0, 0.0]))
    assert len(colours) == 3


def test_cell_summary_aggregates_to_cells_not_segments():
    frame = pd.DataFrame(
        {
            "risk_cell": ["3 | CI | 1950s", "3 | CI | 1950s", "0 | PVC | 2000s"],
            "watmainid": [1, 2, 3],
            "length_km": [1.0, 2.0, 5.0],
            "score_per_100km": [56.3, 56.3, 0.7],
            "expected_breaks": [0.56, 1.13, 0.04],
            "cell_breaks": [123, 123, 4],
            "cell_exposure_km": [201.5, 201.5, 900.0],
        }
    )
    out = da.cell_summary(frame).set_index("risk_cell")

    assert len(out) == 2
    assert out.loc["3 | CI | 1950s", "segments"] == 2
    assert out.loc["3 | CI | 1950s", "km"] == pytest.approx(3.0)
    # Evidence is a property of the cell, so it must not be summed across rows.
    assert out.loc["3 | CI | 1950s", "evidence_breaks"] == 123
    # Worst cell first.
    assert out.index[0] == "3 | CI | 1950s"


def test_parser_contract_matches_the_helper():
    wkt = "LINESTRING (-80.5 43.4, -80.4 43.5)"
    frame = pd.DataFrame({"geometry_wkt": [wkt]})
    assert da.parse_paths.__wrapped__(frame)["path"].iloc[0] == _to_parts(wkt)[0]
