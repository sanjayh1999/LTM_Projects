from __future__ import annotations

import sys

from app.agent.compat import check_change
from app.agent.deps import analyze_project_usage
from app.agent.schemas import ChangeRequest, ImpactFinding
from app.agent.state import AgentState, get_change_request
from app.agent.tools import blast_radius, locate_package
from app.rag.ingest import ingest_package_evidence
from app.rag.retrieve import retrieve_evidence

NO_METADATA_PREFIX = "No PyPI metadata found"
COMPAT_KEYS = ("release_found", "python_ok", "python_msg", "wheel_status", "wheel_msg",
               "conflicts", "breaks_on_remove")


def _resolve_project_hint(hint: str | None, candidates: list[str]) -> str | None:
    """Match the user's project mention to a real project name (case-insensitive, partial ok)."""
    if not hint:
        return None
    wanted = hint.strip().lower()
    for name in candidates:
        if name.lower() == wanted:
            return name
    partial = [name for name in candidates if wanted in name.lower() or name.lower() in wanted]
    return partial[0] if len(partial) == 1 else None


def _project_check(change_request: ChangeRequest, loc: dict) -> dict:
    """Dependency usage + compatibility verdict for one project's virtualenv."""
    usage = analyze_project_usage(change_request.package_name, loc["project_name"], loc["project_path"])
    try:
        compat = check_change(change_request.action, change_request.package_name,
                              change_request.target_version, usage)
    except Exception as exc:
        compat = {k: None for k in COMPAT_KEYS}
        compat.update(conflicts=[], breaks_on_remove=[], python_msg=f"Compatibility check failed: {exc}")
    return {
        "project": loc["project_name"],
        "error": usage.get("error"),
        "python_version": usage.get("python_version"),
        "installed_version": usage.get("installed_version"),
        "is_direct": usage.get("is_direct"),
        "root_basis": usage.get("root_basis", ""),
        "required_by": usage.get("required_by", []),
        "dependent_count": usage.get("dependent_count", 0),
        "chains": usage.get("chains", []),
        **{k: compat.get(k) for k in COMPAT_KEYS},
    }


def _check_findings(check: dict, package: str, target: str | None) -> list[ImpactFinding]:
    p = check["project"]
    if check["error"]:
        return [ImpactFinding(source="compatibility", text=f"{p}: could not inspect its environment ({check['error']}).")]

    out: list[ImpactFinding] = []
    if check["installed_version"]:
        kind = "a direct dependency" if check["is_direct"] else "a transitive dependency (not declared by the project)"
        out.append(ImpactFinding(
            source="graph",
            text=(f"{p}: {package} is {kind}; {len(check['required_by'])} installed packages require it "
                  f"directly, {check['dependent_count']} in total."),
        ))
        if check["chains"]:
            out.append(ImpactFinding(source="graph", text=f"{p}: example chain {' -> '.join(check['chains'][0])}"))
    if check["breaks_on_remove"]:
        names = ", ".join(i["package"] for i in check["breaks_on_remove"][:8])
        more = "..." if len(check["breaks_on_remove"]) > 8 else ""
        out.append(ImpactFinding(
            source="compatibility",
            text=f"{p}: removing {package} breaks {len(check['breaks_on_remove'])} installed packages that require it: {names}{more}",
        ))
    if check["python_ok"] is not None:
        out.append(ImpactFinding(source="compatibility", text=f"{p}: {check['python_msg']}"))
    if check["wheel_status"]:
        out.append(ImpactFinding(source="compatibility", text=f"{p}: {check['wheel_msg']}"))
    for c in check["conflicts"] or []:
        out.append(ImpactFinding(
            source="compatibility",
            text=f"{p}: {c['package']} requires {package} {c['specifier']}, which excludes {target}.",
        ))
    return out


