"""Daily climate extraction from Environment and Climate Change Canada.

Winter severity is the strongest external driver of water main breaks -- frozen
ground loads the pipe, and freeze-thaw cycling works joints loose -- so the
break panel needs a daily temperature series back to 1997.

No single station covers that period. The project plan originally named
WATERLOO WELLINGTON A (climate ID 6149387), but a look at the ECCC station
inventory shows that station stopped reporting daily observations in 2003:

    WATERLOO WELLINGTON A  (stn 4832)   daily 1970-2003
    KITCHENER/WATERLOO     (stn 48569)  daily 2010-2026   <- same airport site
    ROSEVILLE              (stn 4816)   daily 1972-2026   <- ~18 km south

The airport pair is one physical site renamed and re-indexed, but it leaves a
2004-2009 hole. ROSEVILLE runs continuously through that gap, so the series is
spliced: airport where available, ROSEVILLE elsewhere and for individual missing
days. Every row records which station supplied it, so the splice is visible in
the warehouse rather than hidden here.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pandas as pd
import requests

from extract.arcgis import build_session

logger = logging.getLogger(__name__)

BULK_URL = "https://climate.weather.gc.ca/climate_data/bulk_data_e.html"
STATION_INVENTORY_URL = (
    "https://collaboration.cmc.ec.gc.ca/cmc/climate/Get_More_Data_Plus_de_donnees/"
    "Station%20Inventory%20EN.csv"
)

# The panel starts in 1997 (only 10 break records predate it), so the weather
# series starts a year earlier to give winter-season features a full lead-in.
DEFAULT_START_YEAR = 1996


@dataclass(frozen=True)
class Station:
    """An ECCC station, in splice priority order (lower rank wins)."""

    station_id: int
    climate_id: str
    name: str
    first_year: int
    last_year: int
    rank: int

    def covers(self, year: int) -> bool:
        return self.first_year <= year <= self.last_year


# Priority order: the airport site first (it is the closest thing to a canonical
# KW record), ROSEVILLE as the continuous fallback.
STATIONS: tuple[Station, ...] = (
    Station(48569, "6144239", "KITCHENER/WATERLOO", 2010, 2026, rank=0),
    Station(4832, "6149387", "WATERLOO WELLINGTON A", 1970, 2003, rank=0),
    Station(4816, "6147188", "ROSEVILLE", 1972, 2026, rank=1),
)

# Source column substring -> our column name. Matched by substring because the
# ECCC headers carry a degree sign whose encoding is not worth depending on.
_COLUMN_MAP = {
    "Date/Time": "date",
    "Max Temp": "max_temp_c",
    "Min Temp": "min_temp_c",
    "Mean Temp": "mean_temp_c",
    "Total Rain": "total_rain_mm",
    "Total Snow": "total_snow_cm",
    "Total Precip": "total_precip_mm",
    "Snow on Grnd": "snow_on_grnd_cm",
}


def fetch_station_year(
    station: Station, year: int, session: requests.Session | None = None, timeout: int = 60
) -> pd.DataFrame:
    """One station-year of daily observations, normalised to our column names."""
    session = session or build_session()
    params = {
        "format": "csv",
        "stationID": station.station_id,
        "Year": year,
        "Month": 1,
        "Day": 1,
        "timeframe": 2,  # 2 = daily
        "submit": "Download Data",
    }
    response = session.get(BULK_URL, params=params, timeout=timeout)
    response.raise_for_status()
    raw = pd.read_csv(io.StringIO(response.text))

    resolved: dict[str, str] = {}
    for needle, target in _COLUMN_MAP.items():
        matches = [c for c in raw.columns if needle in c and "Flag" not in c]
        if matches:
            resolved[matches[0]] = target

    frame = raw[list(resolved)].rename(columns=resolved)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    for column in set(_COLUMN_MAP.values()) - {"date"}:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")

    frame["source_station_id"] = station.station_id
    frame["source_station_name"] = station.name
    frame["_rank"] = station.rank
    return frame.dropna(subset=["date"])


def fetch_weather(
    start_year: int = DEFAULT_START_YEAR,
    end_year: int | None = None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Spliced daily series for Kitchener-Waterloo, one row per date.

    A day is taken from the highest-priority station that actually reported a
    mean temperature that day; days no station covers are simply absent, and the
    caller can see the gap rather than being handed a silent interpolation.
    """
    session = session or build_session()
    end_year = end_year or pd.Timestamp.now().year
    years = range(start_year, end_year + 1)

    frames: list[pd.DataFrame] = []
    for station in STATIONS:
        for year in years:
            if not station.covers(year):
                continue
            try:
                frames.append(fetch_station_year(station, year, session=session))
            except Exception as exc:  # noqa: BLE001 - one bad year must not kill the run
                logger.warning("weather: %s %s failed: %s", station.name, year, exc)

    if not frames:
        raise RuntimeError("weather: no station-years downloaded")

    combined = pd.concat(frames, ignore_index=True)

    # Splice: keep the best-ranked station that actually has a reading.
    combined = combined[combined["mean_temp_c"].notna()]
    combined = combined.sort_values(["date", "_rank"]).drop_duplicates("date", keep="first")
    combined = combined.drop(columns="_rank").sort_values("date").reset_index(drop=True)

    expected_days = (pd.Timestamp(f"{end_year}-12-31") - pd.Timestamp(f"{start_year}-01-01")).days
    coverage = len(combined) / max(expected_days, 1)
    by_station = combined["source_station_name"].value_counts().to_dict()
    logger.info(
        "weather: %s days, %.1f%% coverage of %s-%s, by station: %s",
        f"{len(combined):,}",
        coverage * 100,
        start_year,
        end_year,
        by_station,
    )
    return combined


def fetch_station_inventory(session: requests.Session | None = None) -> pd.DataFrame:
    """The full ECCC station inventory.

    Not used by the pipeline. Kept because it is how the station splice above
    was derived, and re-running it is how anyone would check that the chosen
    stations are still the right ones.
    """
    session = session or build_session()
    response = session.get(STATION_INVENTORY_URL, timeout=120)
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.content.decode("utf-8-sig")), skiprows=3)
    frame.columns = [c.strip() for c in frame.columns]
    return frame
