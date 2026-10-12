import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from router import classify_query
from warranty_tool import check_warranty
from confidence import assess_confidence, log_deferral, DEFER_MESSAGE
sys.path.append(str(Path(__file__).parent.parent / "retrieval"))
from hybrid_retrieval import search
from generator import build_diagnosis_prompt, build_warranty_prompt, generate_answer


def run_pipeline(query: str, warranty_details: dict = None, route_override: str = None) -> dict:
    """
    warranty_details (optional): {"manufacturer": str, "component": str,
                                   "vehicle_age_years": float, "mileage": int}
    Required only if the query routes to 'warranty' and you want the
    deterministic check to run. If omitted on a warranty query, the
    system will answer from retrieved text alone (no verdict).

    route_override (optional): "diagnosis" or "warranty" to skip the router
    (used when the user picks a mode explicitly in the UI).
    """
    timings = {}

    # 1. Route
    t0 = time.perf_counter()
    if route_override in ("diagnosis", "warranty"):
        route = route_override
    else:
        route = classify_query(query)
    timings["routing_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    print(f"[Router] Classified as: {route}")

    # 2. Retrieve (hybrid + re-rank)
    t0 = time.perf_counter()
    retrieved = search(query, candidates=20, top_n=5)
    timings["retrieval_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    retrieved_chunks = [
        {
            "text": r["text"],
            "metadata": r["payload"],
            "fused_score": r["fused_score"],
            "dense_rank": r["dense_rank"],
            "bm25_rank": r["bm25_rank"],
            "rerank_score": r.get("rerank_score"),
        }
        for r in retrieved
    ]
    print(f"[Retrieval] Fetched {len(retrieved_chunks)} chunks")

    # 3. Deterministic warranty check (only for warranty questions with vehicle details)
    verdict = None
    if route == "warranty" and warranty_details:
        t0 = time.perf_counter()
        verdict = check_warranty(
            warranty_details["manufacturer"],
            warranty_details["component"],
            warranty_details["vehicle_age_years"],
            warranty_details["mileage"],
        )
        timings["warranty_check_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        print(f"[Warranty Tool] Verdict: {verdict['status']}")

    # 4. Confidence gate
    confidence = assess_confidence(retrieved_chunks, has_verdict=verdict is not None)
    print(f"[Confidence] level={confidence['level']} top={confidence['top_score']} deferred={confidence['deferred']}")

    # 5. Generate — or defer to human review
    if confidence["deferred"]:
        log_deferral(query, route, confidence, retrieved_chunks)
        answer = DEFER_MESSAGE
    else:
        if verdict is not None:
            prompt = build_warranty_prompt(query, retrieved_chunks, verdict)
        else:
            prompt = build_diagnosis_prompt(query, retrieved_chunks)
        t0 = time.perf_counter()
        answer = generate_answer(prompt)
        timings["generation_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    timings["total_ms"] = round(sum(timings.values()), 1)

    return {
        "route": route,
        "retrieved_chunks": retrieved_chunks,
        "answer": answer,
        "verdict": verdict,
        "confidence": confidence,
        "timings": timings,
    }


if __name__ == "__main__":
    tests = [
        ("TEST 1: Diagnosis query (expect high confidence)",
         "My car makes a rattling noise when accelerating", None),
        ("TEST 2: Warranty query with verdict (never deferred)",
         "Is my powertrain still covered under warranty?",
         {"manufacturer": "Honda", "component": "powertrain", "vehicle_age_years": 4, "mileage": 55000}),
        ("TEST 3: Off-topic query (expect DEFERRED)",
         "What is a good recipe for chocolate cake?", None),
    ]
    for title, q, details in tests:
        print("=" * 60)
        print(title)
        print("=" * 60)
        r = run_pipeline(q, warranty_details=details)
        c = r["confidence"]
        print(f"\nCONFIDENCE: {c['level']} (top score {c['top_score']}) | deferred={c['deferred']}")
        print(f"ANSWER:\n{r['answer'][:500]}\n")
        print(f"TIMINGS: {r['timings']}\n")