"""Analytical queries against the marts.

Every function takes a DuckDB connection and returns a DataFrame. Kept as
importable functions rather than notebook cells so they can be tested, reused
by the Streamlit app, and diffed in review.

Two conventions apply throughout:

* Length-normalised rates exclude `is_negligible_length` segments. The
  inventory holds 655 sub-metre GIS connector artifacts; a 1 cm "segment" with
  one break scores 14,000 breaks per 100 km and swamps any group it lands in.
* Rates are reported per 100 km per year, which is how water utilities
  benchmark. Raw counts are kept alongside so the exposure is always visible.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DEFAULT_WAREHOUSE = Path("data/warehouse.duckdb")

# The panel runs from 1997, but the first few years are thin on breaks and the
# inventory's oldest records are least reliable. Analyses default to 2000+.
ANALYSIS_START_YEAR = 2000

# Groups thinner than this are dropped from rate tables. A rate computed over a
# few hundred metres of pipe is an artifact of its denominator, not a rate.
MIN_EXPOSURE_KM = 50.0


def connect(warehouse: Path | str = DEFAULT_WAREHOUSE) -> duckdb.DuckDBPyConnection:
    """Read-only connection to the warehouse."""
    return duckdb.connect(str(warehouse), read_only=True)


def _panel(start_year: int = ANALYSIS_START_YEAR) -> str:
    """The complete-year, real-length slice of the panel every rate uses."""
    return f"""
        select * from main_marts.fct_pipe_year
        where is_complete_year
          and panel_year >= {start_year}
          and not is_negligible_length
    """


def rate_by_material(
    con: duckdb.DuckDBPyConnection,
    start_year: int = 2010,
    min_exposure_km: float = MIN_EXPOSURE_KM,
) -> pd.DataFrame:
    """Failure rate by pipe material, normalised by exposure.

    Answers the question raw counts get wrong: cast iron dominates the break
    *count*, but it is a minority of the network by length. Only the
    length-normalised rate settles whether it is actually worse.
    """
    return con.sql(f"""
        with panel as ({_panel(start_year)})
        select
            material,
            sum(break_count)                                        as breaks,
            round(sum(length_km))                                   as km_years,
            round(100.0 * sum(break_count) / sum(length_km), 1)     as rate_per_100km,
            round(100.0 * sum(break_count) / sum(sum(break_count)) over (), 1) as pct_of_breaks,
            round(100.0 * sum(length_km) / sum(sum(length_km)) over (), 1)     as pct_of_network
        from panel
        where material is not null
        group by 1
        having sum(length_km) >= {min_exposure_km}
        order by rate_per_100km desc
    """).df()


def hazard_by_age(
    con: duckdb.DuckDBPyConnection, min_exposure_km: float = MIN_EXPOSURE_KM
) -> pd.DataFrame:
    """Failure rate by pipe age band -- the apparent hazard curve."""
    return con.sql(f"""
        with panel as ({_panel()})
        select
            cast(floor(age_years / 10) * 10 as integer)              as age_band_start,
            round(sum(length_km))                                   as km_years,
            sum(break_count)                                        as breaks,
            round(100.0 * sum(break_count) / sum(length_km), 1)     as rate_per_100km
        from panel
        where age_years < 110
        group by 1
        having sum(length_km) >= {min_exposure_km}
        order by 1
    """).df()


def hazard_by_cohort(
    con: duckdb.DuckDBPyConnection,
    material: str = "CI",
    min_exposure_km: float = MIN_EXPOSURE_KM,
) -> pd.DataFrame:
    """Failure rate by installation decade, for one material.

    The companion to `hazard_by_age`. Age and cohort are confounded -- a pipe's
    age in the panel is fixed by when it went in -- so the age curve alone
    cannot say whether old pipe fails because it is old or because of how it
    was made. Holding material constant and cutting by install decade separates
    them.
    """
    return con.sql(f"""
        with panel as ({_panel()})
        select
            install_decade,
            round(sum(length_km))                                   as km_years,
            sum(break_count)                                        as breaks,
            round(100.0 * sum(break_count) / sum(length_km), 1)     as rate_per_100km,
            round(avg(age_years))                                   as mean_age_years
        from panel
        where material = '{material}' and install_decade is not null
        group by 1
        having sum(length_km) >= {min_exposure_km}
        order by 1
    """).df()


def repeat_failure(
    con: duckdb.DuckDBPyConnection, material: str | None = None, decades: tuple[str, ...] = ()
) -> pd.DataFrame:
    """Failure rate by number of prior breaks on the same pipe.

    `prior_break_count` is as-of 1 January of the panel year, so this is a
    forecast-safe relationship, not a retrospective one. Passing `material` and
    `decades` holds the obvious confounders constant -- pipes that have broken
    before are disproportionately old cast iron, so the raw gradient overstates
    the independent contribution of break history.
    """
    filters = ""
    if material:
        filters += f" and material = '{material}'"
    if decades:
        quoted = ", ".join(f"'{d}'" for d in decades)
        filters += f" and install_decade in ({quoted})"

    return con.sql(f"""
        with panel as ({_panel(2005)})
        select
            prior_break_count_capped                                as prior_breaks,
            count(*)                                                as pipe_years,
            round(sum(length_km))                                   as km_years,
            sum(break_count)                                        as breaks,
            round(100.0 * sum(break_count) / sum(length_km), 1)     as rate_per_100km
        from panel
        where true {filters}
        group by 1
        order by 1
    """).df()


def seasonality(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Break counts by calendar month, against the monthly temperature normal."""
    return con.sql(f"""
        with breaks as (
            select incident_month as month, count(*) as breaks
            from main_marts.fct_break_incident
            where incident_year >= {ANALYSIS_START_YEAR}
            group by 1
        ),
        temps as (
            select weather_month as month, avg(mean_temp_c) as mean_temp_c
            from main_staging.stg_weather_daily
            where weather_year >= {ANALYSIS_START_YEAR}
            group by 1
        )
        select
            breaks.month,
            breaks.breaks,
            round(temps.mean_temp_c, 1)                             as mean_temp_c,
            round(100.0 * breaks.breaks / sum(breaks.breaks) over (), 1) as pct_of_breaks
        from breaks join temps using (month)
        order by breaks.month
    """).df()


