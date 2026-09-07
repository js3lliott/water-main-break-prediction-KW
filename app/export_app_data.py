"""Export the slice of the warehouse the app needs, as parquet.

    python -m app.export_app_data

The warehouse is ~74 MB and rebuildable from the live APIs, so it is not
committed. The app is deployed to Streamlit Community Cloud, which serves
whatever is in the repo -- so the app reads a small generated bundle instead:
about 4 MB, dominated by pipe centreline geometry.

The bundle is committed deliberately. It is build output, but committing it is
what lets the deployed app work from a clone with no warehouse and no API
access. The weekly refresh job regenerates it.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import duckdb

logger = logging.getLogger("app.export")

DEFAULT_WAREHOUSE = Path("data/warehouse.duckdb")
DEFAULT_OUTPUT_DIR = Path("app/data")

# Only the most recent scoring run: ml.score appends, so the table accumulates
# a row per pipe per run and the app must not show four vintages at once.
EXPORTS = {
    "pipes": """
        select
            watmainid, material, install_decade, install_year, diameter_mm,
            length_m, length_km, pressure_zone, ownership, criticality,
            lifetime_break_count, has_ever_broken, predecessor_break_count,
            replaced_after_break, is_negligible_length, last_break_date,
            geometry_wkt
        from main_marts.dim_pipe
    """,
    "scores": """
        select * from main_scores.fct_pipe_risk_score
        where scored_at = (select max(scored_at) from main_scores.fct_pipe_risk_score)
    """,
    "breaks": """
        select
            break_incident_id, watmainid, match_status, incident_date,
            incident_year, incident_month, incident_season, break_nature,
            break_apparent_cause, street, pipe_material, age_at_break_years,
            geometry_wkt
        from main_marts.fct_break_incident
    """,
    "network_health": "select * from main_marts.mart_network_health",
    "panel_summary": """
        select
            panel_year,
            count(*)                                        as pipe_years,
            sum(break_count)                                as breaks,
            round(sum(length_km))                           as exposure_km,
            any_value(freezing_degree_days)                 as freezing_degree_days,
            any_value(freeze_thaw_days)                     as freeze_thaw_days
        from main_marts.fct_pipe_year
        where is_complete_year
        group by 1
        order by 1
    """,
}


# A refresh may legitimately lose a few break records -- the city amends and
# withdraws incidents -- but not many. A larger drop means a bad extract, and
# overwriting a good bundle with it would silently degrade the deployed app.
MAX_ACCEPTABLE_SHRINKAGE = 0.05


def check_not_shrunk(output_dir: Path, new_breaks: int, new_pipes: int) -> None:
    """Refuse to replace an existing bundle with a materially smaller one.

    The extractor already fails on a short read against the server's own count.
    This is the second line: it catches the case where the server itself returns
    a truncated or reset layer, which no client-side count check can detect.
    """
    existing = output_dir / "breaks.parquet"
    if not existing.exists():
        return

    import pandas as pd

    old_breaks = len(pd.read_parquet(existing, columns=["break_incident_id"]))
    old_pipes = len(pd.read_parquet(output_dir / "pipes.parquet", columns=["watmainid"]))

    for label, old, new in (("breaks", old_breaks, new_breaks), ("pipes", old_pipes, new_pipes)):
        if old and new < old * (1 - MAX_ACCEPTABLE_SHRINKAGE):
            raise SystemExit(
                f"refusing to write the bundle: {label} fell from {old:,} to {new:,} "
                f"({100 * (old - new) / old:.1f}% drop, tolerance "
                f"{100 * MAX_ACCEPTABLE_SHRINKAGE:.0f}%). Check the extract before rerunning."
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the app data bundle.")
    parser.add_argument("--warehouse", type=Path, default=DEFAULT_WAREHOUSE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--allow-shrinkage",
        action="store_true",
        help="skip the guard against replacing the bundle with a much smaller one",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    if not args.warehouse.exists():
        logger.error("no warehouse at %s -- run `make build` first", args.warehouse)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not args.allow_shrinkage:
        with duckdb.connect(str(args.warehouse), read_only=True) as con:
            check_not_shrunk(
                args.output_dir,
                con.sql(f"select count(*) from ({EXPORTS['breaks']})").fetchone()[0],
                con.sql(f"select count(*) from ({EXPORTS['pipes']})").fetchone()[0],
            )

    total_mb = 0.0
    with duckdb.connect(str(args.warehouse), read_only=True) as con:
        for name, query in EXPORTS.items():
            path = args.output_dir / f"{name}.parquet"
            con.sql(query).write_parquet(str(path), compression="zstd")
            size_mb = path.stat().st_size / 1_048_576
            total_mb += size_mb
            rows = con.sql(f"select count(*) from ({query})").fetchone()[0]
            logger.info("%-16s %8s rows  %6.2f MB", name, f"{rows:,}", size_mb)

    logger.info("bundle total: %.2f MB in %s", total_mb, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
