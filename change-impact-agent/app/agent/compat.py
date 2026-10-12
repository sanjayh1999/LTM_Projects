from __future__ import annotations

import sys
from functools import lru_cache

import requests
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import InvalidVersion, Version

PYPI_RELEASE_URL = "https://pypi.org/pypi/{name}/{version}/json"


@lru_cache(maxsize=256)
def fetch_release(package_name: str, version: str) -> dict | None:
    """Release metadata from PyPI, or None if that version does not exist."""
    response = requests.get(PYPI_RELEASE_URL.format(name=package_name, version=version), timeout=20)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    return {
        "requires_python": data["info"].get("requires_python") or "",
        "files": [
            {"filename": f["filename"], "packagetype": f["packagetype"], "yanked": f.get("yanked", False)}
            for f in data.get("urls", [])
        ],
    }


def check_python(requires_python: str, python_version: str) -> tuple[bool, str]:
    if not requires_python:
        return True, "No Python version restriction declared."
    try:
        ok = SpecifierSet(requires_python).contains(Version(python_version), prereleases=True)
    except (InvalidSpecifier, InvalidVersion):
        return True, f"Could not interpret Requires-Python '{requires_python}'."
    if ok:
        return True, f"Python {python_version} satisfies Requires-Python {requires_python}."
    return False, f"Requires-Python {requires_python} excludes this venv's Python {python_version}."


def check_wheels(files: list[dict], env_tags: list[str]) -> tuple[str, str]:
    """'wheel' = installable build exists, 'sdist_only' = pip must compile, 'none', or 'unknown'."""
    if not env_tags:
        return "unknown", "Could not read this venv's supported wheel tags."
    supported = set(env_tags)
    for f in files:
        if f["packagetype"] != "bdist_wheel" or f["yanked"]:
            continue
        try:
            _, _, _, tags = parse_wheel_filename(f["filename"])
        except InvalidWheelFilename:
            continue
        if any(str(t) in supported for t in tags):
            return "wheel", f"Compatible wheel available: {f['filename']}"
    if any(f["packagetype"] == "sdist" for f in files):
        return "sdist_only", "No compatible wheel; pip would have to build it from source (needs a compiler)."
    return "none", "No installable files for this platform and Python version."


def check_constraints(target_version: str, required_by: list[dict]) -> list[dict]:
    """Packages whose declared version range does NOT allow the target version."""
    try:
        target = Version(target_version)
    except InvalidVersion:
        return []
    conflicts = []
    for item in required_by:
        spec = item["specifier"]
        if spec == "any version":
            continue
        try:
            if not SpecifierSet(spec).contains(target, prereleases=True):
                conflicts.append(item)
        except InvalidSpecifier:
            continue
    return conflicts


def check_change(action: str, package_name: str, target_version: str | None, usage: dict) -> dict:
    """Compatibility verdict for one project, using the output of deps.analyze_project_usage."""
    result = {
        "project": usage["project"],
        "python_version": usage.get("python_version"),
        "release_found": None,
        "python_ok": None,
        "python_msg": "",
        "wheel_status": None,
        "wheel_msg": "",
        "conflicts": [],
        "breaks_on_remove": [],
    }
    if "error" in usage:
        result["python_msg"] = usage["error"]
        return result

    if action == "remove":
        result["breaks_on_remove"] = usage.get("required_by", [])
        return result

    if not target_version:
        return result

    release = fetch_release(package_name, target_version)
    result["release_found"] = release is not None
    if release is None:
        return result

    result["python_ok"], result["python_msg"] = check_python(release["requires_python"], usage["python_version"])
    result["wheel_status"], result["wheel_msg"] = check_wheels(release["files"], usage.get("tags", []))
    result["conflicts"] = check_constraints(target_version, usage.get("required_by", []))
    return result


if __name__ == "__main__":
    from app.agent.deps import analyze_project_usage
    from app.agent.tools import locate_package

    package = sys.argv[1] if len(sys.argv) > 1 else "numpy"
    version = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    action = sys.argv[3] if len(sys.argv) > 3 else "upgrade"

    print(f"--- {action} {package} {version or ''} ---")
    for loc in locate_package(package):
        usage = analyze_project_usage(package, loc["project_name"], loc["project_path"])
        r = check_change(action, package, version, usage)
        print(f"\n=== {r['project']} (Python {r['python_version']}) ===")
        if action == "remove":
            print(f"  removing breaks {len(r['breaks_on_remove'])} package(s): "
                  f"{', '.join(i['package'] for i in r['breaks_on_remove'][:8])}")
            continue
        if r["release_found"] is False:
            print(f"  {package} {version} does NOT exist on PyPI")
            continue
        print(f"  python : {'OK ' if r['python_ok'] else 'FAIL'} - {r['python_msg']}")
        print(f"  wheel  : {r['wheel_status']} - {r['wheel_msg']}")
        if r["conflicts"]:
            for c in r["conflicts"]:
                print(f"  CONFLICT: {c['package']} requires {package} {c['specifier']}")
        else:
            print("  conflicts: none")