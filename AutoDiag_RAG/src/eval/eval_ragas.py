"""
Step 4c — RAGAS-style answer-quality evaluation (LLM-as-judge) on the saved pipeline answers.

Reads data/eval/pipeline_runs.jsonl (from eval_pipeline.py) — nothing is re-generated — and scores
every answered in-scope question with the four RAGAS metrics (Es et al., 2023, "RAGAS: Automated
Evaluation of Retrieval Augmented Generation"), following the RAGAS definitions:

  faithfulness       claims in the answer supported by the retrieved contexts / all claims in the answer
  answer_relevancy   mean cosine similarity between the user question and questions the judge
                     re-generates from the answer (0 if the answer is evasive / non-committal)
  context_precision  average precision of the retrieved contexts, judged useful against the reference
                     answer, so useful contexts ranked higher score more
  context_recall     statements in the reference answer attributable to the contexts / all statements

Judge LLM : Groq (free tier) — EVAL_JUDGE_MODEL in .env, default openai/gpt-oss-120b
Embeddings: Gemini embedding API (free tier) for answer_relevancy; if it is unavailable the judge's
            direct 0-1 relevance rating is used instead and the method is recorded per question.

One judge call per question (all four judgements in one JSON reply) keeps it inside Groq's free limits.
Scores are saved after every question, so the script can be re-run to resume.

Warranty questions: the generator also receives the deterministic rules-check verdict (coverage limits,
vehicle age/mileage). That verdict is passed to the judge as a separate RULES CHECK block so claims taken
from it count as grounded for faithfulness. Context precision/recall still judge ONLY the retrieved chunks.

Run from the project root:
    python src/eval/eval_ragas.py                      # score everything not yet scored
    python src/eval/eval_ragas.py --redo-warranty      # re-score the warranty questions (rules check included)
    python src/eval/eval_ragas.py --fix-relevancy      # recompute judge-rated answer relevancy with embeddings
                                                       # (re-uses saved judge output, no new Groq calls)
"""
import os
import re
import sys
import json
import math
import time
import statistics
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "src" / "pipeline"))
from warranty_tool import check_warranty  # deterministic, so the verdict can be recomputed exactly

RUNS_FILE = Path("data/eval/pipeline_runs.jsonl")
GOLD_FILE = Path("data/gold/gold_set.jsonl")
OUT_DIR = Path("data/eval")
SCORES_FILE = OUT_DIR / "ragas_scores.jsonl"
SUMMARY_FILE = OUT_DIR / "ragas_summary.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "openai/gpt-oss-120b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")

MAX_CONTEXT_CHARS = 1200   # per retrieved chunk sent to the judge (keeps each call small)
PAUSE_SECONDS = 3          # gap between questions (Groq free-tier rate limits)
TYPES = ["dtc_exact", "dtc_paraphrase", "symptom", "warranty"]
METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]

JUDGE_PROMPT = """You are a strict evaluator of a retrieval-augmented question-answering system for automotive diagnosis and warranty questions.

QUESTION:
{question}

RETRIEVED CONTEXTS (numbered, in ranked order):
{contexts}
{rules_block}
SYSTEM ANSWER:
{answer}

REFERENCE ANSWER (ground truth):
{reference}

Do ALL of the following and reply with ONE JSON object only, no other text:

1. "claims": break the SYSTEM ANSWER into its individual factual claims (ignore citations like "Source 2" and
   ignore pure advice such as "consult a mechanic"). For each claim set "supported" to true only if the
   RETRIEVED CONTEXTS (or the RULES CHECK, if one is given above) directly support it.
2. "context_useful": judging ONLY the retrieved contexts (not the rules check), a list of exactly {n_ctx} booleans, one per retrieved context in order: true if that context
   is useful for arriving at the REFERENCE ANSWER, false otherwise.
3. "reference_statements": break the REFERENCE ANSWER into individual statements. For each set "attributed" to
   true only if it can be attributed to (is supported by) the RETRIEVED CONTEXTS (not the rules check).
4. "generated_questions": write 3 different questions that the SYSTEM ANSWER would be a good answer to.
5. "noncommittal": true if the SYSTEM ANSWER is evasive or says it cannot answer, else false.
6. "relevance_score": a number from 0 to 1 for how directly the SYSTEM ANSWER addresses the QUESTION.

JSON format:
{{"claims": [{{"claim": "...", "supported": true}}],
  "context_useful": [true, false],
  "reference_statements": [{{"statement": "...", "attributed": true}}],
  "generated_questions": ["...", "...", "..."],
  "noncommittal": false,
  "relevance_score": 0.9}}"""


