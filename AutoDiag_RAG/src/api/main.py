import sys
import os
import json
from datetime import datetime, timezone
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "pipeline"))

import requests
import urllib3
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Literal

from orchestrator import run_pipeline
from warranty_tool import check_warranty, WARRANTY_RULES
from hybrid_retrieval import corpus_stats  # importable because orchestrator adds src/retrieval to sys.path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
FEEDBACK_FILE = Path("data/feedback/feedback.jsonl")

app = FastAPI(title="AutoDiag-RAG API")


class WarrantyDetails(BaseModel):
    manufacturer: str
    component: str
    vehicle_age_years: float
    mileage: int


class QueryRequest(BaseModel):
    query: str
    warranty_details: Optional[WarrantyDetails] = None
    route_override: Optional[Literal["diagnosis", "warranty"]] = None


class QueryResponse(BaseModel):
    route: str
    answer: str
    sources: list
    verdict: Optional[dict] = None
    confidence: Optional[dict] = None
    timings: Optional[dict] = None


class FeedbackRequest(BaseModel):
    query: str
    answer: str
    route: str
    rating: Literal["up", "down"]
    comment: Optional[str] = None


@app.get("/")
def root():
    return {"status": "AutoDiag-RAG API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    warranty_dict = request.warranty_details.model_dump() if request.warranty_details else None

    try:
        result = run_pipeline(
            request.query,
            warranty_details=warranty_dict,
            route_override=request.route_override,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Pipeline error: {type(e).__name__}: {e}")

    sources = []
    for chunk in result["retrieved_chunks"]:
        meta = chunk["metadata"]
        sources.append({
            "text": chunk["text"][:600],
            "source": meta.get("source", "unknown"),
            "doc_type": meta.get("doc_type", "unknown"),
            "manufacturer": meta.get("manufacturer"),
            "page": meta.get("page"),
            "dtc_code": meta.get("dtc_code"),
            "make": meta.get("make"),
            "model": meta.get("model"),
            "year": meta.get("year"),
            "components": meta.get("components"),
            "fused_score": chunk.get("fused_score"),
            "dense_rank": chunk.get("dense_rank"),
            "bm25_rank": chunk.get("bm25_rank"),
            "rerank_score": chunk.get("rerank_score"),
        })

    return QueryResponse(
        route=result["route"],
        answer=result["answer"],
        sources=sources,
        verdict=result.get("verdict"),
        confidence=result.get("confidence"),
        timings=result.get("timings"),
    )


@app.get("/stats")
def stats():
    """Corpus composition for the dashboard page."""
    return corpus_stats()


@app.get("/warranty/options")
def warranty_options():
    """Manufacturers and their rule-backed components (drives the UI dropdowns)."""
    return WARRANTY_RULES


@app.post("/warranty/check")
def warranty_check(details: WarrantyDetails):
    """
    Instant, deterministic check (no LLM call). Returns the verdict for the
    chosen component plus a coverage matrix for every component this
    manufacturer has rules for, at the same age and mileage.
    """
    verdict = check_warranty(
        details.manufacturer, details.component, details.vehicle_age_years, details.mileage
    )
    mfr_rules = WARRANTY_RULES.get(details.manufacturer.strip().title(), {})
    matrix = []
    for component in mfr_rules:
        v = check_warranty(details.manufacturer, component, details.vehicle_age_years, details.mileage)
        matrix.append({"component": component, "status": v["status"], "rule": v["rule_used"]})
    return {"verdict": verdict, "coverage_matrix": matrix}


@app.post("/transcribe")
async def transcribe(request: Request):
    """Speech-to-text via Groq's hosted Whisper. Body: raw audio bytes (wav)."""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not set in .env")
    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")

    response = requests.post(
        GROQ_TRANSCRIBE_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        data={"model": "whisper-large-v3-turbo", "language": "en"},
        verify=False,  # same corporate-network workaround used in embeddings.py
        timeout=60,
    )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {response.text[:300]}")
    return {"text": response.json().get("text", "").strip()}


@app.post("/feedback")
def feedback(item: FeedbackRequest):
    """Stores thumbs up/down on answers — useful evidence for the evaluation chapter."""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = item.model_dump()
    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"saved": True}