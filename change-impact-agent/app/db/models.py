from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

EMBEDDING_DIM = 384  # sentence-transformers/all-MiniLM-L6-v2


# ---------- Inventory ----------

class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255))
    os: Mapped[str] = mapped_column(String(100))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    environments: Mapped[list["Environment"]] = relationship(back_populates="machine")
    projects: Mapped[list["Project"]] = relationship(back_populates="machine")


class Environment(Base):
    """A Python interpreter, virtualenv, or conda env found on the machine."""
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))       # "system" | "venv" | "conda"
    python_version: Mapped[str] = mapped_column(String(20))
    path: Mapped[str] = mapped_column(Text)

    machine: Mapped["Machine"] = relationship(back_populates="environments")
    packages: Mapped[list["Package"]] = relationship(back_populates="environment")


class Package(Base):
    """An installed package inside a specific environment."""
    __tablename__ = "packages"
    __table_args__ = (UniqueConstraint("environment_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id"))
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(100))
    requires_python: Mapped[str | None] = mapped_column(String(100), nullable=True)

    environment: Mapped["Environment"] = relationship(back_populates="packages")


class Project(Base):
    """A discovered project folder (has a manifest, maybe a git repo, maybe a Dockerfile)."""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"))
    name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(Text)

    machine: Mapped["Machine"] = relationship(back_populates="projects")
    manifests: Mapped[list["Manifest"]] = relationship(back_populates="project")
    git_repo: Mapped["GitRepo | None"] = relationship(back_populates="project", uselist=False)


class Manifest(Base):
    """requirements.txt / pyproject.toml / Dockerfile found inside a project."""
    __tablename__ = "manifests"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(30))        # "requirements_txt" | "pyproject_toml" | "dockerfile"
    path: Mapped[str] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="manifests")
    requirements: Mapped[list["Requirement"]] = relationship(back_populates="manifest")


class Requirement(Base):
    """A single declared dependency line, parsed out of a manifest."""
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    manifest_id: Mapped[int] = mapped_column(ForeignKey("manifests.id"))
    package_name: Mapped[str] = mapped_column(String(255))
    version_spec: Mapped[str | None] = mapped_column(String(255), nullable=True)   # e.g. ">=1.24,<2.0"
    extras: Mapped[str | None] = mapped_column(String(255), nullable=True)
    marker: Mapped[str | None] = mapped_column(Text, nullable=True)                # PEP 508 environment marker

    manifest: Mapped["Manifest"] = relationship(back_populates="requirements")


class GitRepo(Base):
    __tablename__ = "git_repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), unique=True)
    remote_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_commit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_commit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="git_repo")


# ---------- Dependency graph ----------

class GraphNode(Base):
    """A generic node — a package, a project, an interpreter, a Docker image."""
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("node_type", "external_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node_type: Mapped[str] = mapped_column(String(30))     # "package" | "project" | "interpreter" | "docker_image"
    external_key: Mapped[str] = mapped_column(String(500)) # e.g. "package:numpy:1.24.3"
    label: Mapped[str] = mapped_column(String(255))


class GraphEdge(Base):
    """A directed relationship between two nodes, e.g. project -> depends_on -> package."""
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"))
    relation: Mapped[str] = mapped_column(String(50))      # "depends_on" | "uses_interpreter" | "built_from"

    source: Mapped["GraphNode"] = relationship(foreign_keys=[source_id])
    target: Mapped["GraphNode"] = relationship(foreign_keys=[target_id])


# ---------- Evidence index (RAG) ----------

class EvidenceDocument(Base):
    __tablename__ = "evidence_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30))        # "pypi" | "github_release" | "changelog"
    package_name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunks: Mapped[list["EvidenceChunk"]] = relationship(back_populates="document")


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"))
    chunk_index: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    document: Mapped["EvidenceDocument"] = relationship(back_populates="chunks")


# ---------- Episodic memory ----------

class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_query: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(50))        # "upgrade" | "remove" | "install"
    target: Mapped[str] = mapped_column(String(255))
    from_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped["ImpactReport | None"] = relationship(back_populates="change_request", uselist=False)


class ImpactReport(Base):
    __tablename__ = "impact_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id"), unique=True)
    risk_level: Mapped[str] = mapped_column(String(20))    # "low" | "medium" | "high"
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    change_request: Mapped["ChangeRequest"] = relationship(back_populates="report")
    findings: Mapped[list["ReportFinding"]] = relationship(back_populates="report")


class ReportFinding(Base):
    __tablename__ = "report_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("impact_reports.id"))
    kind: Mapped[str] = mapped_column(String(30))          # "blocker" | "affected" | "clear" | "recommendation"
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["ImpactReport"] = relationship(back_populates="findings")