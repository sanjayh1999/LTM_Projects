import os, time, requests, urllib3
from dotenv import load_dotenv
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL").rstrip("/")
checks = {
    "Qdrant (port 6333)": (QDRANT_URL, {"api-key": os.getenv("QDRANT_API_KEY")}),
    "OpenRouter": ("https://openrouter.ai/api/v1/models", {}),
    "Gemini": ("https://generativelanguage.googleapis.com/", {}),
}
for name, (url, headers) in checks.items():
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=15, verify=False)
            print(f"{name}: OK (HTTP {r.status_code})")
            break
        except Exception as e:
            print(f"{name}: attempt {attempt + 1} FAILED - {type(e).__name__}")
            time.sleep(2)