from __future__ import annotations

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import EvidenceChunk, EvidenceDocument
from app.rag.ingest import get_embedding_model


def retrieve_evidence(
    query: str,
    package_name: str | None = None,
    version: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    model = get_embedding_model()
    query_vector = model.encode(query).tolist()

    session = SessionLocal()
    try:
        stmt = (
            select(
                EvidenceChunk.text,
                EvidenceChunk.chunk_index,
                EvidenceDocument.package_name,
                EvidenceDocument.version,
                EvidenceDocument.url,
                EvidenceChunk.embedding.cosine_distance(query_vector).label("distance"),
            )
            .join(EvidenceDocument, EvidenceChunk.document_id == EvidenceDocument.id)
        )
        if package_name:
            stmt = stmt.where(EvidenceDocument.package_name == package_name)
        if version:
            stmt = stmt.where(EvidenceDocument.version == version)

        stmt = stmt.order_by("distance").limit(top_k)

        rows = session.execute(stmt).all()
        return [
            {
                "text": r.text,
                "chunk_index": r.chunk_index,
                "package_name": r.package_name,
                "version": r.version,
                "url": r.url,
                "distance": float(r.distance),
            }
            for r in rows
        ]
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "does this package support Python 3.13"
    results = retrieve_evidence(query, top_k=3)

    print(f"Query: {query}\n")
    for r in results:
        print(f"[{r['package_name']} {r['version']}]  distance={r['distance']:.4f}")
        print(f"  {r['text'][:200]}...")
        print()