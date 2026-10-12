import re

WARRANTY_KEYWORDS = [
    "warranty", "covered", "coverage", "cover", "claim",
    "mileage limit", "expire", "expiration", "still under",
    "out of warranty", "repair cost", "free repair", "reimburse",
]

DIAGNOSIS_KEYWORDS = [
    "code", "dtc", "check engine", "noise", "symptom",
    "won't start", "not starting", "leak", "smell", "vibration",
    "stall", "misfire", "rattling", "grinding", "squeak",
]

DTC_CODE_PATTERN = re.compile(r"\b[PBCU]\d{4}\b", re.IGNORECASE)


def classify_query(query_text: str) -> str:
    """
    Returns 'warranty' or 'diagnosis'.
    Rule-based query routing (not an autonomous agent): checks for a DTC
    code pattern first, then keyword overlap, defaulting to diagnosis.
    """
    text_lower = query_text.lower()

    if DTC_CODE_PATTERN.search(query_text):
        return "diagnosis"

    warranty_score = sum(1 for kw in WARRANTY_KEYWORDS if kw in text_lower)
    diagnosis_score = sum(1 for kw in DIAGNOSIS_KEYWORDS if kw in text_lower)

    if warranty_score > diagnosis_score:
        return "warranty"
    return "diagnosis"


if __name__ == "__main__":
    test_queries = [
        "My car is making a rattling noise when accelerating",
        "Is a transmission repair covered under warranty at 45000 miles?",
        "What does code P0301 mean?",
        "My Honda is 3 years old, is the engine still covered?",
        "Check engine light came on, smells like gas",
    ]

    for q in test_queries:
        result = classify_query(q)
        print(f"[{result:>9}] {q}")