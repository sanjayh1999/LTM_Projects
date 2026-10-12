from __future__ import annotations

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from app.agent.assess_risk import (
    SIGNAL_NO_WHEEL,
    SIGNAL_PYTHON_INCOMPATIBLE,
    SIGNAL_REMOVE,
    SIGNAL_VERSION_CONFLICT,
    SIGNAL_VERSION_NOT_FOUND,
)
from app.agent.llm import get_llm
from app.agent.schemas import ChangeRequest, ImpactFinding
from app.agent.state import AgentState, get_change_request

EVIDENCE_SNIPPET_CHARS = 300

EXPLAIN_SYSTEM_PROMPT = """You explain the risk of a proposed Python package change to a developer.

Write 2 to 3 sentences explaining WHY the change has the stated risk level, using only the \
risk reasons and findings provided.

Rules:
- Do not invent versions, projects, packages or compatibility claims.
- Projects are the developer's own folders (for example AutoDiag_RAG). Names such as pandas, \
scipy or langchain-community are installed packages: call them packages, never projects.
- Do not list which projects are or are not affected; that is shown separately.
- Do not give recommendations or next steps; that is shown separately.
- Start directly with the explanation. No preamble, no headings, no bullet points."""


def _format_facts(state: AgentState, change_request: ChangeRequest) -> str:
    findings: list[ImpactFinding] = state.get("findings", [])
    lines = [
        f"Requested change: {change_request.action} {change_request.package_name}"
        + (f" to {change_request.target_version}" if change_request.target_version else ""),
        f"Risk level: {state.get('risk_level', 'unknown')}",
        "Risk reasons:",
    ]
    lines += [f"- {r}" for r in state.get("risk_reasons", [])]
    lines.append("Findings:")
    for f in findings:
        text = f.text
        if f.source == "evidence" and len(text) > EVIDENCE_SNIPPET_CHARS:
            text = text[:EVIDENCE_SNIPPET_CHARS] + "..."
        lines.append(f"- [{f.source}] {text}")
    return "\n".join(lines)


def _summary_line(state: AgentState, change_request: ChangeRequest) -> str:
    risk = str(state.get("risk_level", "unknown")).upper()
    change = f"{change_request.action} {change_request.package_name}"
    if change_request.target_version:
        change += f" to {change_request.target_version}"
    affected = state.get("affected_projects", [])
    if affected:
        who = f"would affect {len(affected)} project(s): {', '.join(affected)}"
    else:
        who = "would not affect any scanned project"
    return f"Risk: {risk}. The request to {change} {who}."


def _memory_note(state: AgentState) -> str:
    memories = state.get("memories") or []
    if not memories:
        return ""
    m = memories[0]
    note = (f"Memory: a similar question was analysed on {m['created_at']} "
            f"(\u201c{m['query']}\u201d) and rated {str(m['risk_level']).upper()}")
    if m.get("dry_run_status"):
        note += f"; its dry run result was {str(m['dry_run_status']).upper()}"
    return note + "."


def _combined_range(specs: list[str]) -> str:
    """Merge several version ranges into the tightest single range, e.g. '>=1.26.4,<2.7'."""
    try:
        combined = SpecifierSet(",".join(specs))
    except InvalidSpecifier:
        return "; ".join(specs)
    lower: tuple[str, Version] | None = None
    upper: tuple[str, Version] | None = None
    others: list[str] = []
    for s in combined:
        try:
            v = Version(s.version)
        except InvalidVersion:
            others.append(str(s))
            continue
        if s.operator in (">=", ">"):
            if lower is None or v > lower[1]:
                lower = (s.operator, v)
        elif s.operator in ("<", "<="):
            if upper is None or v < upper[1]:
                upper = (s.operator, v)
        else:
            others.append(str(s))
    parts = [f"{op}{v}" for op, v in (lower, upper) if op] if False else []
    if lower:
        parts.append(f"{lower[0]}{lower[1]}")
    if upper:
        parts.append(f"{upper[0]}{upper[1]}")
    return ",".join(parts + others)


def _recommendation(state: AgentState, change_request: ChangeRequest) -> str:
    signals = state.get("signals", [])
    checks = state.get("project_checks", [])
    pkg, target = change_request.package_name, change_request.target_version
    affected = state.get("affected_projects", [])
    projects = ", ".join(affected)

    if SIGNAL_VERSION_NOT_FOUND in signals:
        return (f"Double-check the version number: {pkg} {target} was not found on PyPI. "
                f"Run `pip index versions {pkg}` to list the versions that exist.")
    if not affected:
        return (f"Nothing scanned on this machine depends on {pkg}, so this change is safe to try. "
                f"Make it inside the specific project's virtualenv rather than globally.")
    if SIGNAL_PYTHON_INCOMPATIBLE in signals:
        return (f"Keep the current {pkg} version. {pkg} {target} does not support this venv's Python, "
                f"so the project would first need a virtualenv on a supported Python version.")
    if SIGNAL_VERSION_CONFLICT in signals:
        specs = sorted({x["specifier"] for c in checks for x in (c.get("conflicts") or [])})
        names = sorted({x["package"] for c in checks for x in (c.get("conflicts") or [])})
        return (f"Choose a {pkg} version in the range {_combined_range(specs)}, which every dependent "
                f"package accepts, or upgrade {', '.join(names)} first. As requested, pip would refuse "
                f"the change or leave those packages broken. Use Verify with dry run to confirm.")
    if SIGNAL_NO_WHEEL in signals:
        return (f"Pick a {pkg} version that ships a ready-made wheel for your Python on Windows, or "
                f"install C/C++ build tools before trying this one.")
    if SIGNAL_REMOVE in signals:
        transitive = any(c.get("installed_version") and not c.get("is_direct") for c in checks)
        if transitive:
            return (f"Leave {pkg} installed. Other installed packages need it, and since the project does "
                    f"not declare it directly, pip would reinstall it on the next install anyway. To get rid "
                    f"of it, remove the packages that pull it in first.")
        return (f"Before removing it, search the code of {projects} for `import {pkg}` and run "
                f"`pip show {pkg}` inside that environment; only remove it if nothing uses it.")
    return (f"Run Verify with dry run to let pip confirm the change, then apply it in {projects} and run "
            f"their tests. Read the {pkg} release notes before upgrading for real.")


def write_report(state: AgentState) -> dict:
    """LangGraph node: deterministic facts + a short LLM-written explanation."""
    change_request = get_change_request(state)

    llm = get_llm()
    response = llm.invoke(
        [
            ("system", EXPLAIN_SYSTEM_PROMPT),
            ("human", _format_facts(state, change_request)),
        ]
    )
    explanation = str(response.content).strip()

    parts = [_summary_line(state, change_request)]
    scope_note = state.get("scope_note")
    if scope_note:
        parts.append(scope_note)
    memory_note = _memory_note(state)
    if memory_note:
        parts.append(memory_note)
    parts.append(explanation)
    parts.append(f"Recommended next step: {_recommendation(state, change_request)}")
    return {"report": "\n\n".join(parts)}


def write_noop_report(state: AgentState) -> dict:
    """LangGraph node: fixed report for a change that would not modify anything (no LLM)."""
    change_request = get_change_request(state)
    parts = [
        f"Risk: LOW. No action needed: {change_request.package_name} "
        f"{change_request.target_version} is already installed everywhere it is used, "
        f"so this change would not modify anything."
    ]
    scope_note = state.get("scope_note")
    if scope_note:
        parts.append(scope_note)
    memory_note = _memory_note(state)
    if memory_note:
        parts.append(memory_note)
    return {"report": "\n\n".join(parts)}