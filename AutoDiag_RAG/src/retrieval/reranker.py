"""
Cross-encoder re-ranking via OpenRouter's rerank API (Cohere Rerank 3.5 by default).

A cross-encoder reads the query and each candidate chunk *together* and scores how well
the chunk answers the query — more precise than comparing two separately computed vectors,
so it is used as a second stage on the fused top-20 only.

If the API is unreachable or fails, the original fused order is kept (graceful fallback).
"""
import os
import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
RERANK_URL = "https://openrouter.ai/api/v1/rerank"
RERANK_MODEL = os.getenv("RERANK_MODEL", "cohere/rerank-v3.5")
MAX_DOC_CHARS = 3000  # model context is ~4K tokens for query + document; keep documents well inside it


def rerank(query: str, candidates: list, top_n: int = 5) -> list:
    """
    candidates: list of dicts that each have a "text" key (e.g. results of hybrid_search_detailed).
    Returns the best `top_n` candidates, re-ordered, each with an added "rerank_score" (0-1).
    """
    if not candidates:
        return []
    try:
        r = requests.post(
            RERANK_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": RERANK_MODEL,
                "query": query,
                "documents": [c["text"][:MAX_DOC_CHARS] for c in candidates],
                "top_n": min(top_n, len(candidates)),
            },
            verify=False,  # same corporate-network workaround as embeddings.py
            timeout=30,
        )
        r.raise_for_status()
        reranked = []
        for item in r.json()["results"]:  # already sorted by relevance, best first
            c = dict(candidates[item["index"]])
            c["rerank_score"] = float(item["relevance_score"])
            reranked.append(c)
        return reranked
    except Exception as e:
        print(f"[Reranker] Unavailable, keeping fused order: {type(e).__name__}: {str(e)[:150]}")
        return [dict(c, rerank_score=None) for c in candidates[:top_n]]


if __name__ == "__main__":
    docs = [
        {"text": "The front seat rattles when driving over bumps."},
        {"text": "Loud rattling noise from the engine that increases when accelerating, with loss of power."},
        {"text": "DTC P0420: Catalyst system efficiency below threshold (Bank 1)."},
    ]
    for c in rerank("car makes a rattling noise when accelerating", docs, top_n=3):
        print(f"{c['rerank_score']}  |  {c['text']}")