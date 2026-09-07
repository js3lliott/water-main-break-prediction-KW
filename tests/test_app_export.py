"""Tests for the app bundle export guard.

The weekly refresh regenerates this bundle unattended and commits it to main,
so the guard against overwriting a good bundle with a bad one is the piece that
most needs a test: nobody is watching when it runs.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.export_app_data import MAX_ACCEPTABLE_SHRINKAGE, check_not_shrunk


def _seed(tmp_path, breaks: int, pipes: int) -> None:
    pd.DataFrame({"break_incident_id": range(breaks)}).to_parquet(tmp_path / "breaks.parquet")
    pd.DataFrame({"watmainid": range(pipes)}).to_parquet(tmp_path / "pipes.parquet")


def test_no_existing_bundle_is_allowed(tmp_path):
    """A first run has nothing to compare against and must not be blocked."""
    check_not_shrunk(tmp_path, new_breaks=100, new_pipes=100)


def test_growth_is_allowed(tmp_path):
    _seed(tmp_path, breaks=2925, pipes=16208)
    check_not_shrunk(tmp_path, new_breaks=2960, new_pipes=16209)


def test_small_shrinkage_is_tolerated(tmp_path):
    """The city amends and withdraws incidents, so a few records can vanish."""
    _seed(tmp_path, breaks=2925, pipes=16208)
    check_not_shrunk(tmp_path, new_breaks=2900, new_pipes=16200)


def test_large_break_drop_is_refused(tmp_path):
    _seed(tmp_path, breaks=2925, pipes=16208)
    with pytest.raises(SystemExit, match="breaks fell from"):
        check_not_shrunk(tmp_path, new_breaks=1000, new_pipes=16208)


def test_large_pipe_drop_is_refused(tmp_path):
    """A truncated inventory layer is the failure the extractor cannot see:
    its own row count would still match the server's."""
    _seed(tmp_path, breaks=2925, pipes=16208)
    with pytest.raises(SystemExit, match="pipes fell from"):
        check_not_shrunk(tmp_path, new_breaks=2925, new_pipes=9000)


def test_boundary_just_inside_tolerance_passes(tmp_path):
    _seed(tmp_path, breaks=1000, pipes=1000)
    just_inside = int(1000 * (1 - MAX_ACCEPTABLE_SHRINKAGE)) + 1
    check_not_shrunk(tmp_path, new_breaks=just_inside, new_pipes=just_inside)


def test_boundary_just_outside_tolerance_fails(tmp_path):
    _seed(tmp_path, breaks=1000, pipes=1000)
    just_outside = int(1000 * (1 - MAX_ACCEPTABLE_SHRINKAGE)) - 1
    with pytest.raises(SystemExit):
        check_not_shrunk(tmp_path, new_breaks=just_outside, new_pipes=1000)