def winter_severity_vs_breaks(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Annual break totals against that winter's severity.

    Freezing degree-days accumulate frost depth. Note that `freeze_thaw_days`
    is NOT a severity measure in this climate -- frequent zero crossings mean a
    mild winter -- so it correlates negatively with breaks.
    """
    return con.sql(f"""
        with panel as ({_panel()})
        select
            panel_year,
            any_value(freezing_degree_days)                         as freezing_degree_days,
            any_value(freeze_thaw_days)                             as freeze_thaw_days,
            any_value(coldest_7day_mean_c)                          as coldest_7day_mean_c,
            sum(break_count)                                        as breaks
        from panel
        group by 1
        order by 1
    """).df()


def survivorship_evidence(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Material mix of breaks by whether the pipe is still in the inventory.

    Pipes replaced after failing leave the inventory, taking their failure
    history with them. If the replaced population skews toward a material, the
    model systematically understates that material's risk.
    """
    return con.sql("""
        select
            match_status,
            coalesce(reported_material, 'UNKNOWN')                  as material,
            count(*)                                                as breaks,
            round(
                100.0 * count(*) / sum(count(*)) over (partition by match_status), 1
            )                                                   as pct_within_status
        from main_marts.fct_break_incident
        where match_status in ('matched', 'orphan_asset')
        group by 1, 2
        order by 1, breaks desc
    """).df()


def break_locations(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Break coordinates for the spatial view, parsed from point WKT."""
    return con.sql(f"""
        select
            break_incident_id,
            incident_year,
            match_status,
            cast(regexp_extract(geometry_wkt, 'POINT \\(([-0-9.]+) ', 1) as double) as longitude,
            cast(regexp_extract(geometry_wkt, ' ([-0-9.]+)\\)', 1) as double)       as latitude
        from main_marts.fct_break_incident
        where geometry_wkt like 'POINT%'
          and incident_year >= {ANALYSIS_START_YEAR}
    """).df()


def concentration_curve(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Cumulative share of breaks against cumulative share of network length,
    with pipes ranked by their observed lifetime break count.

    IMPORTANT: this is a hindsight bound, not a model result. It ranks pipes by
    failures already observed, so it answers "how concentrated is failure?" and
    NOT "how well can we predict it?". It is the ceiling any ranking could have
    hit knowing the answers in advance. Phase 4 measures the forecastable
    version -- ranking on features known before the year starts, scored on a
    held-out year.
    """
    return con.sql("""
        with pipes as (
            select watmainid, length_km, lifetime_break_count
            from main_marts.dim_pipe
            where not is_negligible_length
        ),
        ranked as (
            select
                length_km,
                lifetime_break_count,
                sum(length_km) over (
                    order by lifetime_break_count desc, length_km
                    rows unbounded preceding) as cum_km,
                sum(lifetime_break_count) over (
                    order by lifetime_break_count desc, length_km
                    rows unbounded preceding) as cum_breaks,
                sum(length_km) over ()           as total_km,
                sum(lifetime_break_count) over () as total_breaks
            from pipes
        )
        select
            round(100.0 * cum_km / total_km, 3)         as pct_network_km,
            round(100.0 * cum_breaks / total_breaks, 3) as pct_breaks_captured
        from ranked
        order by pct_network_km
    """).df()


def break_history_profile(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Pipe age and material mix by how many times a segment has failed."""
    return con.sql("""
        select
            case
                when lifetime_break_count = 0 then 'Never broken'
                when lifetime_break_count = 1 then '1 break'
                when lifetime_break_count <= 3 then '2-3 breaks'
                else '4+ breaks'
            end                                             as history,
            count(*)                                        as pipes,
            round(avg(install_year))                        as mean_install_year,
            round(100.0 * avg(case when material = 'CI' then 1.0 else 0 end)) as pct_cast_iron
        from main_marts.dim_pipe
        where not is_negligible_length
        group by 1
    """).df()


def scored_network(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Pipe centrelines with their latest risk score, for the network map.

    Reads the score table written by `ml.score` rather than a mart, so this is
    the one analysis query that depends on the modelling layer having run.
    """
    return con.sql("""
        with latest as (
            select * from main_scores.fct_pipe_risk_score
            where scored_at = (select max(scored_at) from main_scores.fct_pipe_risk_score)
        )
        select
            p.watmainid,
            p.material,
            p.length_km,
            p.geometry_wkt,
            latest.score_per_100km,
            latest.risk_cell
        from main_marts.dim_pipe p
        join latest on latest.watmainid = p.watmainid
        where p.geometry_wkt is not null
          and not p.is_negligible_length
    """).df()
