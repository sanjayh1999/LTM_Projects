"""System insights page: measured quality, corpus composition, pipeline and this session's usage."""
import pandas as pd
import streamlit as st
import api_client as api
import ui
import visuals

visuals.inject_css()

ui.page_header("Under the hood", "System insights",
               "How well the assistant performs on a 48-question test set, what it knows, and how a question "
               "flows through the pipeline.")
st.write("")

# ---------------------------------------------------------------- measured quality (from data/eval)
ev = visuals.load_eval()
ret, pipe, rag = ev.get("retrieval") or {}, ev.get("pipeline") or {}, ev.get("ragas") or {}

st.markdown("#### Measured quality")
if not ret and not rag:
    st.caption("No evaluation results found. Run the scripts in src/eval to create data/eval/*.json.")
else:
    if pipe:
        lat = (pipe.get("latency_ms") or {}).get("end_to_end_median")
        cols = st.columns(4)
        with cols[0]:
            ui.stat_tile("Router accuracy", pipe.get("router_correct", "—"), "diagnosis vs warranty")
        with cols[1]:
            ui.stat_tile("Valid questions deferred", pipe.get("in_scope_deferred", "—"), "confidence gate")
        with cols[2]:
            ui.stat_tile("Off-topic deferred", pipe.get("out_of_scope_deferred", "—"), "refused instead of guessing")
        with cols[3]:
            ui.stat_tile("Median answer time", f"{lat / 1000:.1f}s" if lat else "—", "end-to-end")
        st.write("")

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        if ret:
            st.markdown("##### Retrieval: which search finds the right evidence?")
            metric_names = {"nDCG@5": "ndcg", "Hit@5": "hit", "Recall@5": "recall", "MRR@5": "mrr"}
            choice = st.segmented_control("Metric", list(metric_names), default="nDCG@5", key="ins_metric",
                                          label_visibility="collapsed") or "nDCG@5"
            key = metric_names[choice]
            labels = {"bm25": "BM25 keyword", "dense": "Dense (BGE-M3)", "hybrid": "Hybrid (RRF)",
                      "hybrid_rerank": "Hybrid + re-rank"}
            overall = ret.get("overall", {})
            visuals.metric_bars([(labels[k], overall[k][key]) for k in labels if k in overall],
                                best_label="Hybrid + re-rank")
            st.caption(f"{choice} on {ret.get('n_queries', 48)} test questions, top 5 results. "
                       "Highlighted: the configuration the assistant uses.")
    with right:
        if rag:
            st.markdown("##### Answers: RAGAS scores")
            o = rag.get("overall", {})
            r1, r2 = st.columns(2)
            with r1:
                ui.stat_tile("Faithfulness", f"{o.get('faithfulness', 0):.2f}", "claims backed by sources")
                st.write("")
                ui.stat_tile("Context precision", f"{o.get('context_precision', 0):.2f}", "useful sources ranked first")
            with r2:
                ui.stat_tile("Answer relevancy", f"{o.get('answer_relevancy', 0):.2f}", "answers the question asked")
                st.write("")
                ui.stat_tile("Context recall", f"{o.get('context_recall', 0):.2f}", "reference facts retrieved")
            st.caption(f"LLM judge: {rag.get('judge_model', '—')} on {rag.get('questions_scored', 48)} answers.")

    if ret.get("by_type"):
        with st.expander("Recall@5 by question type", icon=":material/table_chart:"):
            names = {"dtc_exact": "Exact DTC code", "dtc_paraphrase": "Fault described in words",
                     "symptom": "Owner symptom (NHTSA)", "warranty": "Warranty"}
            table = pd.DataFrame([
                {"Question type": names.get(t, t), "Questions": ret["n_by_type"].get(t),
                 "BM25": v["bm25"]["recall"], "Dense": v["dense"]["recall"],
                 "Hybrid": v["hybrid"]["recall"], "Hybrid + re-rank": v["hybrid_rerank"]["recall"]}
                for t, v in ret["by_type"].items()])
            bar = lambda label: st.column_config.ProgressColumn(label, min_value=0.0, max_value=1.0, format="%.2f")
            st.dataframe(table, hide_index=True, use_container_width=True, column_config={
                "BM25": bar("BM25"), "Dense": bar("Dense"), "Hybrid": bar("Hybrid"),
                "Hybrid + re-rank": bar("Hybrid + re-rank")})

