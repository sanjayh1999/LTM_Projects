"""Assistant page: chat over the hybrid-retrieval pipeline, with voice input."""
import hashlib
from datetime import datetime

import streamlit as st
import api_client as api
import ui
import visuals

visuals.inject_css()

EXAMPLES = [
    ("Symptom", "My car makes a rattling noise when accelerating"),
    ("Fault code", "What does code P0301 mean and what usually causes it?"),
    ("Warranty", "Is my powertrain still covered under warranty?"),
    ("Symptom", "Steering wheel feels stiff and hard to turn at highway speed"),
    ("Fault code", "Check engine light shows P0420 — is it serious?"),
    ("Warranty", "Would a transmission repair be covered at my mileage?"),
]
MODES = {"Auto-route": None, "Diagnosis": "diagnosis", "Warranty": "warranty"}

messages = st.session_state.messages


# ---------------------------------------------------------------- helpers
def vehicle_details():
    if not st.session_state.get("vp_attach"):
        return None
    return {
        "manufacturer": st.session_state.vp_mfr,
        "component": st.session_state.vp_comp,
        "vehicle_age_years": float(st.session_state.vp_age),
        "mileage": int(st.session_state.vp_miles),
    }


def report_markdown(question, res, details):
    lines = [f"# AutoDiag report", f"_Generated {datetime.now():%Y-%m-%d %H:%M}_", "",
             f"**Question:** {question}", f"**Route:** {res['route']}", ""]
    conf = res.get("confidence") or {}
    if conf:
        score = conf.get("top_score")
        lines += [f"**Evidence confidence:** {conf.get('level', 'unknown')}"
                  + (f" (top re-rank score {score:.2f})" if score is not None else "")
                  + (" — DEFERRED to human review" if conf.get("deferred") else ""), ""]
    if res.get("verdict"):
        v = res["verdict"]
        lines += [f"**Coverage verdict:** {v['status'].replace('_', ' ').upper()}", f"> {v['reason']}", ""]
        if details:
            lines += [f"Vehicle: {details['manufacturer']} · {details['component']} · "
                      f"{details['vehicle_age_years']:g} yrs · {details['mileage']:,} mi", ""]
    lines += ["## Answer", res["answer"], "", "## Sources"]
    for i, s in enumerate(res.get("sources", []), 1):
        lines.append(f"{i}. [{s.get('source')}] {s.get('text', '')[:300]}")
    return "\n".join(lines)


def render_assistant(msg, idx):
    with st.chat_message("assistant", avatar=":material/directions_car:"):
        if msg.get("error"):
            st.error(msg["error"])
            return
        res, details = msg["response"], msg.get("warranty_details")
        conf = res.get("confidence") or {}
        ui.html(ui.route_badge(res["route"], res.get("timings"), conf))
        if conf.get("deferred"):
            ui.defer_notice(conf)
        code = visuals.find_dtc(msg["question"])
        if code:
            visuals.dtc_decoder(code)

        if res.get("verdict"):
            label = f"{details['manufacturer']} · {ui.pretty(details['component'])}" if details else None
            ui.verdict_block(res["verdict"], details and details["vehicle_age_years"],
                             details and details["mileage"], title=label)

        with st.container(key=f"answer-{idx}"):
            st.markdown(res["answer"])

        sources = res.get("sources", [])
        ui.pipeline_trace(res["route"], res.get("timings"), bool(res.get("verdict")), sources, conf)

        with st.expander(f"Evidence — {len(sources)} retrieved sources", icon=":material/library_books:"):
            for i, s in enumerate(sources, 1):
                ui.source_card(i, s)

        c1, c2, _ = st.columns([1.2, 1.4, 4])
        with c1:
            rating = st.feedback("thumbs", key=f"fb-{idx}")
            sent = st.session_state.setdefault("fb_sent", set())
            if rating is not None and idx not in sent:
                api.send_feedback(msg["question"], res["answer"], res["route"], "up" if rating == 1 else "down")
                sent.add(idx)
                st.toast("Thanks — feedback saved for evaluation.")
        with c2:
            st.download_button("Download report", report_markdown(msg["question"], res, details),
                               file_name=f"autodiag_report_{idx}.md", mime="text/markdown",
                               icon=":material/download:", key=f"dl-{idx}")


