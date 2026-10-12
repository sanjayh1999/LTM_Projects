from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement


def parse_requirements_txt(path: str) -> list[dict]:
    requirements = []
    text = Path(path).read_text(errors="ignore")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        line = line.split(" #", 1)[0].strip()  # strip inline comments
        if not line:
            continue
        if line.startswith(("-r", "--requirement", "-c", "--constraint", "-e", "--editable")):
            continue  # nested includes and editable installs — not resolved in this pass

        try:
            req = Requirement(line)
        except InvalidRequirement:
            continue

        requirements.append({
            "package_name": req.name,
            "version_spec": str(req.specifier) if req.specifier else None,
            "extras": ",".join(sorted(req.extras)) if req.extras else None,
            "marker": str(req.marker) if req.marker else None,
        })

    return requirements


def parse_pyproject_toml(path: str) -> list[dict]:
    with open(path, "rb") as f:
        data = tomllib.load(f)

    requirements = []

    # PEP 621 — modern standard
    project = data.get("project", {})
    for dep_str in project.get("dependencies", []):
        parsed = _parse_pep508(dep_str)
        if parsed:
            requirements.append(parsed)
    for group_deps in project.get("optional-dependencies", {}).values():
        for dep_str in group_deps:
            parsed = _parse_pep508(dep_str)
            if parsed:
                requirements.append(parsed)

    # Poetry — still very common
    poetry = data.get("tool", {}).get("poetry", {})
    for name, spec in poetry.get("dependencies", {}).items():
        if name.lower() != "python":
            requirements.append(_parse_poetry_dep(name, spec))
    for group_data in poetry.get("group", {}).values():
        for name, spec in group_data.get("dependencies", {}).items():
            if name.lower() != "python":
                requirements.append(_parse_poetry_dep(name, spec))

    return requirements


def _parse_pep508(dep_str: str) -> dict | None:
    try:
        req = Requirement(dep_str)
    except InvalidRequirement:
        return None
    return {
        "package_name": req.name,
        "version_spec": str(req.specifier) if req.specifier else None,
        "extras": ",".join(sorted(req.extras)) if req.extras else None,
        "marker": str(req.marker) if req.marker else None,
    }


def _parse_poetry_dep(name: str, spec) -> dict:
    if isinstance(spec, str):
        version_spec, extras = spec, None
    elif isinstance(spec, dict):
        version_spec = spec.get("version")
        extras_list = spec.get("extras")
        extras = ",".join(extras_list) if extras_list else None
    else:
        version_spec, extras = None, None
    return {"package_name": name, "version_spec": version_spec, "extras": extras, "marker": None}


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"
    reqs = parse_pyproject_toml(path) if path.endswith(".toml") else parse_requirements_txt(path)

    print(f"Parsed {len(reqs)} requirement(s) from {path}\n")
    for r in reqs:
        extras = f"[{r['extras']}]" if r["extras"] else ""
        spec = r["version_spec"] or "(any version)"
        marker = f"  ; {r.get('marker')}" if r.get("marker") else ""
        print(f"  {r['package_name']}{extras} {spec}{marker}")