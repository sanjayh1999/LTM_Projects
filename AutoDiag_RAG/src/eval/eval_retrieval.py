"""
Step 4a — Retrieval ablation on the gold set (48 in-scope queries).

Compares four retrievers on the SAME queries:
    bm25            keyword search only
    dense           BGE-M3 vectors (Qdrant) only
    hybrid          dense + BM25 fused with RRF (no re-ranking)
    hybrid_rerank   hybrid top-20 re-ranked by the cross-encoder (the production pipeline)

Metrics at k = 5 (binary relevance from the gold-set rules):
    Hit@5     1 if at least one relevant chunk is in the top 5
    Recall@5  relevant chunks in top 5 / min(5, total relevant in corpus)   (capped recall)
    MRR@5     1 / rank of the first relevant chunk (0 if none in the top 5)
    nDCG@5    rank-aware gain: relevant chunks higher up score more
    P@5       relevant chunks in top 5 / 5

Run from the project root (needs Qdrant reachable — use the personal network or QDRANT_LOCAL_PATH):
    python src/eval/eval_retrieval.py
Cost: 48 embedding calls + 48 re-rank calls on OpenRouter (about $0.05).
"""
import sys
import json
import math
import time
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "src" / "retrieval"))
sys.path.append(str(ROOT / "src" / "eval"))

from hybrid_retrieval import dense_search, bm25_search, reciprocal_rank_fusion
from reranker import rerank
from build_gold import is_relevant

GOLD_FILE = Path("data/gold/gold_set.jsonl")
OUT_DIR = Path("data/eval")
K = 5
CANDIDATES = 20
RETRIEVERS = ["bm25", "dense", "hybrid", "hybrid_rerank"]
METRICS = ["hit", "recall", "mrr", "ndcg", "precision"]
TYPES = ["dtc_exact", "dtc_paraphrase", "symptom", "warranty"]


def score(rule, n_relevant, top):
    """top: list of (text, metadata) best first. Returns metric dict + relevance flags."""
    rels = [is_relevant(rule, text, meta) for text, meta in top[:K]]
    ideal = min(K, n_relevant) if n_relevant else K
    first = next((i for i, r in enumerate(rels) if r), None)
    dcg = sum(1 / math.log2(i + 2) for i, r in enumerate(rels) if r)
    idcg = sum(1 / math.log2(i + 2) for i in range(ideal))
    return {
        "hit": 1.0 if first is not None else 0.0,
        "recall": sum(rels) / ideal,
        "mrr": 1 / (first + 1) if first is not None else 0.0,
        "ndcg": dcg / idcg if idcg else 0.0,
        "precision": sum(rels) / K,
    }, rels


def mean(values):
    return round(sum(values) / len(values), 3) if values else None


def main():
    gold = [json.loads(line) for line in open(GOLD_FILE, encoding="utf-8")]
    gold = [g for g in gold if g["type"] != "out_of_scope"]
    print(f"Evaluating {len(gold)} gold queries x {len(RETRIEVERS)} retrievers (k={K})\n")

    rows, rerank_failures = [], 0
    for n, g in enumerate(gold, 1):
        q = g["query"]

        t0 = time.perf_counter()
        bm = bm25_search(q, top_k=CANDIDATES)
        bm_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        try:
            dn = dense_search(q, top_k=CANDIDATES)
        except Exception as e:
            sys.exit(f"\nDense search failed ({type(e).__name__}: {e}).\n"
                     "Qdrant/OpenRouter is not reachable. Switch to the personal network "
                     "(or set QDRANT_LOCAL_PATH) and run again — the ablation needs real dense results.")
        dn_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        fused = reciprocal_rank_fusion(dn, bm, top_n=CANDIDATES)
        rrf_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        rr = rerank(q, fused, top_n=K)
        rr_ms = (time.perf_counter() - t0) * 1000
        if rr and rr[0].get("rerank_score") is None:
            rerank_failures += 1

        tops = {
            "bm25": [(t, m) for t, m, _ in bm],
            "dense": [(t, m) for t, m, _ in dn],
            "hybrid": [(r["text"], r["payload"]) for r in fused],
            "hybrid_rerank": [(r["text"], r["payload"]) for r in rr],
        }
        latency = {
            "bm25": bm_ms,
            "dense": dn_ms,
            "hybrid": bm_ms + dn_ms + rrf_ms,
            "hybrid_rerank": bm_ms + dn_ms + rrf_ms + rr_ms,
        }

        row = {"id": g["id"], "type": g["type"], "query": q, "n_relevant": g["n_relevant"]}
        for name in RETRIEVERS:
            metrics, rels = score(g["relevance"], g["n_relevant"], tops[name])
            row[name] = {**metrics, "latency_ms": round(latency[name], 1), "relevant_flags": rels,
                         "top_texts": [t[:120] for t, _ in tops[name][:K]]}
        rows.append(row)
        print(f"[{n:2d}/{len(gold)}] {g['id']}  "
              + "  ".join(f"{name}: nDCG {row[name]['ndcg']:.2f}" for name in RETRIEVERS))

    # ---------------------------------------------------------------- aggregate
    summary = {"k": K, "n_queries": len(rows), "rerank_failures": rerank_failures,
               "overall": {}, "by_type": {}, "n_by_type": {}}
    for name in RETRIEVERS:
        summary["overall"][name] = {m: mean([r[name][m] for r in rows]) for m in METRICS}
        summary["overall"][name]["median_latency_ms"] = round(statistics.median(r[name]["latency_ms"] for r in rows), 1)
    for t in TYPES:
        subset = [r for r in rows if r["type"] == t]
        summary["n_by_type"][t] = len(subset)
        summary["by_type"][t] = {name: {m: mean([r[name][m] for r in subset]) for m in METRICS} for name in RETRIEVERS}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "retrieval_per_query.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_DIR / "retrieval_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # ---------------------------------------------------------------- print tables
    print("\n" + "=" * 86)
    print(f"OVERALL ({len(rows)} queries, k={K})")
    print("=" * 86)
    print(f"{'Retriever':15s} {'Hit@5':>7s} {'Recall@5':>9s} {'MRR@5':>7s} {'nDCG@5':>7s} {'P@5':>6s} {'Median ms':>10s}")
    for name in RETRIEVERS:
        o = summary["overall"][name]
        print(f"{name:15s} {o['hit']:>7.3f} {o['recall']:>9.3f} {o['mrr']:>7.3f} {o['ndcg']:>7.3f} "
              f"{o['precision']:>6.3f} {o['median_latency_ms']:>10.0f}")

    for metric, label in [("recall", "Recall@5"), ("mrr", "MRR@5"), ("ndcg", "nDCG@5")]:
        print("\n" + "-" * 86)
        print(f"{label} BY QUERY TYPE")
        print("-" * 86)
        print(f"{'Retriever':15s} " + " ".join(f"{t + ' (' + str(summary['n_by_type'][t]) + ')':>18s}" for t in TYPES))
        for name in RETRIEVERS:
            print(f"{name:15s} " + " ".join(f"{summary['by_type'][t][name][metric]:>18.3f}" for t in TYPES))

    if rerank_failures:
        print(f"\nWARNING: re-ranker failed on {rerank_failures} queries (check OpenRouter credit) — "
              "hybrid_rerank numbers are not valid until this is 0.")
    print(f"\nSaved: {OUT_DIR / 'retrieval_summary.json'} and {OUT_DIR / 'retrieval_per_query.jsonl'}")


if __name__ == "__main__":
    main()