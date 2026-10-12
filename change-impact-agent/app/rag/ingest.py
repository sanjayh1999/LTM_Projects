from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import EvidenceChunk, EvidenceDocument
from app.rag.pypi_client import fetch_package_metadata

CHUNK_SIZE_WORDS = 200
CHUNK_OVERLAP_WORDS = 30


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer("all-MiniLM-L6-v2")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks


def ingest_package_evidence(package_name: str, version: str | None = None) -> EvidenceDocument | None:
    meta = fetch_package_metadata(package_name, version)
    if meta is None:
        print(f"Could not fetch metadata for {package_name} {version or '(latest)'}")
        return None

    text_blob = f"{meta['name']} {meta['version']}\n"
    text_blob += f"Requires-Python: {meta['requires_python']}\n\n"
    text_blob += f"{meta['summary']}\n\n{meta['description']}"

    chunks = chunk_text(text_blob)
    if not chunks:
        print(f"No text to embed for {package_name}")
        return None

    model = get_embedding_model()
    vectors = model.encode(chunks, show_progress_bar=False)

    session = SessionLocal()
    try:
        document = session.execute(
            select(EvidenceDocument).where(
                EvidenceDocument.package_name == meta["name"],
                EvidenceDocument.version == meta["version"],
            )
        ).scalar_one_or_none()

        if document is None:
            document = EvidenceDocument(
                source="pypi", package_name=meta["name"], version=meta["version"], url=meta["project_url"]
            )
            session.add(document)
            session.flush()
        else:
            session.query(EvidenceChunk).filter(EvidenceChunk.document_id == document.id).delete()

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            session.add(EvidenceChunk(
                document_id=document.id, chunk_index=i, text=chunk, embedding=vector.tolist()
            ))

        session.commit()
        print(f"Ingested {meta['name']} {meta['version']}: {len(chunks)} chunk(s)")
        return document
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "numpy"
    version = sys.argv[2] if len(sys.argv) > 2 else None
    ingest_package_evidence(name, version)