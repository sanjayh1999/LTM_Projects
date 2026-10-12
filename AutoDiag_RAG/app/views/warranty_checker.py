"""Warranty checker page: instant rules-based verdict, coverage matrix, and AI explanation."""
import pandas as pd
import streamlit as st
import api_client as api
import ui
import visuals

visuals.inject_css()

options = api.warranty_options()

ui.page_header("Deterministic coverage check", "Is this repair covered?",
               "Instant verdict from the manufacturer rules table — no LLM involved in the decision. "
               "Ask the assistant to explain it with citations from the warranty booklet.")
st.write("")

if not options:
    st.warning("Can't load warranty rules — make sure the API is running.")
    st.stop()

form, result = st.columns([1, 1.6], gap="large")

with form:
    with st.container(border=True):
        mfr = st.segmented_control("Manufacturer", list(options), default=st.session_state.get("vp_mfr") or list(options)[0],
                                   key="wc_mfr")
        mfr = mfr or list(options)[0]
        comps = list(options[mfr])
        comp = st.selectbox("Component", comps, format_func=ui.pretty, key=f"wc_comp_{mfr}",
                            index=comps.index("powertrain") if "powertrain" in comps else 0)
        age = st.slider("Vehicle age (years)", 0.0, 15.0, float(st.session_state.get("vp_age", 4.0)), 0.5, key="wc_age")
        miles = st.number_input("Odometer (miles)", 0, 400_000, int(st.session_state.get("vp_miles", 55_000)), 1_000,
                                key="wc_miles")
        explain = st.button("Explain with citations", type="primary", icon=":material/auto_awesome:",
                            use_container_width=True)

try:
    data = api.warranty_check(mfr, comp, age, miles)
except api.ApiError as e:
    st.error(str(e))
    st.stop()

with result:
    ui.verdict_block(data["verdict"], title=f"{mfr} · {ui.pretty(comp)}")
    visuals.warranty_gauges(data["verdict"], age, miles)

st.markdown(f"##### {mfr} coverage timeline")
st.caption("Each bar runs from purchase to the end of that coverage. The yellow line is your car today; "           "a component can still expire earlier on mileage.")
visuals.coverage_timeline(data["coverage_matrix"], age, miles)

if explain:
    question = f"Is the {ui.pretty(comp).lower()} on my {mfr} still covered under warranty?"
    details = {"manufacturer": mfr, "component": comp, "vehicle_age_years": age, "mileage": int(miles)}
    with st.spinner("Retrieving warranty clauses and drafting an explanation…"):
        try:
            res = api.ask(question, warranty_details=details, route_override="warranty")
        except api.ApiError as e:
            st.error(str(e))
            res = None
    if res:
        st.session_state.query_log.append({"route": res["route"], "total_ms": (res.get("timings") or {}).get("total_ms"),
                                           "verdict": (res.get("verdict") or {}).get("status")})
        st.markdown("#### Explanation")
        with st.container(key="answer-warranty"):
            st.markdown(res["answer"])
        with st.expander(f"Evidence — {len(res['sources'])} retrieved sources", icon=":material/library_books:"):
            for i, s in enumerate(res["sources"], 1):
                ui.source_card(i, s)

st.write("")
st.markdown("#### Compare manufacturers")
st.caption("Basic (bumper-to-bumper) and powertrain terms from the rules table built from each 2026 warranty booklet.")


def term(rule):
    if not rule:
        return "—"
    miles = f"{rule['miles']:,} mi" if rule.get("miles") else "unlimited"
    return f"{rule['years']:g} yrs / {miles}"


table = pd.DataFrame([
    {"Manufacturer": m, "Basic": term(r.get("basic")), "Powertrain": term(r.get("powertrain")),
     "Other rule-backed items": ", ".join(ui.pretty(c) for c in r if c not in ("basic", "powertrain")) or "—"}
    for m, r in options.items()
])
st.dataframe(table, hide_index=True, use_container_width=True)