# ---------------------------------------------------------------- LLM judge
def call_judge(prompt: str) -> dict:
    payload = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    if "gpt-oss" in JUDGE_MODEL:
        payload["reasoning_effort"] = "low"  # keep the hidden reasoning short so the JSON is not cut off

    for attempt in range(1, 6):
        r = requests.post(GROQ_CHAT_URL, json=payload, verify=False, timeout=120,
                          headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"})
        if r.status_code == 429:
            wait = float(r.headers.get("retry-after", 20))
            print(f"    [Judge] Groq rate limit — waiting {wait:.0f}s (attempt {attempt}/5)")
            time.sleep(wait + 1)
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Groq judge failed ({r.status_code}): {r.text[:200]}")
        content = r.json()["choices"][0]["message"]["content"] or ""
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S)
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            raise RuntimeError(f"Judge did not return JSON: {content[:200]}")
        return json.loads(match.group(0))
    raise RuntimeError("Groq judge still rate-limited after 5 attempts")


# ---------------------------------------------------------------- embeddings (answer relevancy)
_embed_client = None


def embed(texts: list) -> list:
    """Gemini embeddings (free tier). Raises if unavailable — caller falls back to the judge rating."""
    global _embed_client
    if _embed_client is None:
        from google import genai
        _embed_client = genai.Client(api_key=GEMINI_API_KEY)
    for attempt in range(1, 4):
        try:
            result = _embed_client.models.embed_content(model=GEMINI_EMBED_MODEL, contents=texts)
            return [e.values for e in result.embeddings]
        except Exception as e:
            if attempt == 3:
                raise
            print(f"    [Embeddings] {type(e).__name__} — waiting 30s before retry ({attempt}/3)")
            time.sleep(30)


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ---------------------------------------------------------------- metric maths (RAGAS definitions)
def faithfulness(j: dict):
    claims = j.get("claims") or []
    return sum(bool(c.get("supported")) for c in claims) / len(claims) if claims else None


def context_precision(j: dict, n_ctx: int):
    verdicts = [bool(v) for v in (j.get("context_useful") or [])][:n_ctx]
    relevant = sum(verdicts)
    if relevant == 0:
        return 0.0
    hits, total = 0, 0.0
    for k, useful in enumerate(verdicts, 1):
        if useful:
            hits += 1
            total += hits / k  # precision@k at each useful position
    return total / relevant


def context_recall(j: dict):
    statements = j.get("reference_statements") or []
    return sum(bool(s.get("attributed")) for s in statements) / len(statements) if statements else None


def answer_relevancy(j: dict, question: str):
    if j.get("noncommittal"):
        return 0.0, "noncommittal"
    generated = [q for q in (j.get("generated_questions") or []) if isinstance(q, str) and q.strip()]
    if generated:
        try:
            vectors = embed([question] + generated)
            return statistics.mean(cosine(vectors[0], v) for v in vectors[1:]), "embedding"
        except Exception as e:
            print(f"    [Embeddings] unavailable ({type(e).__name__}) — using judge relevance rating")
    score = j.get("relevance_score")
    return (float(score), "judge_rating") if isinstance(score, (int, float)) else (None, "missing")


# ---------------------------------------------------------------- rules check (warranty questions)
def rules_block_for(run: dict, gold_by_id: dict) -> str:
    if run["type"] != "warranty":
        return ""
    details = (gold_by_id.get(run["id"]) or {}).get("warranty_details")
    if not details:
        return ""
    v = check_warranty(details["manufacturer"], details["component"],
                       details["vehicle_age_years"], details["mileage"])
    return ("\nRULES CHECK (deterministic warranty-rules engine result that was also given to the system; "
            "it counts as supporting evidence for claims):\n"
            f"Vehicle: {details['manufacturer']}, component {details['component']}, "
            f"{details['vehicle_age_years']} years old, {details['mileage']:,} miles.\n"
            f"Verdict: {v['status'].upper()}. Reason: {v['reason']}\n")


def fix_relevancy(scored: dict) -> int:
    """Recompute judge-rated answer relevancy with embeddings, re-using the saved judge output."""
    fixed = 0
    for r in scored.values():
        if r.get("answer_relevancy_method") != "judge_rating":
            continue
        generated = [q for q in (r["judge"].get("generated_questions") or []) if isinstance(q, str) and q.strip()]
        if not generated:
            continue
        try:
            vectors = embed([r["query"]] + generated)
        except Exception as e:
            print(f"  {r['id']}: embeddings still unavailable ({type(e).__name__}) — kept judge rating")
            continue
        old = r["answer_relevancy"]
        r["answer_relevancy"] = statistics.mean(cosine(vectors[0], v) for v in vectors[1:])
        r["answer_relevancy_method"] = "embedding"
        fixed += 1
        print(f"  {r['id']}: answer relevancy {old:.2f} (judge rating) -> {r['answer_relevancy']:.2f} (embedding)")
    return fixed


