import os
import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
EMBEDDING_MODEL = "baai/bge-m3"

def embed_text(text):
    """Embed a single query string. Returns a 1024-dim dense vector (list of floats)."""
    response = requests.post(
        EMBEDDING_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        },
        json={"model": EMBEDDING_MODEL, "input": text},
        verify=False,
    )
    response.raise_for_status()
    result = response.json()
    return result["data"][0]["embedding"]