def investigate(state: AgentState) -> dict:
    """LangGraph node: gather facts from inventory, dependency metadata, compatibility checks and PyPI."""
    change_request = get_change_request(state)
    package_name = change_request.package_name
    findings: list[ImpactFinding] = []
    scope_note = ""

    locations = locate_package(package_name)
    radius = blast_radius(package_name)
    all_projects = sorted(
        {loc["project_name"] for loc in locations} | {r["project_name"] for r in radius}
    )

    # 0. Scope: if the user named a project, only that project's environment is affected
    hint = change_request.project_hint
    if hint:
        scoped = _resolve_project_hint(hint, all_projects)
        if scoped:
            others = [p for p in all_projects if p != scoped]
            locations = [loc for loc in locations if loc["project_name"] == scoped]
            radius = [r for r in radius if r["project_name"] == scoped]
            scope_note = f"Analysis scoped to {scoped} as requested."
            if others:
                scope_note += (
                    f" {', '.join(others)} also have {package_name} installed, but each project "
                    f"has its own environment, so they are not affected by this change."
                )
        else:
            scope_note = (
                f"Project '{hint}' was not found among projects that have {package_name}; "
                f"showing all of them instead."
            )
        findings.append(ImpactFinding(source="inventory", text=scope_note))

    # 1. Inventory: where is this package actually installed right now?
    if not locations:
        findings.append(ImpactFinding(
            source="inventory",
            text=f"'{package_name}' was not found installed in any scanned environment.",
        ))
    for loc in locations:
        findings.append(ImpactFinding(
            source="inventory",
            text=(f"{loc['project_name']} currently uses {loc['package_name']} "
                  f"{loc['version']} (requires_python: {loc['requires_python']})"),
        ))

    # 2. Dependency usage + compatibility, per affected project venv
    project_checks = [_project_check(change_request, loc) for loc in locations]
    for check in project_checks:
        findings.extend(_check_findings(check, package_name, change_request.target_version))

    affected_projects = sorted({r["project_name"] for r in radius})

    # 3. Evidence: what does the package's own published metadata say about the target version?
    target_version = change_request.target_version
    if target_version:
        try:
            ingest_package_evidence(package_name, target_version)
        except Exception as exc:
            findings.append(ImpactFinding(
                source="evidence",
                text=f"Could not fetch PyPI metadata for {package_name} {target_version}: {exc}",
            ))
        else:
            query = (f"does {package_name} {target_version} support the currently installed "
                     f"Python version, and what changed in this release")
            evidence_rows = retrieve_evidence(query, package_name=package_name, version=target_version, top_k=3)
            if not evidence_rows:
                findings.append(ImpactFinding(
                    source="evidence",
                    text=(f"{NO_METADATA_PREFIX} for {package_name} {target_version}. "
                          f"This version may not exist on PyPI."),
                ))
            for row in evidence_rows:
                findings.append(ImpactFinding(
                    source="evidence",
                    text=f"[{row['package_name']} {row['version']}] {row['text']}",
                ))

    return {
        "findings": findings,
        "affected_projects": affected_projects,
        "project_checks": project_checks,
        "scope_note": scope_note,
    }


if __name__ == "__main__":
    package_name = sys.argv[1] if len(sys.argv) > 1 else "numpy"
    target_version = sys.argv[2] if len(sys.argv) > 2 else "1.24.3"
    action = sys.argv[3] if len(sys.argv) > 3 else "downgrade"

    change_request = ChangeRequest(package_name=package_name, action=action, target_version=target_version)  # type: ignore[arg-type]
    result = investigate({"user_query": "(manual test)", "change_request": change_request})

    print(f"--- investigate({action} {package_name} {target_version}) ---")
    print(f"affected_projects: {result['affected_projects']}\n")
    for f in result["findings"]:
        if f.source != "evidence":
            print(f"[{f.source}] {f.text}")
    for check in result["project_checks"]:
        print(f"\n{check['project']}:")
        for k in ("is_direct", "python_ok", "wheel_status", "conflicts"):
            v = check[k]
            print(f"  {k}: {v}")