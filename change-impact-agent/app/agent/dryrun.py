from __future__ import annotations

import json
import subprocess
import sys

from packaging.utils import canonicalize_name

from app.agent.deps import analyze_project_usage, probe_environment


def _conflict_lines(stderr: str) -> list[str]:
    """Pull pip's 'The conflict is caused by:' block out of its error output."""
    lines = stderr.splitlines()
    out: list[str] = []
    capture = False
    for line in lines:
        if "The conflict is caused by" in line:
            capture = True
            continue
        if capture:
            if not line.strip():
                if out:
                    break
                continue
            out.append(line.strip())
    if not out:
        out = [l.strip() for l in lines if l.strip().startswith("ERROR")][:5]
    return out[:12]


def dry_run(action: str, package: str, version: str | None, usage: dict) -> dict:
    """Verify a change with pip's resolver inside the project's venv. Never installs anything."""
    base = {"project": usage["project"], "command": "", "status": "error", "summary": "",
            "details": [], "changes": []}
    if "error" in usage:
        return {**base, "summary": usage["error"]}

    if action == "remove":
        broken = usage.get("required_by", [])
        summary = (
            f"pip has no uninstall dry run, so this is simulated from installed metadata: removing "
            f"{package} would leave {len(broken)} package(s) with a missing requirement."
            if broken else
            f"Nothing installed requires {package}; removing it would not break other packages."
        )
        return {**base, "command": f"pip uninstall {package} (simulated)",
                "status": "would_break" if broken else "ok", "summary": summary,
                "details": [f"{b['package']} requires {package} {b['specifier']}" for b in broken]}

    if not version:
        return {**base, "status": "skipped", "summary": "A dry run needs a target version."}

    dists = probe_environment(usage["python_exe"])["dists"]
    installed = {canonicalize_name(n): info["version"] for n, info in dists.items()}

    # Pin every package that depends on the target at its installed version, so pip
    # must find a solution that keeps them all working, or refuse.
    pins = []
    for item in usage.get("required_by", []):
        current = installed.get(canonicalize_name(item["package"]))
        if current:
            pins.append(f"{item['package']}=={current}")

    requirement = f"{package}=={version}"
    cmd = [usage["python_exe"], "-m", "pip", "install", "--dry-run", "--quiet", "--report", "-",
           "--disable-pip-version-check", requirement, *pins]
    shown = f"pip install --dry-run {requirement}" + (f" (+{len(pins)} dependents pinned)" if pins else "")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {**base, "command": shown, "summary": "pip did not finish within 10 minutes."}

    if proc.returncode == 0:
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            report = {"install": []}
        changes = []
        for item in report.get("install", []):
            meta = item.get("metadata", {})
            name, new = meta.get("name", ""), meta.get("version", "")
            old = installed.get(canonicalize_name(name))
            if old != new:
                changes.append(f"{name}: {old or 'not installed'} -> {new}")
        summary = "pip's resolver found a consistent set of packages."
        summary += f" {len(changes)} package(s) would change." if changes else " Nothing would change."
        return {**base, "command": shown, "status": "ok", "summary": summary, "changes": changes}

    err = proc.stderr
    if "no such option: --report" in err or "no such option: --dry-run" in err:
        return {**base, "command": shown, "status": "unsupported",
                "summary": "This venv's pip is too old for dry runs (needs pip 22.2 or newer)."}
    if "No matching distribution" in err or "Could not find a version" in err:
        return {**base, "command": shown, "status": "not_found",
                "summary": f"pip could not find {requirement} for this Python and platform."}
    if "ResolutionImpossible" in err or "conflicting dependencies" in err:
        return {**base, "command": shown, "status": "conflict",
                "summary": f"pip refuses: {requirement} conflicts with packages already installed.",
                "details": _conflict_lines(err)}
    last = (err.strip().splitlines() or ["unknown error"])[-1]
    return {**base, "command": shown, "summary": f"pip failed: {last[:300]}"}


if __name__ == "__main__":
    from app.agent.tools import locate_package

    package = sys.argv[1] if len(sys.argv) > 1 else "numpy"
    version = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    action = sys.argv[3] if len(sys.argv) > 3 else "upgrade"
    only = sys.argv[4] if len(sys.argv) > 4 else None

    for loc in locate_package(package):
        if only and loc["project_name"].lower() != only.lower():
            continue
        usage = analyze_project_usage(package, loc["project_name"], loc["project_path"])
        r = dry_run(action, package, version, usage)
        print(f"\n=== {r['project']} ===")
        print(f"  command : {r['command']}")
        print(f"  status  : {r['status'].upper()}")
        print(f"  summary : {r['summary']}")
        for line in r["changes"] + r["details"]:
            print(f"      {line}")