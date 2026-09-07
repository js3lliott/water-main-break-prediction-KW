"""Regenerate every analysis figure.

python -m analysis.run              # all figures to figures/analysis/
python -m analysis.run --only 02    # just the ones whose name contains '02'
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from analysis import queries
from analysis.figures import FIGURES

logger = logging.getLogger("analysis")

DEFAULT_OUTPUT_DIR = Path("figures/analysis")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate analysis figures from the marts.")
    parser.add_argument("--warehouse", type=Path, default=queries.DEFAULT_WAREHOUSE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--only", type=str, default=None, help="substring filter on figure name")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    if not args.warehouse.exists():
        logger.error("no warehouse at %s -- run `make transform` first", args.warehouse)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    con = queries.connect(args.warehouse)
    failures = []

    for name, builder in FIGURES.items():
        if args.only and args.only not in name:
            continue
        try:
            figure = builder(con)
            path = args.output_dir / f"{name}.png"
            figure.savefig(path)
            plt.close(figure)
            logger.info("%-20s -> %s (%.0f KB)", name, path, path.stat().st_size / 1024)
        except Exception as exc:  # noqa: BLE001 - report every figure, not just the first
            logger.error("%-20s FAILED: %s", name, exc)
            failures.append(name)

    if failures:
        logger.error("figures failed: %s", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
