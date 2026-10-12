import os
import time
import requests
import urllib3
from google import genai
from google.genai import types
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# ------------------------------------------------------------------ LLM chain
# 1. Gemini direct (free tier)            -> primary
# 2. Groq (free tier, OpenAI-compatible)  -> first fallback, costs nothing
# 3. OpenRouter (paid credit)             -> last resort, only if a key + credit exist
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(timeout=30_000),  # 30 s per call (milliseconds)
)
MODEL_NAME = "gemini-3.6-flash"
GEMINI_ATTEMPTS = 2
RETRYABLE_CODES = {429, 500, 502, 503, 504}

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
FALLBACK_MODEL = os.getenv("OPENROUTER_FALLBACK_MODEL", "google/gemini-3.8-flash")
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

LAST_MODEL = None  # which model produced the most recent answer (read by the evaluation scripts)


def build_diagnosis_prompt(query: str, retrieved_chunks: list) -> str:
    context = "\n\n".join(
        f"[Source {i+1} | {c['metadata'].get('source', 'unknown')}]\n{c['text']}"
        for i, c in enumerate(retrieved_chunks)
    )
    return f"""You are an automotive diagnostic assistant. Answer the user's question using ONLY the information in the sources below. If the sources don't contain enough information, say so clearly rather than guessing.

SOURCES:
{context}

USER QUESTION: {query}

Give a clear, grounded answer. Cite which source(s) you used (e.g., "Source 2 mentions...")."""


def build_warranty_prompt(query: str, retrieved_chunks: list, warranty_verdict: dict) -> str:
    context = "\n\n".join(
        f"[Source {i+1} | {c['metadata'].get('source', 'unknown')}]\n{c['text']}"
        for i, c in enumerate(retrieved_chunks)
    )
    return f"""You are a warranty coverage assistant. A deterministic rules check has already been performed — treat its verdict as authoritative for coverage status, and use the sources below only for additional explanatory context.

RULES CHECK RESULT: {warranty_verdict['status'].upper()}
REASON: {warranty_verdict['reason']}

SOURCES (for context/explanation only):
{context}

USER QUESTION: {query}

Give a clear answer that states the coverage verdict plainly, then briefly explains why using the rules check reason and any relevant source context."""


def _gemini(prompt: str) -> str:
    for attempt in range(1, GEMINI_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            return response.text or ""
        except Exception as e:
            code = getattr(e, "code", None)
            if code not in RETRYABLE_CODES or attempt == GEMINI_ATTEMPTS:
                raise
            print(f"[Generator] Gemini returned {code} (attempt {attempt}/{GEMINI_ATTEMPTS}) — retrying in 2s")
            time.sleep(2)
    raise RuntimeError("Gemini call failed")


def _openai_compatible(url: str, api_key: str, model: str, prompt: str, name: str) -> str:
    """Groq and OpenRouter both speak the OpenAI chat-completions format."""
    r = requests.post(
        url,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.2, "max_tokens": 1024},
        verify=False,  # same corporate-network workaround as embeddings.py
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{name} failed ({r.status_code}): {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"] or ""


def generate_answer(prompt: str) -> str:
    """Gemini first; if it is overloaded or rate-limited, try Groq (free), then OpenRouter (paid)."""
    global LAST_MODEL
    try:
        answer = _gemini(prompt)
        LAST_MODEL = MODEL_NAME
        return answer
    except Exception as e:
        code = getattr(e, "code", None)
        if code not in RETRYABLE_CODES:
            raise
        first_error = f"Gemini {code}"

    fallbacks = []
    if GROQ_API_KEY:
        fallbacks.append(("Groq", GROQ_CHAT_URL, GROQ_API_KEY, GROQ_CHAT_MODEL))
    if OPENROUTER_API_KEY:
        fallbacks.append(("OpenRouter", OPENROUTER_CHAT_URL, OPENROUTER_API_KEY, FALLBACK_MODEL))

    errors = [first_error]
    for name, url, key, model in fallbacks:
        print(f"[Generator] {errors[-1]} — using fallback {name} ({model})")
        try:
            answer = _openai_compatible(url, key, model, prompt, name)
            LAST_MODEL = f"{name.lower()}:{model}"
            return answer
        except Exception as e:
            errors.append(str(e)[:150])
    raise RuntimeError("All LLMs failed: " + " | ".join(errors))


if __name__ == "__main__":
    fake_chunks = [
        {"text": "DTC P0301 indicates a misfire in cylinder 1. Common causes include worn spark plugs, faulty ignition coils, or low fuel pressure.", "metadata": {"source": "dtc"}},
    ]
    prompt = build_diagnosis_prompt("What does code P0301 mean?", fake_chunks)

    print("=== Normal chain (Gemini first) ===")
    print(generate_answer(prompt))
    print(f"\nAnswered by: {LAST_MODEL}")

    print("\n=== Groq fallback test (direct call) ===")
    if GROQ_API_KEY:
        print(_openai_compatible(GROQ_CHAT_URL, GROQ_API_KEY, GROQ_CHAT_MODEL, prompt, "Groq"))
    else:
        print("GROQ_API_KEY not set in .env")