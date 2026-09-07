"""How it works — the honest version, including what did not work."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import data_access as da

st.title("How it works")
vintage = da.data_vintage()

st.markdown(
    """
The ranking behind this app is a **lookup table**, not a machine-learning model.
That is a finding, not a shortcut.

Every pipe is placed in a cell defined by three things known before the year
starts — **how many times it has already broken**, **what it is made of**, and
**which decade it was laid** — and scored with the historical failure rate of
that cell, in breaks per 100 km per year.
"""
)

st.subheader("What the number means")
st.markdown(
    """
The metric is **capture@5%**: rank the whole network, walk down the list
accumulating kilometres, and read off the share of that year's breaks sitting in
the top 5% of network length.

Not accuracy — predicting "no break" every time is 99.5% accurate and useless.
Not ROC-AUC, which flatters everything at a 0.5% base rate. And measured in
kilometres rather than segment count, because a 300 m main and a 12 m stub are
not equal units of work.

Tested **walk-forward across ten years**: train on everything before a year,
score that year, repeat. Never a random split — a random split would let a
pipe's 2015 break train a model that predicts its 2014 one.
"""
)

st.subheader("The lookup table beat the model")
st.caption(
    "Mean capture@5% across ten walk-forward years. Higher is better; random is 0.05 "
    "by construction."
)
results = pd.DataFrame(
    [
        ["Lookup table (shipped)", 0.301, 0.266, 0.108],
        ["LightGBM, all features", 0.281, 0.206, 0.064],
        ["LightGBM, no break history", 0.302, 0.187, 0.084],
        ["Rank by prior breaks", 0.299, 0.176, 0.105],
        ["Rank by material × decade", 0.197, 0.277, 0.061],
        ["Rank by age", 0.106, 0.176, 0.045],
        ["Random", 0.052, 0.054, 0.059],
    ],
    columns=["Method", "All pipes", "Never broken (90%)", "Has broken before (6%)"],
)
st.dataframe(
    results,
    hide_index=True,
    use_container_width=True,
    column_config={
        c: st.column_config.NumberColumn(format="%.3f")
        for c in ("All pipes", "Never broken (90%)", "Has broken before (6%)")
    },
)

st.markdown(
    """
Read the two right-hand columns, not the left one. Pipes that have broken before
are 6% of the network but over half the breaks, so a method that merely re-finds
them looks strong overall while telling the city nothing its work-order system
does not already contain.

Split that way, the gradient-boosted model is the **worst** of the serious
options: on the 90% of the network with no break history it captures 0.206
against the lookup table's 0.277, beating it in one year out of ten. A single
headline number would have shipped it anyway.
"""
)

st.subheader("What we deliberately did not use")
st.markdown(
    """
**The inventory's own condition score.** It outranks everything here — 75% of
breaks in the top 5% of never-broken network length. That is not skill. It is a
near-deterministic function of break count:

| Lifetime breaks | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Mean condition score | 9.02 | 6.35 | 5.68 | 5.05 | 5.01 | 4.80 | 4.48 |

Among pipes that had **never broken as of 2022**, those that went on to break in
2022–25 already carry a mean score of 7.17 against 9.02 for those that did not.
The inventory snapshot is from September 2026 — the score was marked down in
response to breaks that had not yet happened at prediction time. Using it would
make this app look twice as good and be worthless in the field.

**Weather.** Winter severity predicts the annual total well, but next winter is
unknown when the list is drawn. It belongs to a scenario view, not to a
forward-looking ranking.
"""
)

st.subheader("What this cannot tell you")
st.markdown(
    """
- **Rank within a cell is meaningless.** Every segment in a cell shares one rate.
  Reversing the tiebreak moves capture@5% by under a point across eight years, so
  treat the list as a set of cells to work through — not as evidence that segment
  #204 is riskier than #205.
- **Replaced pipe disappears.** 311 breaks are dated *before* the install year of
  the pipe now holding that asset ID: a segment failed, was replaced, and the
  replacement inherited the ID. The failure-prone pipe has been progressively
  removed from the record, so risk for the oldest cohorts is understated.
- **Attributes are today's.** Historical years are scored with the inventory as it
  stands now. A snapshot has started accumulating point-in-time values, but it can
  only do so going forward.
- **Roughly 20–40 breaks a year** land in the stratum that matters. Any single
  year is noise; that is why everything here is ten-year walk-forward.
- **No soil, pressure-transient, traffic-loading or repair-cost data.** Those are
  the obvious next features, and their absence is the most likely reason a
  flexible model cannot beat a three-column lookup.
- **Kitchener only.** Waterloo is a separate municipality with its own data.
"""
)

st.subheader("Data vintage")
st.markdown(
    f"""
| | |
|---|---|
| Scored for | **{vintage["target_year"]}** |
| Scored on | {vintage["scored_at"]} |
| Ranker version | `{vintage["method_version"]}` |
| Break records to | {vintage["latest_break"]} |

Source: City of Kitchener Open Data — *Water Main Breaks* and *Water Mains*,
pulled from the live ArcGIS feature server. Weather from Environment and Climate
Change Canada, spliced across three stations because no single one covers the
period.
"""
)

st.caption(
    "This is a personal project. The conclusions are the author's and are not a "
    "recommendation to any person or organisation."
)
