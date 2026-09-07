"""Offline tests for the ECCC weather splice.

No single station covers 1997-present, so `fetch_weather` stitches three
together. These tests pin the stitching rules, which are the only real logic in
the module; the HTTP call itself is stubbed out.
"""

from __future__ import annotations

import pandas as pd
import pytest

from extract import weather
from extract.weather import STATIONS, Station, fetch_weather


def _frame(station: Station, dates: list[str], temps: list[float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp(d).date() for d in dates],
            "max_temp_c": temps,
            "min_temp_c": temps,
            "mean_temp_c": temps,
            "total_rain_mm": [0.0] * len(dates),
            "total_snow_cm": [0.0] * len(dates),
            "total_precip_mm": [0.0] * len(dates),
            "snow_on_grnd_cm": [0.0] * len(dates),
            "source_station_id": station.station_id,
            "source_station_name": station.name,
            "_rank": station.rank,
        }
    )


AIRPORT = next(s for s in STATIONS if s.name == "KITCHENER/WATERLOO")
LEGACY = next(s for s in STATIONS if s.name == "WATERLOO WELLINGTON A")
FALLBACK = next(s for s in STATIONS if s.name == "ROSEVILLE")


def test_station_coverage_windows_are_disjoint_at_the_airport():
    """The two airport records are one site renamed -- they must not overlap."""
    assert LEGACY.last_year < AIRPORT.first_year


def test_fallback_station_spans_the_airport_gap():
    """2004-2009 exists in neither airport record; ROSEVILLE must cover it."""
    for year in range(LEGACY.last_year + 1, AIRPORT.first_year):
        assert not LEGACY.covers(year) and not AIRPORT.covers(year)
        assert FALLBACK.covers(year), f"{year} uncovered"


def test_airport_wins_when_both_stations_report(monkeypatch):
    def fake(station, year, session=None, timeout=60):
        temps = [1.0] if station is AIRPORT else [99.0]
        return _frame(station, ["2015-01-01"], temps)

    monkeypatch.setattr(weather, "fetch_station_year", fake)
    out = fetch_weather(start_year=2015, end_year=2015, session=object())

    assert len(out) == 1
    assert out["source_station_name"].iloc[0] == "KITCHENER/WATERLOO"
    assert out["mean_temp_c"].iloc[0] == 1.0


def test_fallback_fills_days_the_airport_missed(monkeypatch):
    """A null reading at the priority station must fall through, not win."""

    def fake(station, year, session=None, timeout=60):
        if station is AIRPORT:
            return _frame(station, ["2015-01-01", "2015-01-02"], [1.0, None])
        return _frame(station, ["2015-01-01", "2015-01-02"], [99.0, 42.0])

    monkeypatch.setattr(weather, "fetch_station_year", fake)
    out = fetch_weather(start_year=2015, end_year=2015, session=object()).set_index("date")

    assert out.loc[pd.Timestamp("2015-01-01").date(), "source_station_name"] == "KITCHENER/WATERLOO"
    assert out.loc[pd.Timestamp("2015-01-02").date(), "source_station_name"] == "ROSEVILLE"
    assert out.loc[pd.Timestamp("2015-01-02").date(), "mean_temp_c"] == 42.0


def test_one_bad_station_year_does_not_kill_the_run(monkeypatch):
    def fake(station, year, session=None, timeout=60):
        if station is AIRPORT:
            raise RuntimeError("503 from ECCC")
        return _frame(station, ["2015-01-01"], [7.0])

    monkeypatch.setattr(weather, "fetch_station_year", fake)
    out = fetch_weather(start_year=2015, end_year=2015, session=object())

    assert len(out) == 1
    assert out["source_station_name"].iloc[0] == "ROSEVILLE"


def test_total_failure_raises(monkeypatch):
    def fake(station, year, session=None, timeout=60):
        raise RuntimeError("network down")

    monkeypatch.setattr(weather, "fetch_station_year", fake)
    with pytest.raises(RuntimeError, match="no station-years downloaded"):
        fetch_weather(start_year=2015, end_year=2015, session=object())


def test_output_has_one_row_per_date(monkeypatch):
    def fake(station, year, session=None, timeout=60):
        return _frame(station, ["2015-01-01", "2015-01-02"], [1.0, 2.0])

    monkeypatch.setattr(weather, "fetch_station_year", fake)
    out = fetch_weather(start_year=2015, end_year=2015, session=object())
    assert out["date"].is_unique
