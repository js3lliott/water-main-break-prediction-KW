"""Risk map: the network drawn as pipe centrelines, coloured by risk."""

from __future__ import annotations

import pydeck as pdk
import streamlit as st

import data_access as da

st.title("Where the risk is")
st.caption(
    "Every water main in Kitchener, drawn as it runs in the ground and coloured by "
    "its expected break rate. The previous version of this app plotted past break "
    "locations as a heat map, which answers where the city has already dug rather "
    "than where it should dig next."
)

pipes = da.pipes_with_scores()
vintage = da.data_vintage()

with st.sidebar:
    st.subheader("Filter the network")
    zones = sorted(pipes["pressure_zone"].dropna().unique())
    materials = sorted(pipes["material"].dropna().unique())
    decades = sorted(pipes["install_decade"].dropna().unique())

    chosen_zones = st.multiselect("Pressure zone", zones, default=[])
    chosen_materials = st.multiselect("Material", materials, default=[])
    chosen_decades = st.multiselect("Install decade", decades, default=[])
    min_rate = st.slider(
        "Minimum rate (breaks per 100 km per year)",
        0.0,
        float(pipes["score_per_100km"].max()),
        0.0,
        step=1.0,
    )
    show_breaks = st.checkbox("Show recorded breaks since 2000", value=False)

view = pipes
if chosen_zones:
    view = view[view["pressure_zone"].isin(chosen_zones)]
if chosen_materials:
    view = view[view["material"].isin(chosen_materials)]
if chosen_decades:
    view = view[view["install_decade"].isin(chosen_decades)]
view = view[view["score_per_100km"] >= min_rate]

if view.empty:
    st.warning("No pipe matches those filters.")
    st.stop()

cols = st.columns(4)
cols[0].metric("Segments shown", f"{len(view):,}")
cols[1].metric("Length", f"{view['length_km'].sum():,.0f} km")
cols[2].metric(
    "Expected breaks",
    f"{view['expected_breaks'].sum():.0f}",
    help=f"During {vintage['target_year']}",
)
cols[3].metric(
    "Mean rate",
    f"{100 * view['expected_breaks'].sum() / max(view['length_km'].sum(), 1e-9):.1f}",
    help="Breaks per 100 km per year, length-weighted",
)

paths = da.parse_paths(view)
paths["colour"] = da.risk_colour(paths["score_per_100km"])
# Width in METRES, not pixels. pydeck 0.9 turns a string-valued layer prop into
# a data accessor -- `width_units="pixels"` is emitted as `widthUnits: "@@=pixels"`,
# deck.gl reads that as an undefined field per row, falls back to "common" units,
# and every pipe renders several times the width of the world. The pixel clamps
# below keep the lines legible at any zoom without needing the prop at all.
paths["width"] = (4 + 22 * (paths["score_per_100km"] / paths["score_per_100km"].max())).clip(4, 26)

layers = [
    pdk.Layer(
        "PathLayer",
        data=paths[
            [
                "path",
                "colour",
                "width",
                "watmainid",
                "risk_cell",
                "score_per_100km",
                "material",
                "install_year",
                "length_m",
                "pressure_zone",
                "lifetime_break_count",
                "cell_breaks",
                "cell_exposure_km",
            ]
        ],
        get_path="path",
        get_color="colour",
        get_width="width",
        width_min_pixels=1.5,
        width_max_pixels=7,
        pickable=True,
        auto_highlight=True,
    )
]

if show_breaks:
    breaks = da.load("breaks")
    breaks = breaks[breaks["incident_year"] >= 2000].copy()
    breaks["lon"] = breaks["geometry_wkt"].str.extract(r"POINT \(([-0-9.]+)").astype(float)
    breaks["lat"] = breaks["geometry_wkt"].str.extract(r" ([-0-9.]+)\)").astype(float)
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=breaks[["lon", "lat", "incident_year", "street"]].dropna(),
            get_position="[lon, lat]",
            get_fill_color=[20, 32, 41, 150],
            get_radius=14,
            radius_min_pixels=2,
            pickable=False,
        )
    )

st.pydeck_chart(
    pdk.Deck(
        map_style="light",
        initial_view_state=pdk.ViewState(
            latitude=da.CENTRE_LAT, longitude=da.CENTRE_LON, zoom=11.4, pitch=0
        ),
        layers=layers,
        tooltip={
            "html": (
                "<b>Main {watmainid}</b><br/>"
                "{material}, laid {install_year} — {length_m} m, zone {pressure_zone}<br/>"
                "<b>{score_per_100km}</b> breaks per 100 km/yr<br/>"
                "Risk cell: {risk_cell}<br/>"
                "Based on {cell_breaks} breaks over {cell_exposure_km} km-years<br/>"
                "This segment: {lifetime_break_count} recorded breaks"
            ),
            "style": {"backgroundColor": "#132029", "color": "white", "fontSize": "12px"},
        },
    ),
    height=620,
)

st.caption(
    f"Scored {vintage['scored_at']} for calendar {vintage['target_year']} · "
    f"ranker `{vintage['method_version']}` · break records to {vintage['latest_break']}. "
    "Colour is a square-root ramp — the rate distribution is skewed enough that a "
    "linear scale renders almost the whole network the same shade."
)
