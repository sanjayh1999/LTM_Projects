import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent))

from index.embeddings import embed_text
from index.bm25_index import simple_tokenize
from reranker import rerank
from qdrant_client import QdrantClient
from collections import Counter
import pickle
import os
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "autodiag_rag"
BM25_INDEX_DIR = Path("data/processed/bm25_index")

QDRANT_LOCAL_PATH = os.getenv("QDRANT_LOCAL_PATH")
if QDRANT_LOCAL_PATH:
    client = QdrantClient(path=QDRANT_LOCAL_PATH)   # local mode — works on the office network
else:
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30, check_compatibility=False)

# Load BM25 index once at module load
with open(BM25_INDEX_DIR / "bm25.pkl", "rb") as f:
    _bm25 = pickle.load(f)
with open(BM25_INDEX_DIR / "chunks.pkl", "rb") as f:
    _bm25_chunks = pickle.load(f)


def dense_search(query_text, top_k=20):
    """Returns list of (chunk_text, payload, qdrant_point_id) ranked by dense similarity."""
    query_vector = embed_text(query_text)
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        using="dense",
        limit=top_k,
    )
    return [(r.payload["text"], r.payload, r.id) for r in results.points]


def bm25_search(query_text, top_k=20):
    """Returns list of (chunk_text, payload, synthetic_id) ranked by BM25 score."""
    tokenized_query = simple_tokenize(query_text)
    scores = _bm25.get_scores(tokenized_query)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    results = []
    for i in top_indices:
        chunk = _bm25_chunks[i]
        # Use chunk text itself as a stable identifier for fusion matching
        results.append((chunk["text"], chunk["metadata"], chunk["text"]))
    return results


def reciprocal_rank_fusion(dense_results, sparse_results, k=60, top_n=10):
    """
    Combines two ranked lists using RRF.
    Each result is (text, payload, id). We fuse on 'text' as the matching key,
    since dense uses Qdrant point IDs and sparse uses list position — text is
    the one thing guaranteed to be identical for the same chunk in both systems.

    Returns a list of dicts, best first:
        {"text", "payload", "fused_score", "dense_rank", "bm25_rank"}
    where a rank is 1-based, or None if that retriever did not return the chunk.
    """
    scores = {}
    data = {}  # text -> payload
    dense_rank = {}
    bm25_rank = {}

    for rank, (text, payload, _id) in enumerate(dense_results):
        scores[text] = scores.get(text, 0) + 1 / (k + rank + 1)
        data[text] = payload
        dense_rank[text] = rank + 1

    for rank, (text, payload, _id) in enumerate(sparse_results):
        scores[text] = scores.get(text, 0) + 1 / (k + rank + 1)
        data[text] = payload
        bm25_rank[text] = rank + 1

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {
            "text": text,
            "payload": data[text],
            "fused_score": fused_score,
            "dense_rank": dense_rank.get(text),
            "bm25_rank": bm25_rank.get(text),
        }
        for text, fused_score in ranked
    ]


def hybrid_search_detailed(query_text, top_k=20, top_n=10):
    """Hybrid search; falls back to BM25-only if the dense side (OpenRouter/Qdrant) is unreachable."""
    try:
        dense_results = dense_search(query_text, top_k=top_k)
    except Exception as e:
        print(f"[Retrieval] Dense search unavailable, using BM25 only: {type(e).__name__}: {e}")
        dense_results = []
    sparse_results = bm25_search(query_text, top_k=top_k)
    return reciprocal_rank_fusion(dense_results, sparse_results, top_n=top_n)


def hybrid_search(query_text, top_k=20, top_n=10):
    """Original interface, kept for existing callers: list of (text, payload, fused_score)."""
    return [
        (r["text"], r["payload"], r["fused_score"])
        for r in hybrid_search_detailed(query_text, top_k=top_k, top_n=top_n)
    ]


def search(query_text, candidates=20, top_n=5, use_rerank=True):
    """
    Full retrieval used by the pipeline:
    dense top-20 + BM25 top-20 -> RRF -> best `candidates` fused chunks -> cross-encoder re-rank -> top_n.
    use_rerank=False gives plain hybrid (used in the evaluation ablation).
    """
    fused = hybrid_search_detailed(query_text, top_k=20, top_n=candidates)
    if not use_rerank:
        return fused[:top_n]
    return rerank(query_text, fused, top_n=top_n)


def corpus_stats():
    """Counts of indexed chunks by source/doc type/manufacturer, for the UI dashboard."""
    by_source = Counter(c["metadata"].get("source", "unknown") for c in _bm25_chunks)
    by_doc_type = Counter(c["metadata"].get("doc_type", "unknown") for c in _bm25_chunks)
    warranty_by_mfr = Counter(
        c["metadata"].get("manufacturer", "Unknown")
        for c in _bm25_chunks
        if c["metadata"].get("doc_type") == "warranty"
    )
    # Warranty chunks carry the PDF filename as 'source'; group them under one label
    grouped = Counter()
    for src, n in by_source.items():
        grouped["warranty" if src.lower().endswith(".pdf") else src] += n

    try:
        qdrant_points = client.get_collection(COLLECTION_NAME).points_count
    except Exception:
        qdrant_points = None

    return {
        "bm25_chunks": len(_bm25_chunks),
        "qdrant_points": qdrant_points,
        "by_source": dict(grouped),
        "by_doc_type": dict(by_doc_type),
        "warranty_by_manufacturer": dict(warranty_by_mfr),
    }


if __name__ == "__main__":
    query = "car makes a rattling noise when accelerating"
    print(f"Query: {query}\n")

    print("=" * 60)
    print("WITHOUT re-ranking (hybrid RRF only)")
    print("=" * 60)
    for i, r in enumerate(search(query, use_rerank=False), 1):
        print(f"{i}. RRF {r['fused_score']:.4f} | dense #{r['dense_rank']} | bm25 #{r['bm25_rank']}")
        print(f"   {r['text'][:140]}...\n")

    print("=" * 60)
    print("WITH re-ranking (hybrid RRF -> cross-encoder)")
    print("=" * 60)
    for i, r in enumerate(search(query, use_rerank=True), 1):
        print(f"{i}. Rerank {r['rerank_score']} | dense #{r['dense_rank']} | bm25 #{r['bm25_rank']}")
        print(f"   {r['text'][:140]}...\n")