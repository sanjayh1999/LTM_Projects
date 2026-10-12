from __future__ import annotations

import json
import time
import warnings
from pathlib import Path
from typing import Iterator, Optional

# Silence a harmless deprecation notice raised inside LangGraph's own imports
warnings.filterwarnings("ignore", message=".*allowed_objects")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.agent.deps import analyze_project_usage  # noqa: E402
from app.agent.dryrun import dry_run  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.agent.memory import list_recent, update_dry_run  # noqa: E402
from app.agent.tools import locate_package  # noqa: E402
from app.ui.data import (  # noqa: E402
    check_database,
    check_llm,
    packages_for_project,
    project_summary,
    shared_packages,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

STEP_LABELS = {
    "parse_change": "Understood the question",
    "recall_memory": "Checked memory for similar past changes",
    "investigate": "Inspected environments, dependencies, compatibility and PyPI",
    "assess_risk": "Scored the risk",
    "write_report": "Wrote the explanation",
    "noop_report": "Nothing to change, skipped the LLM",
    "save_memory": "Saved the analysis to memory",
}

DRY_RUN_SEVERITY = ["conflict", "would_break", "not_found", "unsupported", "error", "skipped", "ok"]

app = FastAPI(title="Change Impact Agent")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class AnalyzeRequest(BaseModel):
    query: str


class DryRunRequest(BaseModel):
    package: str
    action: str
    target_version: Optional[str] = None
    projects: list[str]
    memory_id: Optional[int] = None


def _line(obj: dict) -> str:
    return json.dumps(obj, default=str) + "\n"


def _serialize(query: str, state: dict, steps: list[dict], duration: float) -> dict:
    change_request = state.get("change_request")
    if change_request is None or state.get("risk_level") is None:
        raise ValueError("The agent did not finish its analysis.")
    return {
        "query": query,
        "change_request": change_request.model_dump(),
        "risk_level": state["risk_level"],
        "risk_reasons": state.get("risk_reasons", []),
        "signals": state.get("signals", []),
        "is_noop": bool(state.get("is_noop")),
        "affected_projects": state.get("affected_projects", []),
        "scope_note": state.get("scope_note", ""),
        "narrative": state.get("report", ""),
        "memory_id": state.get("memory_id"),
        "memories": state.get("memories", []),
        "findings": [f.model_dump() for f in state.get("findings", [])],
        "project_checks": state.get("project_checks", []),
        "locations": locate_package(change_request.package_name),
        "steps": steps,
        "duration": round(duration, 1),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    db_ok, db_msg = check_database()
    llm_ok, llm_msg = check_llm()
    return {"database": {"ok": db_ok, "message": db_msg}, "llm": {"ok": llm_ok, "message": llm_msg}}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> StreamingResponse:
    """Run the LangGraph agent and stream one JSON line per completed node, then the result."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Type a question first.")

    def events() -> Iterator[str]:
        state: dict = {"user_query": query}
        steps: list[dict] = []
        started = step_started = time.perf_counter()
        try:
            for update in build_graph().stream({"user_query": query}, stream_mode="updates"):
                for node, delta in update.items():
                    if delta:
                        state.update(delta)
                    now = time.perf_counter()
                    step = {"node": node, "label": STEP_LABELS.get(node, node),
                            "seconds": round(now - step_started, 2)}
                    steps.append(step)
                    step_started = now
                    yield _line({"type": "step", **step})
            yield _line({"type": "result",
                         "data": _serialize(query, state, steps, time.perf_counter() - started)})
        except Exception as exc:
            yield _line({"type": "error", "message": str(exc)})

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post("/api/dryrun")
def run_dry_run(req: DryRunRequest) -> StreamingResponse:
    """Human-approved verification: pip's resolver in dry-run mode, streamed one project at a time."""

    def events() -> Iterator[str]:
        locations = {loc["project_name"]: loc for loc in locate_package(req.package)}
        results: list[dict] = []
        for project in req.projects:
            loc = locations.get(project)
            if not loc:
                continue
            yield _line({"type": "progress", "project": project})
            try:
                usage = analyze_project_usage(req.package, project, loc["project_path"])
                result = dry_run(req.action, req.package, req.target_version, usage)
            except Exception as exc:
                result = {"project": project, "status": "error", "summary": str(exc),
                          "command": "", "details": [], "changes": []}
            results.append(result)
            yield _line({"type": "result", "data": result})

        statuses = [r["status"] for r in results if r["status"] in DRY_RUN_SEVERITY]
        overall = min(statuses, key=DRY_RUN_SEVERITY.index) if statuses else "error"
        if req.memory_id and results:
            try:
                update_dry_run(req.memory_id, overall,
                               "; ".join(f"{r['project']}: {r['status']}" for r in results))
            except Exception:
                pass
        yield _line({"type": "done", "overall": overall})

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.get("/api/inventory")
def inventory() -> dict:
    return {"projects": project_summary(), "shared": shared_packages()}


@app.get("/api/projects/{name}/packages")
def project_packages(name: str) -> list[dict]:
    return packages_for_project(name)


@app.get("/api/explore/{package}")
def explore(package: str) -> dict:
    """Where a package is installed and, per project, which installed packages need it."""
    rows = locate_package(package)
    projects = []
    for row in rows:
        usage = analyze_project_usage(package, row["project_name"], row["project_path"])
        projects.append({
            "project": row["project_name"],
            "path": row["project_path"],
            "version": row["version"],
            "requires_python": row["requires_python"],
            "error": usage.get("error"),
            "python_version": usage.get("python_version"),
            "is_direct": usage.get("is_direct"),
            "root_basis": usage.get("root_basis", ""),
            "required_by": usage.get("required_by", []),
            "dependent_count": usage.get("dependent_count", 0),
            "chains": usage.get("chains", [])[:3],
        })
    return {"package": package, "locations": rows, "projects": projects}


@app.get("/api/history")
def history() -> list[dict]:
    return list_recent(100)