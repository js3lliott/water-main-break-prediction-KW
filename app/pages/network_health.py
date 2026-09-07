"""Network health: what the historical record says."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_access as da

BLUE, RUST, MUTED = "#0B5FBF", "#AB4318", "#657785"

st.title("How the network has behaved")

health = da.load("network_health")
panel = da.load("panel_summary")
breaks = da.load("breaks")

recent = health[health["panel_year"] >= 2010]

st.subheader("Failure rate by material")
st.caption(
    "Normalised by length, which is the only way to compare. Cast iron dominates the raw "
    "break count, but it is also a minority of the network — the rate is what settles it."
)
by_material = (
    recent[recent["has_reportable_exposure"]]
    .groupby("material", as_index=False)
    .agg(breaks=("breaks", "sum"), exposure_km=("exposure_km", "sum"))
)
by_material = by_material[by_material["exposure_km"] >= 50]
by_material["rate"] = 100 * by_material["breaks"] / by_material["exposure_km"]
by_material = by_material.sort_values("rate")

fig = px.bar(
    by_material,
    x="rate",
    y="material",
    orientation="h",
    labels={"rate": "Breaks per 100 km per year", "material": ""},
    color=by_material["material"].eq("CI").map({True: RUST, False: BLUE}),
    color_discrete_map="identity",
    text=by_material["rate"].round(1),
)
fig.update_layout(showlegend=False, height=320, margin={"l": 0, "r": 0, "t": 10, "b": 0})
st.plotly_chart(fig, use_container_width=True)

st.subheader("Failure rate by installation decade")
st.caption(
    "Cast iron only. Hazard peaks at the 1950s–60s cohort and falls away on both sides — "
    "pre-war pipe is thick-walled pit cast iron, the mid-century material is thin-wall spun "
    "cast. It is why ranking by age alone is wrong at the top of the list: 1920s pipe outranks "
    "1950s pipe on age, and is roughly half as likely to fail."
)
by_decade = (
    recent[(recent["material"] == "CI") & recent["has_reportable_exposure"]]
    .groupby("install_decade", as_index=False)
    .agg(breaks=("breaks", "sum"), exposure_km=("exposure_km", "sum"))
)
by_decade = by_decade[by_decade["exposure_km"] >= 50].sort_values("install_decade")
by_decade["rate"] = 100 * by_decade["breaks"] / by_decade["exposure_km"]

fig = px.bar(
    by_decade,
    x="install_decade",
    y="rate",
    labels={"rate": "Breaks per 100 km per year", "install_decade": ""},
    color=by_decade["install_decade"].isin(["1950s", "1960s"]).map({True: RUST, False: BLUE}),
    color_discrete_map="identity",
    text=by_decade["rate"].round(0),
)
fig.update_layout(showlegend=False, height=320, margin={"l": 0, "r": 0, "t": 10, "b": 0})
st.plotly_chart(fig, use_container_width=True)

st.subheader("Breaks and winter severity, year by year")
st.caption(
    "Freezing degree-days accumulate frost depth. Across 26 years they correlate 0.73 with the "
    "annual break count — 2014 and 2015, the two hardest winters on record here, are the two "
    "worst break years."
)
fig = go.Figure()
fig.add_bar(x=panel["panel_year"], y=panel["breaks"], name="Breaks", marker_color=BLUE)
fig.add_scatter(
    x=panel["panel_year"],
    y=panel["freezing_degree_days"],
    name="Freezing degree-days",
    yaxis="y2",
    mode="lines+markers",
    line={"color": RUST, "width": 2},
)
fig.update_layout(
    height=380,
    margin={"l": 0, "r": 0, "t": 10, "b": 0},
    yaxis={"title": "Breaks"},
    yaxis2={"title": "Freezing degree-days", "overlaying": "y", "side": "right"},
    legend={"orientation": "h", "y": 1.12},
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("When breaks happen")
season = (
    breaks[breaks["incident_year"] >= 2000]
    .groupby("incident_month", as_index=False)
    .size()
    .rename(columns={"size": "breaks"})
)
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
season["month"] = season["incident_month"].map(lambda m: months[int(m) - 1])
fig = px.bar(
    season,
    x="month",
    y="breaks",
    labels={"breaks": "Breaks since 2000", "month": ""},
    color=season["incident_month"].isin([12, 1, 2]).map({True: RUST, False: BLUE}),
    color_discrete_map="identity",
)
fig.update_layout(showlegend=False, height=300, margin={"l": 0, "r": 0, "t": 10, "b": 0})
st.plotly_chart(fig, use_container_width=True)
winter_share = (
    season.loc[season["incident_month"].isin([12, 1, 2]), "breaks"].sum() / season["breaks"].sum()
)
st.caption(
    f"{winter_share:.0%} of breaks fall in December-February, "
    "against 25% if they were spread evenly."
)
