"""
Confidence gate: decides whether the retrieved evidence is strong enough to answer.

Uses the cross-encoder (re-rank) score of the best retrieved chunk:
    top >= HIGH_THRESHOLD             -> "high"    answer normally
    THRESHOLD <= top < HIGH_THRESHOLD -> "medium"  answer, but flag "verify with a technician"
    top < THRESHOLD                   -> "low"     DEFER: no LLM answer, logged for human review
    no score (re-ranker unavailable)  -> "unknown" answer normally, confidence not measured

Thresholds can be changed in .env (CONFIDENCE_THRESHOLD, CONFIDENCE_HIGH) and are tuned in the evaluation step.
"""
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.30"))
HIGH_THRESHOLD = float(os.getenv("CONFIDENCE_HIGH", "0.60"))
REVIEW_QUEUE = Path("data/feedback/review_queue.jsonl")

DEFER_MESSAGE = (
    "**I couldn't find strong enough evidence to answer this reliably, so I've passed it to human review "
    "instead of guessing.**\n\n"
    "None of the retrieved DTC records, NHTSA complaints or warranty booklet pages closely matched the question. "
    "To get a grounded answer, try:\n"
    "- adding the exact **DTC code** from your scanner (e.g. P0301), or\n"
    "- describing **when** the symptom happens and **where** it seems to come from "
    "(e.g. \"clunk from front left when braking at low speed\"), or\n"
    "- naming the **manufacturer and component** for warranty questions.\n\n"
    "The closest sources found are listed under *Evidence* below for reference."
)


def assess_confidence(chunks: list, has_verdict: bool = False) -> dict:
    """chunks: retrieved chunks, each possibly carrying 'rerank_score'."""
    scores = [c["rerank_score"] for c in chunks if c.get("rerank_score") is not None]
    base = {"threshold": THRESHOLD, "high_threshold": HIGH_THRESHOLD}

    if not scores:
        return {**base, "level": "unknown", "top_score": None, "deferred": False,
                "reason": "Re-ranker unavailable — evidence strength could not be measured."}

    top = max(scores)
    if top >= HIGH_THRESHOLD:
        return {**base, "level": "high", "top_score": top, "deferred": False,
                "reason": "Strong match between the question and the retrieved evidence."}
    if top >= THRESHOLD:
        return {**base, "level": "medium", "top_score": top, "deferred": False,
                "reason": "Partial match — verify the suggested causes with a technician."}

    # Low evidence. A warranty verdict comes from the deterministic rules table, not from
    # retrieval, so it is still safe to answer; everything else is deferred.
    if has_verdict:
        return {**base, "level": "low", "top_score": top, "deferred": False,
                "reason": "Weak document match, but the coverage verdict comes from the rules table."}
    return {**base, "level": "low", "top_score": top, "deferred": True,
            "reason": "Evidence below the confidence threshold — deferred to human review."}


def log_deferral(query: str, route: str, confidence: dict, chunks: list):
    """Appends a deferred question to the human-review queue."""
    REVIEW_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "route": route,
        "top_score": confidence.get("top_score"),
        "threshold": confidence.get("threshold"),
        "closest_sources": [c["text"][:200] for c in chunks[:3]],
    }
    with open(REVIEW_QUEUE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    tests = [
        ("strong evidence", [{"rerank_score": 0.89}, {"rerank_score": 0.70}], False),
        ("partial evidence", [{"rerank_score": 0.45}], False),
        ("weak evidence", [{"rerank_score": 0.08}], False),
        ("weak evidence + verdict", [{"rerank_score": 0.08}], True),
        ("re-ranker down", [{"rerank_score": None}], False),
    ]
    for name, chunks, verdict in tests:
        c = assess_confidence(chunks, has_verdict=verdict)
        print(f"{name:26s} -> level={c['level']:8s} deferred={c['deferred']}  top={c['top_score']}")