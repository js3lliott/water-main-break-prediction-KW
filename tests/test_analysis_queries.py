"""Tests for the analysis queries.

These build a tiny synthetic warehouse rather than reading the real one, so the
rate arithmetic is checked against numbers worked out by hand and CI needs no
data. The point is not to re-test DuckDB -- it is to pin the two conventions
that are easy to break silently: rates are per 100 km per year, and sub-metre
segments are excluded from every one of them.
"""

from __future__ import annotations

import duckdb
import pytest

from analysis import queries


@pytest.fixture
def warehouse() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.sql("create schema main_marts; create schema main_staging;")

    # Two pipes of 1 km each over one complete year:
    #   CI  -> 2 breaks over 1 km  = 200 breaks per 100 km
    #   PVC -> 0 breaks over 1 km  =   0
    # Plus a 0.5 m connector artifact carrying a break, which must be excluded
    # or it alone would score 200,000 per 100 km.
    con.sql("""
        create table main_marts.fct_pipe_year as
        select * from (values
            (1, 2015, 2, true,  1.0, 60, 'CI',  '1955s', 0, false, true,  false),
            (2, 2015, 0, false, 1.0, 10, 'PVC', '2005s', 0, false, true,  false),
            (3, 2015, 1, true,  0.0005, 5, 'CI', '1955s', 0, false, true, true)
        ) as t(watmainid, panel_year, break_count, broke_in_year, length_km,
               age_years, material, install_decade, prior_break_count_capped,
               has_prior_break, is_complete_year, is_negligible_length)
    """)
    yield con
    con.close()


def test_rate_by_material_is_per_100km(warehouse):
    out = queries.rate_by_material(warehouse, start_year=2000, min_exposure_km=0).set_index(
        "material"
    )
    # 2 breaks / 1 km -> 200 per 100 km. The 0.5 m segment must not appear.
    assert out.loc["CI", "rate_per_100km"] == pytest.approx(200.0)
    assert out.loc["PVC", "rate_per_100km"] == pytest.approx(0.0)


def test_negligible_length_segments_are_excluded(warehouse):
    """A sub-metre segment with a break would otherwise dominate any group."""
    out = queries.rate_by_material(warehouse, start_year=2000, min_exposure_km=0)
    assert out["breaks"].sum() == 2, "the 0.5 m connector's break leaked into the rate"


def test_incomplete_years_are_excluded(warehouse):
    """An in-progress year has partially observed outcomes and drags rates down."""
    warehouse.sql("""
        insert into main_marts.fct_pipe_year values
            (4, 2026, 0, false, 5.0, 3, 'PVC', '2020s', 0, false, false, false)
    """)
    out = queries.rate_by_material(warehouse, start_year=2000, min_exposure_km=0).set_index(
        "material"
    )
    # PVC exposure stays at the single complete-year kilometre.
    assert out.loc["PVC", "km_years"] == pytest.approx(1.0)


def test_repeat_failure_filters_compose(warehouse):
    """material and decade filters must both apply, not just the last one."""
    warehouse.sql("""
        insert into main_marts.fct_pipe_year values
            (5, 2015, 9, true, 1.0, 60, 'DI', '1955s', 0, false, true, false)
    """)
    unfiltered = queries.repeat_failure(warehouse)
    filtered = queries.repeat_failure(warehouse, material="CI", decades=("1955s",))
    assert unfiltered["breaks"].sum() == 11
    assert filtered["breaks"].sum() == 2


def test_hazard_by_age_bands_by_decade(warehouse):
    out = queries.hazard_by_age(warehouse, min_exposure_km=0).set_index("age_band_start")
    # age 60 and age 10 fall in distinct decade bands.
    assert 60 in out.index
    assert out.loc[60, "breaks"] == 2
