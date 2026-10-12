# AutoDiag-RAG

**Hybrid retrieval for automotive fault diagnosis and warranty validation**

M.Tech Individual Project 1 · Advanced Industry Integrated Programme (University × LTIMindtree × L&T EduTech)
Sanjay Suresh Hullyal

AutoDiag-RAG answers vehicle diagnosis and warranty questions, typed or spoken, with cited evidence from a
59,504-chunk knowledge base: an OBD-II fault code library, NHTSA owner complaints and six manufacturers'
2026 warranty booklets. Coverage decisions come from a deterministic rules engine, not from the LLM.

## How a question flows

```
Question (text / voice)
   → Router (diagnosis / warranty)
   → Dense search (BGE-M3 → Qdrant) + Keyword search (BM25)
   → Reciprocal Rank Fusion (top 20)
   → Cross-encoder re-rank (top 5)
   → Rules check (warranty questions only)
   → Confidence gate (weak evidence is deferred to human review)
   → Grounded, cited answer (Gemini, with Groq / OpenRouter failover)
```

## Results (48-question gold set)

| Retriever | Hit@5 | Recall@5 | MRR@5 | nDCG@5 |
|---|---|---|---|---|
| BM25 only | 0.812 | 0.521 | 0.738 | 0.552 |
| Dense only (BGE-M3) | 0.792 | 0.387 | 0.664 | 0.425 |
| Hybrid (RRF) | 0.896 | 0.509 | 0.778 | 0.543 |
| **Hybrid + re-rank** | **0.938** | **0.640** | **0.891** | **0.691** |

| Answer quality (RAGAS metrics, LLM judge) | Score |
|---|---|
| Faithfulness | 0.928 |
| Answer relevancy | 0.824 |
| Context precision | 0.769 |
| Context recall | 0.664 |

System results:
- **Routing:** 48/48 questions routed correctly.
- **Warranty:** 10/10 coverage verdicts correct.
- **Confidence gate:** 0/48 valid questions deferred; every off-topic question deferred.
- **Speed:** median answer time 10.9 s.

## Project structure

```
src/
  ingest/      load DTC codes, NHTSA complaints and warranty PDFs into chunks
  index/       BGE-M3 embeddings, BM25 index, Qdrant upload
  retrieval/   hybrid search (dense + BM25 + RRF) and cross-encoder re-ranking
  pipeline/    router, warranty rules engine, confidence gate, generator, orchestrator
  api/         FastAPI backend (/query, /warranty/check, /transcribe, /stats, /feedback)
  eval/        gold set, retrieval ablation, end-to-end run, RAGAS-style scoring
app/           Streamlit front end (assistant, warranty checker, system insights)
data/
  warranty_rules.json   coverage limits for Honda, Hyundai, Toyota, Ford, Nissan, Kia
  gold/                 48 test questions + 4 off-topic questions with relevance rules
  eval/                 evaluation results
```

## Run it locally

1. **Set up Python.** Python 3.11 is required:
   ```bash
   python -m venv venv
   venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   ```
2. **Add your keys.** Copy `.env.example` to `.env` and fill in the keys: Gemini, OpenRouter, Groq, Qdrant.
3. **Build the data.** Raw data and indexes are not stored in this repo. Run the scripts in `src/ingest` and `src/index` to rebuild them.
4. **Start the backend:**
   ```bash
   uvicorn src.api.main:app --port 8000
   ```
5. **Start the front end:**
   ```bash
   streamlit run app/streamlit_app.py
   ```

## Tech stack

Python 3.11 · BGE-M3 · Qdrant · rank_bm25 · Cohere Rerank 3.5 (via OpenRouter) · Gemini · Groq (Whisper, gpt-oss) ·
FastAPI · Streamlit

## Data sources

NHTSA Complaints API · OBDex DTC database · 2026 manufacturer warranty booklets (Honda, Hyundai, Toyota, Ford,
Nissan, Kia).
