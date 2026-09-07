"""CLI entry point for the extract layer.

Writes date-partitioned parquet under data/raw/, one directory per dataset:

    data/raw/water_mains/extracted_at=2026-09-06/part-0.parquet
    data/raw/water_main_breaks/extracted_at=2026-09-06/part-0.parquet
    data/raw/weather_daily/extracted_at=2026-09-06/part-0.parquet

Partitioning by extract date means DuckDB can read the whole history with a
glob, and re-running on the same day overwrites that day's partition rather
than accumulating duplicates.

    python -m extract.run --dataset all
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from extract.arcgis import LAYERS, build_session, fetch_layer
from extract.weather import DEFAULT_START_YEAR, fetch_weather

logger = logging.getLogger("extract")

DEFAULT_OUTPUT_DIR = Path("data/raw")
DATASETS = ("water_mains", "water_main_breaks", "weather_daily")


def write_partition(frame: pd.DataFrame, dataset: str, output_dir: Path, run_date: str) -> Path:
    """Write one dataset to its extract-date partition, stamped with provenance."""
    stamped = frame.copy()
    stamped["_extracted_at"] = pd.Timestamp.now(tz="UTC")

    partition = output_dir / dataset / f"extracted_at={run_date}"
    partition.mkdir(parents=True, exist_ok=True)
    path = partition / "part-0.parquet"
    stamped.to_parquet(path, index=False, engine="pyarrow", compression="snappy")

    size_mb = path.stat().st_size / 1_048_576
    logger.info("%s: wrote %s rows -> %s (%.1f MB)", dataset, f"{len(stamped):,}", path, size_mb)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract raw KW water data to parquet.")
    parser.add_argument(
        "--dataset", choices=(*DATASETS, "all"), default="all", help="which dataset to extract"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    wanted = DATASETS if args.dataset == "all" else (args.dataset,)
    run_date = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    session = build_session()
    failures: list[str] = []

    for dataset in wanted:
        try:
            if dataset == "weather_daily":
                frame = fetch_weather(start_year=args.start_year, session=session)
            else:
                frame = fetch_layer(LAYERS[dataset], session=session)
            write_partition(frame, dataset, args.output_dir, run_date)
        except Exception as exc:  # noqa: BLE001 - report all failures, not just the first
            logger.error("%s: FAILED: %s", dataset, exc)
            failures.append(dataset)

    if failures:
        logger.error("extract finished with failures: %s", ", ".join(failures))
        return 1
    logger.info("extract complete: %s", ", ".join(wanted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
