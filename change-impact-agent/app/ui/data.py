from __future__ import annotations

import urllib.request

from sqlalchemy import distinct, func, select, text

from app.config import get_settings
from app.db.base import SessionLocal
from app.db.models import Environment, Package, Project


def check_database() -> tuple[bool, str]:
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        return True, "Connected"
    except Exception as exc:
        return False, str(exc).splitlines()[0]
    finally:
        session.close()


def check_llm() -> tuple[bool, str]:
    settings = get_settings()
    if settings.llm_provider != "ollama":
        return True, f"{settings.llm_provider}: {settings.llm_model}"
    url = f"{settings.ollama_base_url}/api/tags"
    # Bypass any corporate proxy settings for this localhost check
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=2) as response:
            ok = response.status == 200
        return ok, f"Ollama · {settings.llm_model}"
    except Exception:
        return False, f"Ollama not reachable at {settings.ollama_base_url}"


def project_summary() -> list[dict]:
    session = SessionLocal()
    try:
        stmt = (
            select(Project.name, Project.path, func.count(Package.id).label("package_count"))
            .select_from(Project)
            .join(Environment, Environment.project_id == Project.id)
            .join(Package, Package.environment_id == Environment.id)
            .group_by(Project.name, Project.path)
            .order_by(Project.name)
        )
        return [
            {"project": r.name, "packages": r.package_count, "path": r.path}
            for r in session.execute(stmt).all()
        ]
    finally:
        session.close()


def packages_for_project(project_name: str) -> list[dict]:
    session = SessionLocal()
    try:
        stmt = (
            select(Package.name, Package.version, Package.requires_python)
            .select_from(Package)
            .join(Environment, Package.environment_id == Environment.id)
            .join(Project, Environment.project_id == Project.id)
            .where(Project.name == project_name)
            .order_by(func.lower(Package.name))
        )
        return [
            {"name": r.name, "version": r.version, "requires_python": r.requires_python}
            for r in session.execute(stmt).all()
        ]
    finally:
        session.close()


def shared_packages(limit: int = 100) -> list[dict]:
    """Packages installed in more than one project, with version drift detection."""
    session = SessionLocal()
    try:
        package_key = func.lower(Package.name)
        project_count = func.count(distinct(Project.id))
        version_count = func.count(distinct(Package.version))
        stmt = (
            select(
                package_key.label("package"),
                project_count.label("project_count"),
                version_count.label("version_count"),
                func.array_agg(distinct(Project.name)).label("projects"),
                func.array_agg(distinct(Package.version)).label("versions"),
            )
            .select_from(Package)
            .join(Environment, Package.environment_id == Environment.id)
            .join(Project, Environment.project_id == Project.id)
            .group_by(package_key)
            .having(project_count > 1)
            .order_by(version_count.desc(), project_count.desc(), package_key)
            .limit(limit)
        )
        return [
            {
                "package": r.package,
                "project_count": r.project_count,
                "version_count": r.version_count,
                "projects": sorted(r.projects),
                "versions": sorted(r.versions),
            }
            for r in session.execute(stmt).all()
        ]
    finally:
        session.close()