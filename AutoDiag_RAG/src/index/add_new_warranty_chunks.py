import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import json
import uuid
import os
from embeddings import embed_text
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "autodiag_rag"
WARRANTY_FILE = Path("data/processed/warranty_chunks.jsonl")
NEW_MANUFACTURERS = {"Ford", "Nissan", "Kia"}

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def load_new_chunks():
    chunks = []
    with open(WARRANTY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            chunk = json.loads(line)
            if chunk["metadata"].get("manufacturer") in NEW_MANUFACTURERS:
                chunks.append(chunk)
    return chunks

def main():
    chunks = load_new_chunks()
    print(f"Found {len(chunks)} new chunks to embed and upload (Ford/Nissan/Kia)")

    points = []
    for i, chunk in enumerate(chunks):
        dense_vector = embed_text(chunk["text"])
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector={"dense": dense_vector},
            payload={"text": chunk["text"], **chunk["metadata"]},
        ))
        if (i + 1) % 20 == 0:
            print(f"Embedded {i + 1}/{len(chunks)}")

    print("Uploading to Qdrant...")
    client.upsert(collection_name=COLLECTION_NAME, points=points)

    info = client.get_collection(COLLECTION_NAME)
    print(f"\nDone. Collection now has {info.points_count} total points.")

if __name__ == "__main__":
    main()