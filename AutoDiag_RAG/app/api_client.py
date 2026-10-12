"""Thin HTTP client for the AutoDiag-RAG FastAPI backend."""
import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


class ApiError(Exception):
    pass


def _handle(resp):
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ApiError(f"{resp.status_code}: {detail}")
    return resp.json()


def is_online() -> bool:
    try:
        return requests.get(f"{API_BASE}/health", timeout=3).status_code == 200
    except requests.RequestException:
        return False


def ask(query, warranty_details=None, route_override=None):
    payload = {"query": query}
    if warranty_details:
        payload["warranty_details"] = warranty_details
    if route_override:
        payload["route_override"] = route_override
    try:
        return _handle(requests.post(f"{API_BASE}/query", json=payload, timeout=120))
    except requests.RequestException as e:
        raise ApiError(f"Could not reach the API at {API_BASE} ({e.__class__.__name__}). Is uvicorn running?")


def transcribe(audio_bytes: bytes) -> str:
    try:
        resp = requests.post(f"{API_BASE}/transcribe", data=audio_bytes,
                             headers={"Content-Type": "audio/wav"}, timeout=60)
    except requests.RequestException as e:
        raise ApiError(f"Could not reach the API ({e.__class__.__name__}).")
    return _handle(resp)["text"]


def warranty_check(manufacturer, component, age_years, mileage):
    payload = {"manufacturer": manufacturer, "component": component,
               "vehicle_age_years": age_years, "mileage": int(mileage)}
    try:
        return _handle(requests.post(f"{API_BASE}/warranty/check", json=payload, timeout=15))
    except requests.RequestException as e:
        raise ApiError(f"Could not reach the API ({e.__class__.__name__}).")


def send_feedback(query, answer, route, rating, comment=None):
    try:
        requests.post(f"{API_BASE}/feedback", timeout=10,
                      json={"query": query, "answer": answer, "route": route,
                            "rating": rating, "comment": comment})
    except requests.RequestException:
        pass


@st.cache_data(ttl=300, show_spinner=False)
def warranty_options() -> dict:
    try:
        return _handle(requests.get(f"{API_BASE}/warranty/options", timeout=10))
    except (requests.RequestException, ApiError):
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def corpus_stats() -> dict:
    try:
        return _handle(requests.get(f"{API_BASE}/stats", timeout=30))
    except (requests.RequestException, ApiError):
        return {}