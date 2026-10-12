"""AutoDiag-RAG — run with:  streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import streamlit as st
import api_client as api
import ui

st.set_page_config(page_title="AutoDiag · Diagnosis & Warranty", page_icon="🚗", layout="wide")
ui.inject_css()

st.session_state.setdefault("messages", [])
st.session_state.setdefault("query_log", [])

online = api.is_online()
options = api.warranty_options()

with st.sidebar:
    ui.brand(online)
    if not online:
        st.caption("Start the backend first:  `uvicorn src.api.main:app --port 8000`")

    st.markdown("### Vehicle profile")
    manufacturers = list(options.keys()) or ["Honda", "Hyundai", "Toyota", "Ford", "Nissan", "Kia"]
    mfr = st.selectbox("Manufacturer", manufacturers, key="vp_mfr")
    components = list(options.get(mfr, {}).keys()) or ["basic", "powertrain"]
    st.selectbox("Component", components, key="vp_comp", format_func=ui.pretty)
    c1, c2 = st.columns(2)
    c1.number_input("Age (yrs)", min_value=0.0, max_value=30.0, step=0.5, value=4.0, key="vp_age")
    c2.number_input("Mileage", min_value=0, max_value=400_000, step=1_000, value=55_000, key="vp_miles")
    st.toggle("Use profile for warranty questions", value=True, key="vp_attach",
              help="When a question is routed to warranty, the rules check runs on this vehicle.")

pages = [
    st.Page("views/assistant.py", title="Assistant", icon=":material/forum:", default=True),
    st.Page("views/warranty_checker.py", title="Warranty checker", icon=":material/verified_user:"),
    st.Page("views/insights.py", title="System insights", icon=":material/insights:"),
]
st.navigation(pages, position="top").run()