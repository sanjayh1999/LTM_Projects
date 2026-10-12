from __future__ import annotations

import platform
import socket
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import SessionLocal
from app.db.models import (
    Environment, GitRepo, GraphEdge, GraphNode, Machine, Manifest, Package, Project, Requirement,
)
from app.discovery.environments import find_virtualenvs, venv_python_exe
from app.discovery.git_scan import find_git_repos
from app.discovery.interpreters import get_installed_packages
from app.graph.dockerfile_parser import parse_dockerfile
from app.graph.manifest_parsers import parse_pyproject_toml, parse_requirements_txt

COMMON_VENV_NAMES = {"venv", ".venv", "env", ".env", "virtualenv"}


def _project_root_for_venv(venv_path: str) -> Path:
    p = Path(venv_path)
    return p.parent if p.name.lower() in COMMON_VENV_NAMES else p


def _default_roots() -> list[str]:
    settings = get_settings()
    if settings.scan_roots:
        return [r.strip() for r in settings.scan_roots.split(",") if r.strip()]
    return [str(Path.home() / "Desktop"), str(Path.home() / "Documents")]


def _find_manifests(project_root: Path) -> list[dict]:
    manifests = []
    for filename, kind in [
        ("requirements.txt", "requirements_txt"),
        ("pyproject.toml", "pyproject_toml"),
        ("Dockerfile", "dockerfile"),
    ]:
        candidate = project_root / filename
        if candidate.exists():
            manifests.append({"kind": kind, "path": str(candidate)})
    return manifests


def _get_or_create_node(session: Session, node_type: str, external_key: str, label: str) -> GraphNode:
    node = session.execute(
        select(GraphNode).where(GraphNode.node_type == node_type, GraphNode.external_key == external_key)
    ).scalar_one_or_none()
    if node is None:
        node = GraphNode(node_type=node_type, external_key=external_key, label=label)
        session.add(node)
        session.flush()
    return node


def _get_or_create_edge(session: Session, source_id: int, target_id: int, relation: str) -> None:
    existing = session.execute(
        select(GraphEdge).where(
            GraphEdge.source_id == source_id,
            GraphEdge.target_id == target_id,
            GraphEdge.relation == relation,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(GraphEdge(source_id=source_id, target_id=target_id, relation=relation))


def _get_or_create_manifest(session: Session, project_id: int, kind: str, path: str) -> Manifest:
    manifest = session.execute(
        select(Manifest).where(Manifest.project_id == project_id, Manifest.path == path)
    ).scalar_one_or_none()
    if manifest is None:
        manifest = Manifest(project_id=project_id, kind=kind, path=path)
        session.add(manifest)
        session.flush()
    return manifest


def _replace_requirements(session: Session, manifest_id: int, reqs: list[dict]) -> None:
    session.query(Requirement).filter(Requirement.manifest_id == manifest_id).delete()
    for r in reqs:
        session.add(Requirement(
            manifest_id=manifest_id,
            package_name=r["package_name"],
            version_spec=r.get("version_spec"),
            extras=r.get("extras"),
            marker=r.get("marker"),
        ))


def run_scan(roots: list[str] | None = None) -> None:
    roots = roots or _default_roots()
    print(f"Scanning: {roots}\n")

    venvs = find_virtualenvs(roots)
    repos = find_git_repos(roots)
    print(f"Found {len(venvs)} virtualenv(s), {len(repos)} git repo(s)\n")

    projects: dict[str, dict] = {}
    for v in venvs:
        root = str(_project_root_for_venv(v["path"]))
        projects.setdefault(root, {})["venv"] = v
    for r in repos:
        root = str(Path(r["path"]))
        projects.setdefault(root, {})["git"] = r

    session = SessionLocal()
    try:
        machine = session.execute(
            select(Machine).where(Machine.hostname == socket.gethostname())
        ).scalar_one_or_none()
        if machine is None:
            machine = Machine(hostname=socket.gethostname(), os=f"{platform.system()} {platform.release()}")
            session.add(machine)
            session.flush()

        for root_path, info in projects.items():
            project_name = Path(root_path).name

            project = session.execute(
                select(Project).where(Project.machine_id == machine.id, Project.path == root_path)
            ).scalar_one_or_none()
            if project is None:
                project = Project(machine_id=machine.id, name=project_name, path=root_path)
                session.add(project)
                session.flush()

            project_node = _get_or_create_node(session, "project", f"project:{root_path}", project_name)

            if "venv" in info:
                v = info["venv"]
                env = session.execute(
                    select(Environment).where(Environment.machine_id == machine.id, Environment.path == v["path"])
                ).scalar_one_or_none()
                if env is None:
                    env = Environment(
                        machine_id=machine.id, project_id=project.id, kind="venv",
                        python_version=v["python_version"], path=v["path"],
                    )
                    session.add(env)
                    session.flush()

                exe = venv_python_exe(v["path"])
                packages = get_installed_packages(exe) if exe else []

                for pkg in packages:
                    existing = session.execute(
                        select(Package).where(Package.environment_id == env.id, Package.name == pkg["name"])
                    ).scalar_one_or_none()
                    if existing is None:
                        session.add(Package(
                            environment_id=env.id,
                            name=pkg["name"],
                            version=pkg["version"] or "",
                            requires_python=pkg.get("requires_python"),
                        ))
                    else:
                        existing.version = pkg["version"] or ""
                        existing.requires_python = pkg.get("requires_python")

                    pkg_node = _get_or_create_node(
                        session, "package", f"package:{pkg['name']}:{pkg['version']}", f"{pkg['name']} {pkg['version']}"
                    )
                    _get_or_create_edge(session, project_node.id, pkg_node.id, "depends_on")

                print(f"{project_name}: {len(packages)} installed packages recorded")

            if "git" in info:
                r = info["git"]
                git_repo = session.execute(
                    select(GitRepo).where(GitRepo.project_id == project.id)
                ).scalar_one_or_none()
                if git_repo is None:
                    git_repo = GitRepo(project_id=project.id)
                    session.add(git_repo)
                git_repo.remote_url = r["remote_url"]
                git_repo.branch = r["branch"]
                git_repo.last_commit_hash = r["last_commit_hash"]
                git_repo.last_commit_at = r["last_commit_at"]

            for m in _find_manifests(Path(root_path)):
                manifest = _get_or_create_manifest(session, project.id, m["kind"], m["path"])

                if m["kind"] == "requirements_txt":
                    reqs = parse_requirements_txt(m["path"])
                    _replace_requirements(session, manifest.id, reqs)
                    print(f"{project_name}: {len(reqs)} declared requirement(s) in requirements.txt")

                elif m["kind"] == "pyproject_toml":
                    reqs = parse_pyproject_toml(m["path"])
                    _replace_requirements(session, manifest.id, reqs)
                    print(f"{project_name}: {len(reqs)} declared requirement(s) in pyproject.toml")

                elif m["kind"] == "dockerfile":
                    result = parse_dockerfile(m["path"])
                    _replace_requirements(session, manifest.id, result["pip_requirements"])
                    for image in result["base_images"]:
                        image_node = _get_or_create_node(session, "docker_image", f"docker_image:{image}", image)
                        _get_or_create_edge(session, project_node.id, image_node.id, "built_from")
                    print(
                        f"{project_name}: Dockerfile -> base image(s) {result['base_images']}, "
                        f"{len(result['pip_requirements'])} pinned package(s)"
                    )

        session.commit()
        print("\nScan complete — database updated.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import sys
    run_scan(sys.argv[1:] or None)