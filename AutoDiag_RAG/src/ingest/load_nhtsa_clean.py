import pandas as pd
import json
import re
import ast
from pathlib import Path

INPUT_FILE = Path("data/raw/nhtsa/nhtsa_complaints.csv")
OUTPUT_DIR = Path("data/processed")
OUTPUT_FILE = OUTPUT_DIR / "nhtsa_chunks.jsonl"

MIN_WORDS = 15  # complaints shorter than this are usually junk/uninformative

def clean_text(text):
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def extract_product_info(products_str):
    """The 'products' column is a stringified list of dicts, e.g.
    "[{'type': 'Vehicle', 'productYear': '2020', 'productMake': 'HONDA', 'productModel': 'CIVIC', ...}]"
    """
    try:
        products = ast.literal_eval(products_str)
        if isinstance(products, list) and len(products) > 0:
            p = products[0]
            return {
                "make": str(p.get("productMake", "")).strip(),
                "model": str(p.get("productModel", "")).strip(),
                "year": str(p.get("productYear", "")).strip(),
            }
    except (ValueError, SyntaxError):
        pass
    return {"make": "", "model": "", "year": ""}

def main():
    print(f"Loading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Raw rows: {len(df)}")

    # Identify the summary/description column (name varies by API version)
    text_col = None
    for candidate in ["summary", "Summary", "description", "Description"]:
        if candidate in df.columns:
            text_col = candidate
            break
    if text_col is None:
        raise ValueError(f"Could not find a summary/description column. Columns are: {list(df.columns)}")

    df["clean_text"] = df[text_col].apply(clean_text)

    # Drop empty or too-short complaints
    df = df[df["clean_text"].str.split().str.len() >= MIN_WORDS]
    print(f"After length filter (>= {MIN_WORDS} words): {len(df)}")

    # Deduplicate identical complaint text
    before = len(df)
    df = df.drop_duplicates(subset="clean_text")
    print(f"After deduplication: {len(df)} (removed {before - len(df)})")

    # Build chunks
    chunks = []
    for _, row in df.iterrows():
        product_info = extract_product_info(row.get("products", "[]"))
        chunk = {
            "text": row["clean_text"],
            "metadata": {
                "source": "nhtsa",
                "doc_type": "diagnosis",
                "make": product_info["make"],
                "model": product_info["model"],
                "year": product_info["year"],
                "components": str(row.get("components", "")).strip(),
            }
        }
        chunks.append(chunk)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(chunks)} total NHTSA chunks to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()