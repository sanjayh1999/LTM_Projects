from __future__ import annotations

import re
import sys

from app.agent.investigate import NO_METADATA_PREFIX
from app.agent.schemas import ChangeRequest, ImpactFinding
from app.agent.state import AgentState, RiskLevel, get_change_request

SIGNAL_MULTIPLE_PROJECTS = "multiple_projects"
SIGNAL_REMOVE = "remove"
SIGNAL_MAJOR_VERSION = "major_version_jump"
SIGNAL_VERSION_NOT_FOUND = "version_not_found"
SIGNAL_VERSION_CONFLICT = "version_conflict"
SIGNAL_PYTHON_INCOMPATIBLE = "python_incompatible"
SIGNAL_NO_WHEEL = "no_wheel"

_VERSION_RE = re.compile(r"^(\d+)")


def _current_versions(findings: list[ImpactFinding]) -> list[str]:
    """Installed version in every environment found by investigate."""
    versions: list[str] = []
    for f in findings:
        if f.source == "inventory" and " currently uses " in f.text:
            # e.g. "AutoDiag_RAG currently uses numpy 2.4.6 (requires_python: >=3.11)"
            parts = f.text.split(" currently uses ", 1)[1].split()
            if len(parts) >= 2:
                versions.append(parts[1])
    return versions


def _major(version: str | None) -> int | None:
    if not version:
        return None
    match = _VERSION_RE.match(version)
    return int(match.group(1)) if match else None


def assess_risk(state: AgentState) -> dict:
    """LangGraph node: rule-based risk classification from gathered findings and project checks."""
    change_request = get_change_request(state)
    findings: list[ImpactFinding] = state.get("findings", [])
    affected_projects: list[str] = state.get("affected_projects", [])
    checks: list[dict] = state.get("project_checks", [])
    pkg, target = change_request.package_name, change_request.target_version

    current_versions = _current_versions(findings)
    current_version = current_versions[0] if current_versions else None

    # Short-circuit: every environment already has the requested version
    if (
        change_request.action in ("upgrade", "downgrade", "install")
        and target
        and current_versions
        and all(v == target for v in current_versions)
    ):
        return {
            "risk_level": "low",
            "risk_reasons": [f"{pkg} {target} is already installed everywhere it is used. This change is a no-op."],
            "signals": [],
            "is_noop": True,
            "affected_projects": [],
        }

    reasons: list[str] = []
    signals: list[str] = []
    risk_score = 0

    # Signal 1: blast radius
    if len(affected_projects) == 0:
        reasons.append("No scanned project currently depends on this package.")
    elif len(affected_projects) == 1:
        risk_score += 1
        reasons.append(f"1 project would be affected: {affected_projects[0]}.")
    else:
        risk_score += 2
        signals.append(SIGNAL_MULTIPLE_PROJECTS)
        reasons.append(f"{len(affected_projects)} projects would be affected: {', '.join(affected_projects)}.")

    # Signal 2: removal breaks the packages that require it
    if change_request.action == "remove" and affected_projects:
        risk_score += 3
        signals.append(SIGNAL_REMOVE)
        broken = [c for c in checks if c.get("breaks_on_remove")]
        if broken:
            detail = "; ".join(f"{c['project']}: {len(c['breaks_on_remove'])} package(s)" for c in broken)
            reasons.append(f"Removing it breaks installed packages that require it ({detail}).")
        else:
            reasons.append("Removing a package that a project depends on will break that project's imports.")
        transitive = [c["project"] for c in checks
                      if c.get("installed_version") and not c.get("is_direct") and not c.get("error")]
        if transitive:
            reasons.append(f"It is not declared directly in {', '.join(transitive)}; "
                           f"it is installed because other packages need it.")

    # Signal 3: major version jump
    if target and current_version:
        current_major, target_major = _major(current_version), _major(target)
        if current_major is not None and target_major is not None and target_major != current_major:
            risk_score += 2
            signals.append(SIGNAL_MAJOR_VERSION)
            reasons.append(f"This is a major version change ({current_version} -> {target}), "
                           f"which commonly includes breaking changes.")

    # Signal 4: target version is outside a dependent package's allowed range
    conflicted = [c for c in checks if c.get("conflicts")]
    if conflicted:
        risk_score += 3
        signals.append(SIGNAL_VERSION_CONFLICT)
        names = sorted({x["package"] for c in conflicted for x in c["conflicts"]})
        reasons.append(f"{pkg} {target} is outside the version range required by {', '.join(names)} "
                       f"(in {len(conflicted)} project(s)).")

    # Signal 5: target version does not support the venv's Python
    bad_python = [c for c in checks if c.get("python_ok") is False]
    if bad_python:
        risk_score += 3
        signals.append(SIGNAL_PYTHON_INCOMPATIBLE)
        where = ", ".join(f"{c['project']} (Python {c['python_version']})" for c in bad_python)
        reasons.append(f"{pkg} {target} does not support the Python version used by {where}.")

    # Signal 6: no ready-made wheel for this platform + Python
    no_wheel = [c for c in checks if c.get("wheel_status") in ("sdist_only", "none")]
    if no_wheel:
        risk_score += 2
        signals.append(SIGNAL_NO_WHEEL)
        reasons.append(f"No ready-made wheel of {pkg} {target} for {', '.join(c['project'] for c in no_wheel)}; "
                       f"pip would have to build it from source.")

    # Signal 7: target version could not be verified on PyPI
    missing = any(c.get("release_found") is False for c in checks) or any(
        f.source == "evidence" and f.text.startswith(NO_METADATA_PREFIX) for f in findings
    )
    if missing:
        risk_score += 1
        signals.append(SIGNAL_VERSION_NOT_FOUND)
        reasons.append(f"{pkg} {target} could not be found on PyPI, so its compatibility cannot be verified.")

    risk_level: RiskLevel
    if risk_score >= 4:
        risk_level = "high"
    elif risk_score >= 2:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {"risk_level": risk_level, "risk_reasons": reasons, "signals": signals, "is_noop": False}


if __name__ == "__main__":
    from app.agent.investigate import investigate

    package_name = sys.argv[1] if len(sys.argv) > 1 else "numpy"
    target_version = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    action = sys.argv[3] if len(sys.argv) > 3 else "upgrade"

    change_request = ChangeRequest(
        package_name=package_name, action=action, target_version=target_version  # type: ignore[arg-type]
    )
    state: AgentState = {"user_query": "(manual test)", "change_request": change_request}
    state.update(investigate(state))  # type: ignore[typeddict-item]
    result = assess_risk(state)

    print(f"--- assess_risk({action} {package_name} {target_version or ''}) ---")
    print(f"risk_level: {result['risk_level']}  signals: {result['signals']}")
    for reason in result["risk_reasons"]:
        print(f"  - {reason}")