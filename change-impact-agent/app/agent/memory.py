from __future__ import annotations

import sys
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from app.agent.schemas import ChangeRequest
from app.agent.state import AgentState, get_change_request
from app.db.base import Base, SessionLocal, engine
from app.rag.ingest import get_embedding_model

MAX_RECALL_DISTANCE = 0.35
_table_ready = False


class AnalysisMemory(Base):
    """Episodic memory: one row per analysis the agent has run."""

    __tablename__ = "analysis_memory"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    query: Mapped[str] = mapped_column(Text)
    package_name: Mapped[str] = mapped_column(String(200), index=True)
    action: Mapped[str] = mapped_column(String(20))
    target_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    projects: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String(10))
    signals: Mapped[list] = mapped_column(JSON, default=list)
    report: Mapped[str] = mapped_column(Text)
    dry_run_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dry_run_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(384))


def ensure_table() -> None:
    global _table_ready
    if not _table_ready:
        Base.metadata.create_all(engine, tables=[AnalysisMemory.__table__])
        _table_ready = True


def _memory_text(query: str, cr: ChangeRequest) -> str:
    return f"{query} | {cr.action} {cr.package_name} {cr.target_version or ''}"


def _embed(text: str) -> list[float]:
    return get_embedding_model().encode(text).tolist()


def _to_dict(m: AnalysisMemory, distance: float | None = None) -> dict:
    return {
        "id": m.id,
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
        "query": m.query,
        "package_name": m.package_name,
        "action": m.action,
        "target_version": m.target_version,
        "projects": m.projects or [],
        "risk_level": m.risk_level,
        "signals": m.signals or [],
        "report": m.report,
        "dry_run_status": m.dry_run_status,
        "dry_run_summary": m.dry_run_summary,
        "distance": distance,
    }


def save_analysis(state: AgentState) -> int:
    ensure_table()
    cr = get_change_request(state)
    record = AnalysisMemory(
        query=state["user_query"],
        package_name=cr.package_name.lower(),
        action=cr.action,
        target_version=cr.target_version,
        projects=list(state.get("affected_projects", [])),
        risk_level=state.get("risk_level", "low"),
        signals=list(state.get("signals", [])),
        report=state.get("report", ""),
        embedding=_embed(_memory_text(state["user_query"], cr)),
    )
    with SessionLocal() as session:
        session.add(record)
        session.commit()
        return record.id


def recall_similar(query: str, cr: ChangeRequest, limit: int = 3) -> list[dict]:
    ensure_table()
    vector = _embed(_memory_text(query, cr))
    distance = AnalysisMemory.embedding.cosine_distance(vector).label("distance")
    stmt = (
        select(AnalysisMemory, distance)
        .where(AnalysisMemory.package_name == cr.package_name.lower())
        .order_by(distance)
        .limit(limit)
    )
    with SessionLocal() as session:
        rows = session.execute(stmt).all()
        return [_to_dict(m, float(d)) for m, d in rows if d <= MAX_RECALL_DISTANCE]


def update_dry_run(memory_id: int, status: str, summary: str) -> None:
    ensure_table()
    with SessionLocal() as session:
        record = session.get(AnalysisMemory, memory_id)
        if record is not None:
            record.dry_run_status = status
            record.dry_run_summary = summary
            session.commit()


def list_recent(limit: int = 50) -> list[dict]:
    ensure_table()
    with SessionLocal() as session:
        rows = session.scalars(select(AnalysisMemory).order_by(AnalysisMemory.id.desc()).limit(limit)).all()
        return [_to_dict(m) for m in rows]


def delete_analysis(memory_id: int) -> None:
    ensure_table()
    with SessionLocal() as session:
        session.execute(delete(AnalysisMemory).where(AnalysisMemory.id == memory_id))
        session.commit()


# ---------- LangGraph nodes ----------

def recall_memory(state: AgentState) -> dict:
    """Look up similar past analyses of the same package."""
    try:
        return {"memories": recall_similar(state["user_query"], get_change_request(state))}
    except Exception as exc:
        print(f"Memory recall skipped: {exc}")
        return {"memories": []}


def save_memory(state: AgentState) -> dict:
    """Store this analysis so it can be recalled and audited later."""
    try:
        return {"memory_id": save_analysis(state)}
    except Exception as exc:
        print(f"Could not save analysis to memory: {exc}")
        return {"memory_id": None}


if __name__ == "__main__":
    # Self-test: create the table, save a test record, recall it with a reworded question, delete it.
    ensure_table()
    print("Table analysis_memory is ready.")
    cr = ChangeRequest(package_name="numpy", action="downgrade", target_version="1.24.3")
    test_state: AgentState = {
        "user_query": "Can I downgrade numpy to 1.24.3?", "change_request": cr,
        "affected_projects": ["AutoDiag_RAG"], "risk_level": "high",
        "signals": ["version_conflict"], "report": "(self-test record)",
    }
    new_id = save_analysis(test_state)
    print(f"Saved test record id={new_id}")
    update_dry_run(new_id, "conflict", "self-test")
    matches = recall_similar("Is it safe to move numpy back to version 1.24.3?", cr)
    for m in matches:
        print(f"Recalled id={m['id']} distance={m['distance']:.3f} risk={m['risk_level']} dry_run={m['dry_run_status']}")
    delete_analysis(new_id)
    print(f"Deleted test record. Records stored: {len(list_recent())}")
    if not any(m["id"] == new_id for m in matches):
        sys.exit("Recall did not find the test record - tell me this output.")
    print("Self-test passed: save, recall and delete all work.")