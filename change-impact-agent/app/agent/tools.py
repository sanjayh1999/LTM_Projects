from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.db.base import SessionLocal
from app.db.models import Environment, GraphEdge, GraphNode, Package, Project


def locate_package(package_name: str) -> list[dict]:
    """Find every environment on this machine that has this package installed."""
    session = SessionLocal()
    try:
        stmt = (
            select(
                Package.name, Package.version, Package.requires_python,
                Project.name.label("project_name"), Project.path,
            )
            .join(Environment, Package.environment_id == Environment.id)
            .join(Project, Environment.project_id == Project.id)
            .where(Package.name.ilike(package_name))
        )
        rows = session.execute(stmt).all()
        return [
            {
                "package_name": r.name,
                "version": r.version,
                "requires_python": r.requires_python,
                "project_name": r.project_name,
                "project_path": r.path,
            }
            for r in rows
        ]
    finally:
        session.close()


def blast_radius(package_name: str) -> list[dict]:
    """Find every project whose dependency graph edge points at this package."""
    session = SessionLocal()
    try:
        source = aliased(GraphNode)
        target = aliased(GraphNode)
        stmt = (
            select(source.label.label("project_name"), target.label.label("package_label"))
            .join(GraphEdge, GraphEdge.source_id == source.id)
            .join(target, GraphEdge.target_id == target.id)
            .where(
                source.node_type == "project",
                target.node_type == "package",
                GraphEdge.relation == "depends_on",
                target.external_key.ilike(f"package:{package_name}:%"),
            )
        )
        rows = session.execute(stmt).all()
        return [{"project_name": r.project_name, "package_label": r.package_label} for r in rows]
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "numpy"

    print(f"--- locate_package('{name}') ---")
    for r in locate_package(name):
        print(f"  {r['project_name']}: {r['package_name']} {r['version']}  (requires_python: {r['requires_python']})")

    print(f"\n--- blast_radius('{name}') ---")
    for r in blast_radius(name):
        print(f"  {r['project_name']}  -> depends_on ->  {r['package_label']}")