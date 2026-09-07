"""KW water main break risk — entry point.

streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="KW Water Main Risk",
    page_icon="🚱",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES = [
    st.Page("pages/risk_map.py", title="Risk map", icon="🗺️", default=True),
    st.Page("pages/inspection_list.py", title="Inspection list", icon="📋"),
    st.Page("pages/network_health.py", title="Network health", icon="📈"),
    st.Page("pages/model_card.py", title="How it works", icon="📐"),
]

st.navigation(PAGES).run()