st.write("")

# ---------------------------------------------------------------- corpus
stats = api.corpus_stats()
st.markdown("#### What it knows")
if not stats:
    st.warning("Can't load corpus statistics — make sure the API is running.")
else:
    src = stats.get("by_source", {})
    mfrs = stats.get("warranty_by_manufacturer", {})
    qpts = stats.get("qdrant_points")
    tiles = st.columns(4)
    with tiles[0]:
        ui.stat_tile("Indexed chunks", f"{stats.get('bm25_chunks', 0):,}", "BM25 keyword index")
    with tiles[1]:
        ui.stat_tile("Vector points", f"{qpts:,}" if qpts else "—", "Qdrant · BGE-M3 1024-d")
    with tiles[2]:
        ui.stat_tile("Owner complaints", f"{src.get('nhtsa', 0):,}", "NHTSA, 20 models × 7 years")
    with tiles[3]:
        ui.stat_tile("Manufacturers", f"{len(mfrs)}", "warranty booklets indexed")

    st.write("")
    a, b = st.columns(2, gap="large")
    with a:
        st.markdown("##### Corpus composition (chunks)")
        labels = {"nhtsa": "NHTSA complaints", "obdex": "DTC code library", "warranty": "Warranty clauses"}
        ui.bar_list(sorted(((labels.get(k, k), v) for k, v in src.items()), key=lambda x: -x[1]))
    with b:
        st.markdown("##### Warranty clauses by manufacturer")
        ui.bar_list(sorted(mfrs.items(), key=lambda x: -x[1]))

st.write("")
st.markdown("#### How a question flows")
ui.html("""
<div class="ad-card"><div class="ad-flow">
  <div class="ad-node">Question<small>typed or spoken (Whisper)</small></div><span class="ad-arrow">→</span>
  <div class="ad-node">Router<small>diagnosis / warranty</small></div><span class="ad-arrow">→</span>
  <div class="ad-node">Dense search<small>BGE-M3 → Qdrant</small></div><span class="ad-arrow">+</span>
  <div class="ad-node">Keyword search<small>BM25, local</small></div><span class="ad-arrow">→</span>
  <div class="ad-node">RRF fusion<small>top 20</small></div><span class="ad-arrow">→</span>
  <div class="ad-node">Re-rank<small>cross-encoder, top 5</small></div><span class="ad-arrow">→</span>
  <div class="ad-node">Rules check<small>warranty only</small></div><span class="ad-arrow">→</span>
  <div class="ad-node">Confidence gate<small>defer weak evidence</small></div><span class="ad-arrow">→</span>
  <div class="ad-node">Gemini<small>grounded, cited answer</small></div>
</div></div>
""")

st.write("")
st.markdown("#### This session")
log = st.session_state.get("query_log", [])
if not log:
    st.caption("No questions asked yet — try the Assistant or the Warranty checker.")
else:
    times = [q["total_ms"] for q in log if q.get("total_ms")]
    cols = st.columns(4)
    with cols[0]:
        ui.stat_tile("Questions", str(len(log)))
    with cols[1]:
        ui.stat_tile("Avg. response", f"{sum(times) / len(times) / 1000:.1f}s" if times else "—", "end-to-end")
    with cols[2]:
        n_diag = sum(1 for q in log if q["route"] == "diagnosis")
        ui.stat_tile("Diagnosis / warranty", f"{n_diag} / {len(log) - n_diag}", "router split")
    with cols[3]:
        n_def = sum(1 for q in log if q.get("deferred"))
        ui.stat_tile("Deferred", str(n_def), "sent to human review")

st.write("")
st.markdown("#### Stack")
stack = st.columns(4)
for col, (icon, title, body) in zip(stack, [
    ("🧠", "Embeddings", "BGE-M3 (1024-d), corpus embedded on GPU; queries via OpenRouter."),
    ("🎯", "Re-ranking", "Cohere Rerank 3.5 cross-encoder re-scores the fused top 20."),
    ("✍️", "Generation", "Gemini 3.6 Flash, with Groq and OpenRouter as automatic fallbacks."),
    ("🎙️", "Voice", "Groq-hosted Whisper large-v3-turbo speech-to-text."),
]):
    with col:
        ui.feature_card(icon, title, body)