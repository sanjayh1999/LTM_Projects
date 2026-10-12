from pypdf import PdfReader
import json
import re
from pathlib import Path

RAW_DIR = Path("data/raw/warranty")
OUTPUT_DIR = Path("data/processed")
OUTPUT_FILE = OUTPUT_DIR / "warranty_chunks.jsonl"

CHUNK_SIZE = 800      # characters per chunk (~150-200 words, good for warranty clauses)
CHUNK_OVERLAP = 150   # overlap so we don't cut a clause in half at a chunk boundary

# Map filenames to a clean manufacturer label
MANUFACTURER_MAP = {
    "2026_Honda_Warranty_Booklet.pdf": "Honda",
    "2026_owners_handbook_warranty.pdf": "Hyundai",
    "T-MMS-26GrandHighlanderHV.pdf": "Toyota",
    "26MY_US_Ford_WTY_V4.pdf": "Ford",
    "2026-nissan-warranty-booklet.pdf": "Nissan",
    "kia-warranty-manual.pdf": "Kia",
}

def guess_manufacturer(filename):
    return MANUFACTURER_MAP.get(filename, "Unknown")

def extract_text(filepath):
    reader = PdfReader(filepath)
    pages_text = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages_text.append((i + 1, text))  # 1-indexed page number
    return pages_text

def clean_text(text):
    # Collapse excessive whitespace/newlines from PDF extraction noise
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if len(chunk.strip()) > 50:  # skip tiny leftover fragments
            chunks.append(chunk.strip())
        start += chunk_size - overlap
    return chunks

def process_file(filepath):
    manufacturer = guess_manufacturer(filepath.name)
    pages_text = extract_text(filepath)

    all_chunks = []
    for page_num, raw_text in pages_text:
        cleaned = clean_text(raw_text)
        if not cleaned:
            continue
        for chunk in chunk_text(cleaned):
            all_chunks.append({
                "text": chunk,
                "metadata": {
                    "source": filepath.name,
                    "doc_type": "warranty",
                    "manufacturer": manufacturer,
                    "page": page_num,
                }
            })
    return all_chunks

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks = []

    pdf_files = list(RAW_DIR.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {RAW_DIR}")

    for filepath in pdf_files:
        print(f"Processing {filepath.name}...")
        chunks = process_file(filepath)
        print(f"  -> {len(chunks)} chunks")
        all_chunks.extend(chunks)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(all_chunks)} total warranty chunks to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()