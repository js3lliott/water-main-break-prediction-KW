"""Inspection list: the product. A length budget, and what it buys."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import data_access as da

st.title("What to inspect next")

pipes = da.pipes_with_scores()
vintage = da.data_vintage()
total_km = pipes["length_km"].sum()
total_expected = pipes["expected_breaks"].sum()

st.caption(
    f"Kitchener's distribution network is {total_km:,.0f} km across {len(pipes):,} segments. "
    "Set a budget in kilometres and this ranks the network against it for "
    f"{vintage['target_year']}."
)

budget_km = st.slider(
    "Inspection budget (km of pipe)",
    min_value=5.0,
    max_value=float(round(total_km * 0.25)),
    value=float(round(total_km * 0.05)),
    step=5.0,
    help="5% of the network is about 47 km.",
)

ranked = pipes.sort_values(["score_per_100km", "length_km"], ascending=[False, True]).copy()
ranked["cumulative_km"] = ranked["length_km"].cumsum()
ranked["cumulative_expected"] = ranked["expected_breaks"].cumsum()
selected = ranked[ranked["cumulative_km"] <= budget_km]

if selected.empty:
    st.warning("Budget is smaller than the first segment. Raise it a little.")
    st.stop()

caught = selected["expected_breaks"].sum()
share = caught / total_expected
lift = share / (budget_km / total_km)

cols = st.columns(4)
cols[0].metric("Budget", f"{budget_km:,.0f} km", f"{budget_km / total_km:.1%} of network")
cols[1].metric("Segments", f"{len(selected):,}")
cols[2].metric("Expected breaks caught", f"{caught:.0f}", f"{share:.0%} of the year's expected")
cols[3].metric("Lift over random", f"{lift:.1f}×")

st.info(
    f"**Inspecting the worst {budget_km:,.0f} km covers about {share:.0%} of the breaks "
    f"expected across the whole network in {vintage['target_year']}** — {lift:.1f} times what "
    "the same length chosen at random would find. Walk-forward tested over ten years; see "
    "**How it works** for what that number does and does not mean."
)

st.subheader("Risk cells in the budget")
st.caption(
    "The risk cell is the unit that carries information. Every segment in a cell shares one "
    "rate, so the order *within* a cell is arbitrary — reversing the tiebreak moves the "
    "capture rate by under a point. Treat this as a set of cells to work through, not a "
    "league table of individual pipes."
)
cells = da.cell_summary(selected)
st.dataframe(
    cells.rename(
        columns={
            "risk_cell": "Prior breaks | material | decade",
            "segments": "Segments",
            "km": "km",
            "rate_per_100km": "Breaks/100km/yr",
            "expected_breaks": "Expected breaks",
            "evidence_breaks": "Evidence: breaks",
            "evidence_km": "Evidence: km-years",
        }
    ),
    hide_index=True,
    use_container_width=True,
    column_config={
        "km": st.column_config.NumberColumn(format="%.1f"),
        "Breaks/100km/yr": st.column_config.NumberColumn(format="%.1f"),
        "Expected breaks": st.column_config.NumberColumn(format="%.2f"),
        "Evidence: km-years": st.column_config.NumberColumn(format="%.0f"),
    },
)

with st.expander(f"All {len(selected):,} segments in the budget"):
    show = selected[
        [
            "watmainid",
            "risk_cell",
            "score_per_100km",
            "length_m",
            "material",
            "install_year",
            "pressure_zone",
            "lifetime_break_count",
            "last_break_date",
            "cumulative_km",
        ]
    ].rename(
        columns={
            "watmainid": "Main ID",
            "risk_cell": "Risk cell",
            "score_per_100km": "Breaks/100km/yr",
            "length_m": "Length (m)",
            "material": "Material",
            "install_year": "Installed",
            "pressure_zone": "Zone",
            "lifetime_break_count": "Past breaks",
            "last_break_date": "Last break",
            "cumulative_km": "Running km",
        }
    )
    st.dataframe(show, hide_index=True, use_container_width=True, height=420)

st.download_button(
    "Download this list as CSV",
    data=selected.drop(columns=["geometry_wkt"], errors="ignore").to_csv(index=False),
    file_name=f"kw_inspection_list_{vintage['target_year']}_{budget_km:.0f}km.csv",
    mime="text/csv",
    type="primary",
)

st.divider()
st.subheader("What other budgets would buy")
rows = []
for pct in (0.01, 0.02, 0.05, 0.10, 0.20):
    cut = ranked[ranked["cumulative_km"] <= total_km * pct]
    got = cut["expected_breaks"].sum()
    rows.append(
        {
            "Budget": f"{pct:.0%}",
            "km": round(cut["length_km"].sum(), 1),
            "Segments": len(cut),
            "Expected breaks": round(got, 1),
            "Share of expected": f"{got / total_expected:.0%}",
            "Lift": f"{(got / total_expected) / pct:.1f}×",
        }
    )
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
