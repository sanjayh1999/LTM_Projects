import yaml
import json
import os
from pathlib import Path

RAW_DIR = Path("data/raw/dtc")
OUTPUT_DIR = Path("data/processed")
OUTPUT_FILE = OUTPUT_DIR / "dtc_chunks.jsonl"

def load_yaml_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def build_chunk_text(entry):
    """Turn one DTC entry into a readable text chunk for embedding."""
    code = entry.get("code", "UNKNOWN")
    title = entry.get("title", {}).get("en", "")
    description = entry.get("description", {}).get("en", "")

    causes = entry.get("common_causes", []) or []
    cause_lines = [c.get("label", {}).get("en", "") for c in causes if c.get("label")]

    symptoms = entry.get("symptoms", []) or []
    symptom_lines = [s.get("en", "") for s in symptoms if isinstance(s, dict)]

    repair = entry.get("repair", {}) or {}
    difficulty = repair.get("difficulty", "unknown")

    text = f"DTC Code: {code}\nTitle: {title}\nDescription: {description}\n"
    if symptom_lines:
        text += f"Symptoms: {', '.join(symptom_lines)}\n"
    if cause_lines:
        text += f"Common Causes: {', '.join(cause_lines)}\n"
    text += f"Repair Difficulty: {difficulty}\n"

    return text.strip()

def process_file(filepath):
    data = load_yaml_file(filepath)
    chunks = []

    # data is usually a list of entries, or a dict with a key holding the list
    entries = data if isinstance(data, list) else data.get("codes", data)

    for entry in entries:
        if not isinstance(entry, dict) or "code" not in entry:
            continue
        chunk = {
            "text": build_chunk_text(entry),
            "metadata": {
                "source": "obdex",
                "doc_type": "diagnosis",
                "dtc_code": entry.get("code"),
                "category": entry.get("category", ""),
            }
        }
        chunks.append(chunk)

    return chunks

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks = []

    yaml_files = list(RAW_DIR.glob("*.yaml")) + list(RAW_DIR.glob("*.yml"))
    print(f"Found {len(yaml_files)} YAML files in {RAW_DIR}")

    for filepath in yaml_files:
        print(f"Processing {filepath.name}...")
        chunks = process_file(filepath)
        print(f"  -> {len(chunks)} chunks")
        all_chunks.extend(chunks)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(all_chunks)} total DTC chunks to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()