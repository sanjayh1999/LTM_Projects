from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

VENV_DIR_NAMES = (".venv", "venv", "env")

# Runs INSIDE the target venv's Python: reports its version, wheel tags and every
# installed package with that package's own requirements (Requires-Dist).
_PROBE = r"""
import json, sys
import importlib.metadata as md
try:
    from packaging import tags
except Exception:
    try:
        from pip._vendor.packaging import tags
    except Exception:
        tags = None
dists = {}
for d in md.distributions():
    name = d.metadata["Name"]
    if name:
        dists[name] = {"version": d.version, "requires": list(d.requires or [])}
print(json.dumps({
    "python": "%d.%d.%d" % sys.version_info[:3],
    "tags": [str(t) for t in tags.sys_tags()] if tags else [],
    "dists": dists,
}))
"""


def _venv_python(venv_dir: Path) -> Path | None:
    for exe in (venv_dir / "Scripts" / "python.exe", venv_dir / "bin" / "python"):
        if exe.exists():
            return exe
    return None


def find_venv_python(project_path: str) -> Path | None:
    """Find the python.exe of the virtualenv that belongs to a project folder."""
    root = Path(project_path)
    if not root.is_dir():
        return None
    candidates = [root, *(root / n for n in VENV_DIR_NAMES)]
    candidates += [c for c in sorted(root.iterdir()) if c.is_dir() and c not in candidates]
    for c in candidates:
        if (c / "pyvenv.cfg").is_file():
            exe = _venv_python(c)
            if exe:
                return exe
    return None


@lru_cache(maxsize=32)
def probe_environment(python_exe: str) -> dict:
    result = subprocess.run(
        [python_exe, "-I", "-c", _PROBE], capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not inspect {python_exe}: {result.stderr.strip()[-400:]}")
    return json.loads(result.stdout)


def declared_requirements(project_path: str) -> tuple[set[str], list[str]]:
    """Package names the project itself declares (requirements*.txt, pyproject.toml)."""
    root = Path(project_path)
    names: set[str] = set()
    sources: list[str] = []

    for f in sorted(root.glob("requirements*.txt")):
        found = False
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            try:
                names.add(canonicalize_name(Requirement(line).name))
                found = True
            except InvalidRequirement:
                continue
        if found:
            sources.append(f.name)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            data = {}
        before = len(names)
        for raw in data.get("project", {}).get("dependencies", []) or []:
            try:
                names.add(canonicalize_name(Requirement(raw).name))
            except InvalidRequirement:
                continue
        for n in data.get("tool", {}).get("poetry", {}).get("dependencies", {}) or {}:
            if n.lower() != "python":
                names.add(canonicalize_name(n))
        if len(names) > before:
            sources.append("pyproject.toml")

    return names, sources


def build_reverse_graph(dists: dict, python_version: str) -> dict[str, list[tuple[str, str]]]:
    """dependency -> [(package that requires it, version specifier)], for this venv's Python."""
    env = default_environment()
    env.update({
        "python_version": ".".join(python_version.split(".")[:2]),
        "python_full_version": python_version,
        "extra": "",
    })
    installed = {canonicalize_name(n) for n in dists}
    reverse: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for name, info in dists.items():
        for raw in info["requires"]:
            try:
                req = Requirement(raw)
            except InvalidRequirement:
                continue
            if req.marker is not None:
                try:
                    if not req.marker.evaluate(env):
                        continue  # optional extra or a different platform/Python
                except Exception:
                    continue
            dep = canonicalize_name(req.name)
            if dep in installed:
                reverse[dep].append((name, str(req.specifier) or "any version"))
    return reverse


def analyze_project_usage(package_name: str, project_name: str, project_path: str) -> dict:
    """Why is this package in this project's venv, and who depends on it?"""
    target = canonicalize_name(package_name)
    base = {"project": project_name, "package": package_name}

    exe = find_venv_python(project_path)
    if exe is None:
        return {**base, "error": "No virtual environment found in the project folder."}
    try:
        probe = probe_environment(str(exe))
    except Exception as exc:
        return {**base, "error": str(exc)}

    dists = probe["dists"]
    by_canon = {canonicalize_name(n): (n, info) for n, info in dists.items()}
    result = {
        **base,
        "python_exe": str(exe),
        "python_version": probe["python"],
        "tags": probe["tags"],
        "installed_version": by_canon[target][1]["version"] if target in by_canon else None,
    }
    if target not in by_canon:
        return {**result, "is_direct": False, "root_basis": "", "required_by": [], "chains": [],
                "dependent_count": 0}

    reverse = build_reverse_graph(dists, probe["python"])
    declared, sources = declared_requirements(project_path)
    if sources:
        roots = declared
        root_basis = "declared in " + ", ".join(sources)
    else:
        roots = {n for n in by_canon if not reverse.get(n)}
        root_basis = "top-level installed packages (no requirements file found)"

    # Walk upwards: everything that directly or indirectly needs the target
    parent_of: dict[str, str | None] = {target: None}
    queue = deque([target])
    while queue:
        current = queue.popleft()
        for dependent, _ in reverse.get(current, []):
            d = canonicalize_name(dependent)
            if d not in parent_of:
                parent_of[d] = current
                queue.append(d)

    chains = []
    for root in sorted(roots):
        if root != target and root in parent_of:
            chain, node = [root], root
            while parent_of[node] is not None:
                node = parent_of[node]
                chain.append(node)
            chains.append([by_canon[n][0] if n in by_canon else n for n in chain])

    return {
        **result,
        "is_direct": target in roots,
        "root_basis": root_basis,
        "required_by": [{"package": p, "specifier": s} for p, s in reverse.get(target, [])],
        "chains": chains,
        "dependent_count": len(parent_of) - 1,
    }


if __name__ == "__main__":
    from app.agent.tools import locate_package

    package = sys.argv[1] if len(sys.argv) > 1 else "numpy"
    for loc in locate_package(package):
        r = analyze_project_usage(package, loc["project_name"], loc["project_path"])
        print(f"\n=== {r['project']} ===")
        if "error" in r:
            print(f"  ERROR: {r['error']}")
            continue
        print(f"  venv python : {r['python_version']}  ({r['python_exe']})")
        print(f"  installed   : {package} {r['installed_version']}")
        print(f"  direct?     : {r['is_direct']}   (roots = {r['root_basis']})")
        print(f"  required by : {len(r['required_by'])} package(s) directly, "
              f"{r['dependent_count']} in total")
        for item in r["required_by"][:10]:
            print(f"      - {item['package']} needs {package} {item['specifier']}")
        for chain in r["chains"][:5]:
            print(f"  chain       : {' -> '.join(chain)}")