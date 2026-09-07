"""Paginated extraction from the City of Kitchener ArcGIS feature server.

The published CSV exports drop geometry -- the mains export carries only
`Shape__Length`, with no coordinates -- so this module goes to the REST API and
requests GeoJSON instead. Without line geometry there is no risk map and no
spatial features, which makes this the load-bearing part of the extract layer.

Two differences from the original `src/data/fetch_data.py`:

* It pages with `resultOffset`, not by bisecting OBJECTID ranges. Both layers
  report `supportsPagination: true`, so the range-splitting workaround (and its
  adaptive block-shrinking retry loop) is unnecessary.
* It parses GeoJSON with the stdlib and shapely rather than reading it through
  geopandas, which removes the fiona/GDAL dependency chain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from shapely.geometry import shape
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

ARCGIS_BASE = "https://services1.arcgis.com/qAo1OsXi67t7XgmS/arcgis/rest/services"

# GeoJSON mandates WGS84; ArcGIS honours `outSR` and both layers are stored in
# EPSG:26917 (UTM 17N), so this is an explicit reprojection, not a no-op.
OUT_SR = 4326

# Hard ceiling so a server-side paging bug can't spin forever.
MAX_PAGES = 500


@dataclass(frozen=True)
class Layer:
    """A feature layer to extract."""

    name: str  # local table name, snake_case
    service: str  # ArcGIS service name

    @property
    def url(self) -> str:
        return f"{ARCGIS_BASE}/{self.service}/FeatureServer/0"


LAYERS: dict[str, Layer] = {
    "water_mains": Layer("water_mains", "Water_Mains"),
    "water_main_breaks": Layer("water_main_breaks", "Water_Main_Breaks"),
}


def build_session(total_retries: int = 5) -> requests.Session:
    """A session that retries on the transient 5xx /429 the service throws."""
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def layer_definition(layer: Layer, session: requests.Session, timeout: int = 60) -> dict[str, Any]:
    """Fetch the layer metadata: object id field, page size, field types."""
    response = session.get(f"{layer.url}/?f=pjson", timeout=timeout)
    response.raise_for_status()
    definition = response.json()
    if "error" in definition:
        raise RuntimeError(f"{layer.name}: layer definition error: {definition['error']}")
    return definition


def feature_count(layer: Layer, session: requests.Session, timeout: int = 60) -> int:
    """Server-side row count, used to verify the extract is complete."""
    response = session.get(
        f"{layer.url}/query",
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    return int(response.json()["count"])


def date_fields(definition: dict[str, Any]) -> list[str]:
    """Names of fields the service declares as dates.

    ArcGIS returns dates as epoch milliseconds. Reading the field types off the
    layer definition converts exactly the right columns, rather than hardcoding
    the two the original script happened to know about.
    """
    return [
        field["name"]
        for field in definition.get("fields", [])
        if field.get("type") == "esriFieldTypeDate"
    ]


def _features_to_frame(features: list[dict[str, Any]]) -> pd.DataFrame:
    """Flatten GeoJSON features into a frame, geometry preserved as WKT."""
    rows = []
    for feature in features:
        row = dict(feature.get("properties") or {})
        geometry = feature.get("geometry")
        row["geometry_wkt"] = shape(geometry).wkt if geometry else None
        rows.append(row)
    return pd.DataFrame(rows)


def fetch_layer(
    layer: Layer,
    session: requests.Session | None = None,
    page_size: int | None = None,
    timeout: int = 120,
) -> pd.DataFrame:
    """Download every feature in a layer, with geometry, as a DataFrame.

    Raises if the row count doesn't match the server's own count -- a silent
    short read is the failure mode that would quietly poison every downstream
    model, so it fails loudly here instead.
    """
    session = session or build_session()
    definition = layer_definition(layer, session)
    oid_field = definition.get("objectIdField", "OBJECTID")
    max_records = int(definition.get("maxRecordCount", 1000))
    page_size = min(page_size or max_records, max_records)
    expected = feature_count(layer, session)

    logger.info(
        "%s: expecting %s features, paging %s at a time", layer.name, f"{expected:,}", page_size
    )

    frames: list[pd.DataFrame] = []
    offset = 0
    for page in range(MAX_PAGES):
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": OUT_SR,
            # A stable sort is required: without it, offset paging on some
            # services can skip or duplicate rows between pages.
            "orderByFields": oid_field,
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "geojson",
        }
        response = session.get(f"{layer.url}/query", params=params, timeout=timeout)
        response.raise_for_status()
        payload = json.loads(response.text)
        if "error" in payload:
            raise RuntimeError(f"{layer.name}: query error at offset {offset}: {payload['error']}")

        features = payload.get("features") or []
        if not features:
            break

        frames.append(_features_to_frame(features))
        offset += len(features)
        logger.debug("%s: page %s, %s rows, %s total", layer.name, page, len(features), offset)

        # Stop on a short page, or once the server's own count is satisfied --
        # the latter saves a round trip and stops a service that ignores
        # `resultOffset` from paging forever.
        if len(features) < page_size or offset >= expected:
            break
    else:
        raise RuntimeError(f"{layer.name}: exceeded {MAX_PAGES} pages; aborting")

    if not frames:
        raise RuntimeError(f"{layer.name}: no features returned")

    frame = pd.concat(frames, ignore_index=True)

    if len(frame) != expected:
        raise RuntimeError(
            f"{layer.name}: extracted {len(frame):,} rows but server reports "
            f"{expected:,}. Refusing to write a partial extract."
        )
    if oid_field in frame.columns and frame[oid_field].duplicated().any():
        dupes = int(frame[oid_field].duplicated().sum())
        raise RuntimeError(f"{layer.name}: {dupes} duplicate {oid_field} values in extract")

    for column in date_fields(definition):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], unit="ms", errors="coerce", utc=True)

    logger.info("%s: extracted %s rows, %s columns", layer.name, f"{len(frame):,}", frame.shape[1])
    return frame
