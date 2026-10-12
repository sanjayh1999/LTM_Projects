"""
Step 4b — End-to-end pipeline run on the gold set (48 in-scope + 4 out-of-scope queries).

For every query it runs the full system (router -> hybrid retrieval + re-rank -> rules check ->
confidence gate -> Gemini) and records:
    route vs expected route        -> router accuracy
    deferred / confidence level    -> % deferred (in-scope should be low, out-of-scope should be 100%)
    timings                        -> median / p95 end-to-end latency
    answer + retrieved contexts    -> input for the RAGAS step

Results are saved after EVERY query to data/eval/pipeline_runs.jsonl, so if Gemini rate-limits or
the network drops, just run the script again — finished queries are skipped.

Run from the project root (personal network, so Qdrant is reachable):
    python src/eval/eval_pipeline.py
Takes ~10–15 minutes (52 queries, pause between calls to respect Gemini rate limits).
"""
import sys
import json
import time
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "src" / "pipeline"))

from orchestrator import run_pipeline
import generator
import hybrid_retrieval  # same module object the orchestrator uses (src/retrieval is on sys.path)

# Track whether the dense side really ran. hybrid_retrieval silently falls back to BM25-only when
# Qdrant/embeddings fail, so we wrap dense_search to record failures for the guard below.
_dense_state = {"ok": None}
_original_dense_search = hybrid_retrieval.dense_search


def _tracked_dense_search(*args, **kwargs):
    _dense_state["ok"] = False
    results = _original_dense_search(*args, **kwargs)
    _dense_state["ok"] = True
    return results


hybrid_retrieval.dense_search = _tracked_dense_search

GOLD_FILE = Path("data/gold/gold_set.jsonl")
OUT_DIR = Path("data/eval")
RUNS_FILE = OUT_DIR / "pipeline_runs.jsonl"
PAUSE_SECONDS = 6  # gap between queries so the Gemini free tier is not rate-limited


def load_done():
    if not RUNS_FILE.exists():
        return {}
    done = {}
    for line in open(RUNS_FILE, encoding="utf-8"):
        r = json.loads(line)
        if not r.get("error"):
            done[r["id"]] = r
    return done


def percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    idx = min(len(values) - 1, max(0, round(p / 100 * (len(values) - 1))))
    return values[idx]


