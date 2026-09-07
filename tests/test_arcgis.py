"""Offline tests for the ArcGIS extractor.

Fixtures were recorded from the live service (trimmed to a handful of fields)
so the shapes are real, but no test touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import responses

from extract.arcgis import Layer, date_fields, feature_count, fetch_layer, layer_definition

FIXTURES = Path(__file__).parent / "fixtures"
LAYER = Layer("water_mains", "Water_Mains")


@pytest.fixture
def layer_def() -> dict:
    return json.loads((FIXTURES / "mains_layer_def.json").read_text())


@pytest.fixture
def page() -> dict:
    return json.loads((FIXTURES / "mains_page.geojson").read_text())


def _register(layer_def: dict, pages: list[dict], count: int) -> None:
    responses.add(responses.GET, f"{LAYER.url}/", json=layer_def)
    responses.add(responses.GET, f"{LAYER.url}/query", json={"count": count})
    for payload in pages:
        responses.add(responses.GET, f"{LAYER.url}/query", json=payload)
    # A real service returns an empty feature list once the offset runs past the
    # end; without it, `responses` would replay the last page forever.
    responses.add(
        responses.GET, f"{LAYER.url}/query", json={"type": "FeatureCollection", "features": []}
    )


def test_date_fields_reads_types_from_definition(layer_def):
    assert date_fields(layer_def) == ["INSTALLATION_DATE"]


@responses.activate
def test_layer_definition_and_count(layer_def):
    responses.add(responses.GET, f"{LAYER.url}/", json=layer_def)
    responses.add(responses.GET, f"{LAYER.url}/query", json={"count": 3})
    assert layer_definition(LAYER, __import__("requests").Session())["objectIdField"] == "OBJECTID"
    assert feature_count(LAYER, __import__("requests").Session()) == 3


@responses.activate
def test_fetch_layer_parses_geometry_and_dates(layer_def, page):
    _register(layer_def, [page], count=3)
    frame = fetch_layer(LAYER, page_size=3)

    assert len(frame) == 3
    # Geometry survives the CSV export's blind spot.
    assert frame["geometry_wkt"].notna().all()
    assert frame["geometry_wkt"].iloc[0].startswith("LINESTRING")
    # Epoch-ms date fields are converted using the layer's declared types.
    assert pd.api.types.is_datetime64_any_dtype(frame["INSTALLATION_DATE"])
    assert frame["INSTALLATION_DATE"].iloc[0].year == 1979


def _page_with_oids(template: dict, oids: list[int]) -> dict:
    """Clone the recorded feature, restamping OBJECTID so pages stay distinct."""
    base = template["features"][0]
    features = []
    for oid in oids:
        feature = json.loads(json.dumps(base))
        feature["properties"]["OBJECTID"] = oid
        features.append(feature)
    return {"type": "FeatureCollection", "features": features}


@responses.activate
def test_fetch_layer_pages_until_short_page(layer_def, page):
    """Two full pages then a short one; offsets must accumulate across pages."""
    pages = [
        _page_with_oids(page, [1, 2, 3]),
        _page_with_oids(page, [4, 5, 6]),
        _page_with_oids(page, [7]),
    ]
    _register(layer_def, pages, count=7)
    frame = fetch_layer(LAYER, page_size=3)
    assert len(frame) == 7
    assert sorted(frame["OBJECTID"]) == [1, 2, 3, 4, 5, 6, 7]


@responses.activate
def test_short_read_raises_rather_than_writing_partial(layer_def, page):
    """A silent short read would poison every downstream model, so it must fail."""
    _register(layer_def, [page], count=999)
    with pytest.raises(RuntimeError, match="Refusing to write a partial extract"):
        fetch_layer(LAYER, page_size=3)


@responses.activate
def test_duplicate_object_ids_raise(layer_def, page):
    dupe = {"type": "FeatureCollection", "features": page["features"] + [page["features"][0]]}
    _register(layer_def, [dupe], count=4)
    with pytest.raises(RuntimeError, match="duplicate OBJECTID"):
        fetch_layer(LAYER, page_size=4)


@responses.activate
def test_server_error_payload_raises(layer_def):
    responses.add(responses.GET, f"{LAYER.url}/", json=layer_def)
    responses.add(responses.GET, f"{LAYER.url}/query", json={"count": 3})
    responses.add(responses.GET, f"{LAYER.url}/query", json={"error": {"code": 400}})
    with pytest.raises(RuntimeError, match="query error"):
        fetch_layer(LAYER, page_size=3)
