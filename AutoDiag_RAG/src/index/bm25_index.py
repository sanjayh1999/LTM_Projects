import json
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi
import re

PROCESSED_DIR = Path("data/processed")
INDEX_DIR = Path("data/processed/bm25_index")

FILES = [
    PROCESSED_DIR / "dtc_chunks.jsonl",
    PROCESSED_DIR / "warranty_chunks.jsonl",
    PROCESSED_DIR / "nhtsa_chunks.jsonl",
]

def simple_tokenize(text):
    """Lowercase + split on non-alphanumeric. Keeps codes like P0301 intact."""
    text = text.lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return tokens

def load_all_chunks():
    chunks = []
    for filepath in FILES:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                chunks.append(json.loads(line))
    return chunks

def main():
    print("Loading all chunks...")
    chunks = load_all_chunks()
    print(f"Total chunks: {len(chunks)}")

    print("Tokenizing (this may take a minute for 59K chunks)...")
    tokenized_corpus = [simple_tokenize(chunk["text"]) for chunk in chunks]

    print("Building BM25 index...")
    bm25 = BM25Okapi(tokenized_corpus)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    with open(INDEX_DIR / "bm25.pkl", "wb") as f:
        pickle.dump(bm25, f)

    with open(INDEX_DIR / "chunks.pkl", "wb") as f:
        pickle.dump(chunks, f)

    print(f"\nSaved BM25 index and chunks to {INDEX_DIR}")
    print(f"Index covers {len(chunks)} chunks.")

if __name__ == "__main__":
    main()