# ---------------------------------------------------------------- main
def load_scored():
    if not SCORES_FILE.exists():
        return {}
    return {r["id"]: r for r in map(json.loads, open(SCORES_FILE, encoding="utf-8")) if not r.get("error")}


def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 3) if values else None


def main():
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY is not set in .env")
    runs = [json.loads(line) for line in open(RUNS_FILE, encoding="utf-8")]
    runs = [r for r in runs if not r.get("error") and r["type"] != "out_of_scope" and not r.get("deferred")]
    gold_by_id = {g["id"]: g for g in map(json.loads, open(GOLD_FILE, encoding="utf-8"))}
    scored = load_scored()
    if "--redo-warranty" in sys.argv:
        scored = {k: v for k, v in scored.items() if v["type"] != "warranty"}
        print("Re-scoring warranty questions with the rules check included.")
    if "--fix-relevancy" in sys.argv:
        print("Recomputing judge-rated answer relevancy with embeddings:")
        print(f"  fixed {fix_relevancy(scored)} question(s)\n")
    todo = [r for r in runs if r["id"] not in scored]
    print(f"Answered in-scope questions: {len(runs)} | already scored: {len(scored)} | to score: {len(todo)}")
    print(f"Judge: {JUDGE_MODEL} (Groq) | embeddings: {GEMINI_EMBED_MODEL} (Gemini)\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        for r in scored.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    for n, r in enumerate(todo, 1):
        contexts = r["contexts"]
        ctx_block = "\n\n".join(f"[{i}] {c[:MAX_CONTEXT_CHARS]}" for i, c in enumerate(contexts, 1))
        prompt = JUDGE_PROMPT.format(question=r["query"], contexts=ctx_block, answer=r["answer"],
                                     reference=r["reference_answer"], n_ctx=len(contexts),
                                     rules_block=rules_block_for(r, gold_by_id))
        record = {"id": r["id"], "type": r["type"], "query": r["query"],
                  "generator_model": r.get("generator_model")}
        try:
            j = call_judge(prompt)
            relevancy, method = answer_relevancy(j, r["query"])
            record.update({
                "faithfulness": faithfulness(j),
                "answer_relevancy": relevancy,
                "answer_relevancy_method": method,
                "context_precision": context_precision(j, len(contexts)),
                "context_recall": context_recall(j),
                "judge": j,
            })
            fmt = lambda v: f"{v:.2f}" if v is not None else " n/a"
            print(f"[{n:2d}/{len(todo)}] {r['id']}  faith {fmt(record['faithfulness'])}  "
                  f"relev {fmt(record['answer_relevancy'])} ({method})  "
                  f"c.prec {fmt(record['context_precision'])}  c.rec {fmt(record['context_recall'])}")
        except Exception as e:
            record["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            print(f"[{n:2d}/{len(todo)}] {r['id']}  ERROR {record['error'][:120]}")
        with open(SCORES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        time.sleep(PAUSE_SECONDS)

    # ---------------------------------------------------------------- summary
    rows = [json.loads(line) for line in open(SCORES_FILE, encoding="utf-8")]
    ok = [r for r in rows if not r.get("error")]
    errors = [r for r in rows if r.get("error")]
    summary = {
        "judge_model": JUDGE_MODEL,
        "questions_scored": len(ok),
        "errors": len(errors),
        "answer_relevancy_methods": {m: sum(r["answer_relevancy_method"] == m for r in ok)
                                     for m in sorted({r["answer_relevancy_method"] for r in ok})},
        "overall": {m: mean(r[m] for r in ok) for m in METRICS},
        "by_type": {t: {m: mean(r[m] for r in ok if r["type"] == t) for m in METRICS} for t in TYPES},
        "n_by_type": {t: sum(r["type"] == t for r in ok) for t in TYPES},
    }
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 84)
    print(f"RAGAS METRICS  ({len(ok)} answered questions, judge: {JUDGE_MODEL})")
    print("=" * 84)
    print(f"{'':22s}" + "".join(f"{m:>18s}" for m in METRICS))
    o = summary["overall"]
    print(f"{'OVERALL':22s}" + "".join(f"{(o[m] if o[m] is not None else float('nan')):>18.3f}" for m in METRICS))
    for t in TYPES:
        b = summary["by_type"][t]
        label = f"{t} ({summary['n_by_type'][t]})"
        print(f"{label:22s}" + "".join(f"{(b[m] if b[m] is not None else float('nan')):>18.3f}" for m in METRICS))
    print(f"\nAnswer relevancy method: {summary['answer_relevancy_methods']}")
    if errors:
        print(f"\n{len(errors)} questions failed — run the script again to retry only those.")
    print(f"\nSaved: {SCORES_FILE} and {SUMMARY_FILE}")


if __name__ == "__main__":
    main()