def main():
    gold = [json.loads(line) for line in open(GOLD_FILE, encoding="utf-8")]
    done = load_done()
    todo = [g for g in gold if g["id"] not in done]
    print(f"Gold queries: {len(gold)} | already done: {len(done)} | to run: {len(todo)}\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # rewrite the file with only successful runs, then append new ones
    with open(RUNS_FILE, "w", encoding="utf-8") as f:
        for r in done.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    for n, g in enumerate(todo, 1):
        expected_route = "warranty" if g["type"] == "warranty" else "diagnosis"
        record = {"id": g["id"], "type": g["type"], "query": g["query"],
                  "expected_route": expected_route, "reference_answer": g.get("reference_answer")}
        t0 = time.perf_counter()
        try:
            generator.LAST_MODEL = None
            _dense_state["ok"] = None
            res = run_pipeline(g["query"], warranty_details=g.get("warranty_details"))

            # Guard: never save a run where part of the real pipeline silently fell back,
            # otherwise the numbers would not describe the actual system. Such runs are retried later.
            if _dense_state["ok"] is False:
                raise RuntimeError("Dense search fell back to BM25-only (Qdrant/embeddings unreachable or no credit)")
            if res["confidence"]["level"] == "unknown":
                raise RuntimeError("Re-ranker unavailable (no OpenRouter credit?) — confidence could not be measured")

            record.update({
                "route": res["route"],
                "route_correct": res["route"] == expected_route,
                "deferred": res["confidence"]["deferred"],
                "confidence_level": res["confidence"]["level"],
                "top_score": res["confidence"]["top_score"],
                "verdict": (res.get("verdict") or {}).get("status"),
                "answer": res["answer"],
                "generator_model": generator.LAST_MODEL if not res["confidence"]["deferred"] else None,
                "contexts": [c["text"] for c in res["retrieved_chunks"]],
                "timings": res["timings"],
                "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
            })
            status = "DEFERRED" if record["deferred"] else f"answered ({record['confidence_level']})"
            print(f"[{n:2d}/{len(todo)}] {g['id']} {status:22s} route={record['route']:9s} "
                  f"{record['timings']['total_ms'] / 1000:5.1f}s  model={record['generator_model']}")
        except Exception as e:
            record["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            print(f"[{n:2d}/{len(todo)}] {g['id']} ERROR {record['error'][:120]}")
        with open(RUNS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        time.sleep(PAUSE_SECONDS)

    # ---------------------------------------------------------------- summary
    runs = [json.loads(line) for line in open(RUNS_FILE, encoding="utf-8")]
    ok = [r for r in runs if not r.get("error")]
    errors = [r for r in runs if r.get("error")]
    in_scope = [r for r in ok if r["type"] != "out_of_scope"]
    oos = [r for r in ok if r["type"] == "out_of_scope"]
    answered = [r for r in in_scope if not r["deferred"]]

    totals = [r["timings"]["total_ms"] for r in answered]
    retrieval = [r["timings"]["retrieval_ms"] for r in ok]
    generation = [r["timings"]["generation_ms"] for r in answered if "generation_ms" in r["timings"]]

    summary = {
        "queries_run": len(ok),
        "errors": len(errors),
        "router_accuracy": round(sum(r["route_correct"] for r in in_scope) / len(in_scope), 3) if in_scope else None,
        "router_correct": f"{sum(r['route_correct'] for r in in_scope)}/{len(in_scope)}",
        "in_scope_deferred_pct": round(100 * sum(r["deferred"] for r in in_scope) / len(in_scope), 1) if in_scope else None,
        "in_scope_deferred": f"{sum(r['deferred'] for r in in_scope)}/{len(in_scope)}",
        "out_of_scope_deferred": f"{sum(r['deferred'] for r in oos)}/{len(oos)}",
        "confidence_levels": {lvl: sum(r["confidence_level"] == lvl for r in in_scope)
                              for lvl in ("high", "medium", "low", "unknown")},
        "latency_ms": {
            "end_to_end_median": round(statistics.median(totals), 0) if totals else None,
            "end_to_end_p95": round(percentile(totals, 95), 0) if totals else None,
            "retrieval_median": round(statistics.median(retrieval), 0) if retrieval else None,
            "generation_median": round(statistics.median(generation), 0) if generation else None,
        },
        "answered_by_model": dict(Counter(r.get("generator_model") or "not recorded (earlier run)" for r in answered)),
        "warranty_verdicts": {r["id"]: r["verdict"] for r in in_scope if r["type"] == "warranty"},
    }
    with open(OUT_DIR / "pipeline_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 70)
    print("END-TO-END SUMMARY")
    print("=" * 70)
    print(f"Queries run OK          : {summary['queries_run']}   (errors: {summary['errors']})")
    print(f"Router accuracy         : {summary['router_correct']}  = {summary['router_accuracy']}")
    print(f"In-scope deferred       : {summary['in_scope_deferred']}  = {summary['in_scope_deferred_pct']}%")
    print(f"Out-of-scope deferred   : {summary['out_of_scope_deferred']}  (target: all)")
    print(f"Confidence levels       : {summary['confidence_levels']}")
    lat = summary["latency_ms"]
    print(f"Latency end-to-end      : median {lat['end_to_end_median']} ms | p95 {lat['end_to_end_p95']} ms")
    print(f"  retrieval median      : {lat['retrieval_median']} ms")
    print(f"  generation median     : {lat['generation_median']} ms")
    print(f"Answered by model       : {summary['answered_by_model']}")
    print(f"Warranty verdicts       : {summary['warranty_verdicts']}")
    if errors:
        print(f"\n{len(errors)} queries failed — run the script again to retry only those.")
    print(f"\nSaved: {RUNS_FILE} and {OUT_DIR / 'pipeline_summary.json'}")


if __name__ == "__main__":
    main()