# ---------------------------------------------------------------- header
left, right = st.columns([3, 1.3], vertical_alignment="bottom")
with left:
    ui.page_header("Hybrid retrieval · grounded answers", "What's wrong with the vehicle?",
                   "Describe a symptom, paste a DTC code, or ask about coverage. "
                   "Every answer is grounded in DTC data, NHTSA complaints and manufacturer warranty booklets.")
with right:
    mode = st.segmented_control("Routing", list(MODES), default="Auto-route", key="mode")

pending = None

# ---------------------------------------------------------------- sidebar extras (this page only)
with st.sidebar:
    st.markdown("### Voice question")
    audio = st.audio_input("Record a question", key="voice", label_visibility="collapsed")
    if audio is not None:
        digest = hashlib.md5(audio.getvalue()).hexdigest()
        if digest != st.session_state.get("voice_hash"):
            st.session_state.voice_hash = digest
            try:
                with st.spinner("Transcribing…"):
                    pending = api.transcribe(audio.getvalue())
                st.session_state.last_voice = pending
            except api.ApiError as e:
                st.error(f"Transcription failed — {e}")
    if st.session_state.get("last_voice"):
        st.caption(f"Heard: “{st.session_state.last_voice}”")

    st.markdown("### Conversation")
    if st.button("Clear conversation", icon=":material/delete_sweep:", use_container_width=True, disabled=not messages):
        messages.clear()
        st.session_state.pop("fb_sent", None)
        st.rerun()

# ---------------------------------------------------------------- empty state
if not messages:
    st.write("")
    visuals.car_hero()
    st.write("")
    cols = st.columns(3)
    with cols[0]:
        ui.feature_card("🔎", "Hybrid search + re-ranking", "Semantic BGE-M3 vectors and BM25 keywords, fused with "
                        "RRF and re-ranked by a cross-encoder — catches both “rough idle” and exact codes like P0301.")
    with cols[1]:
        ui.feature_card("🛡️", "Rules-checked warranty", "Coverage verdicts come from a deterministic rules table, "
                        "never from the LLM guessing mileage maths.")
    with cols[2]:
        ui.feature_card("📚", "Cited, confidence-gated", "Every answer shows its sources and an evidence score. "
                        "Weak matches are deferred to human review instead of guessed.")
    st.write("")
    st.markdown("##### Try a question")
    grid = st.columns(3)
    for i, (tag, text) in enumerate(EXAMPLES):
        if grid[i % 3].button(f"**{tag}**  \n{text}", key=f"example-{i}", use_container_width=True):
            pending = text

# ---------------------------------------------------------------- history
for idx, msg in enumerate(messages):
    if msg["role"] == "user":
        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(msg["content"])
    else:
        render_assistant(msg, idx)

# ---------------------------------------------------------------- new question
typed = st.chat_input("Describe a symptom, paste a DTC code, or ask about coverage…")
if typed:
    pending = typed

if pending:
    details = vehicle_details()
    messages.append({"role": "user", "content": pending})
    with st.chat_message("user", avatar=":material/person:"):
        st.markdown(pending)
    with st.chat_message("assistant", avatar=":material/directions_car:"):
        with st.spinner("Routing → retrieving (dense + BM25) → re-ranking → generating…"):
            try:
                res = api.ask(pending, warranty_details=details, route_override=MODES.get(mode))
                messages.append({"role": "assistant", "question": pending, "response": res,
                                 "warranty_details": details if res.get("verdict") else None})
                st.session_state.query_log.append({
                    "route": res["route"],
                    "total_ms": (res.get("timings") or {}).get("total_ms"),
                    "verdict": (res.get("verdict") or {}).get("status"),
                    "confidence": (res.get("confidence") or {}).get("level"),
                    "deferred": (res.get("confidence") or {}).get("deferred", False),
                })
            except api.ApiError as e:
                messages.append({"role": "assistant", "question": pending, "error": str(e)})
    st.rerun()