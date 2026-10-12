from __future__ import annotations

import html
import time
import warnings
from datetime import datetime

# Silence a harmless deprecation notice raised inside LangGraph's own imports
warnings.filterwarnings("ignore", message=".*allowed_objects")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.agent.deps import analyze_project_usage  # noqa: E402
from app.agent.dryrun import dry_run  # noqa: E402
from app.agent.graph import build_graph, to_report  # noqa: E402
from app.agent.memory import list_recent, update_dry_run  # noqa: E402
from app.agent.schemas import ImpactReport  # noqa: E402
from app.agent.state import AgentState, get_change_request  # noqa: E402
from app.agent.tools import locate_package  # noqa: E402
from app.ui.data import (  # noqa: E402
    check_database,
    check_llm,
    packages_for_project,
    project_summary,
    shared_packages,
)

st.set_page_config(page_title="Change Impact Agent", layout="wide")

# ---------- constants ----------

EXAMPLES = [
    "Can I downgrade numpy to 1.24.3?",
    "Can I remove numpy from change-impact-agent?",
    "What if I upgrade numpy to 2.3.5?",
]

RISK_COLORS = {"high": "#A63D40", "medium": "#B7791F", "low": "#2F855A"}
RISK_TINTS = {"high": "#F8E7E7", "medium": "#FBF1DE", "low": "#E4F2EA"}
ACCENT = "#3B4CA8"
ACCENT_TINT = "#E8EBF7"

SIGNAL_LABELS = {
    "multiple_projects": "Shared by several projects",
    "remove": "Destructive change",
    "major_version_jump": "Major version jump",
    "version_conflict": "Version conflict",
    "python_incompatible": "Python incompatible",
    "no_wheel": "No ready-made wheel",
    "version_not_found": "Version not on PyPI",
}

STEP_LABELS = {
    "parse_change": "Understood the question",
    "recall_memory": "Checked memory for similar past changes",
    "investigate": "Checked environments, dependencies, compatibility and PyPI",
    "assess_risk": "Scored the risk",
    "write_report": "Wrote the explanation",
    "noop_report": "Nothing to change, skipped the LLM",
    "save_memory": "Saved the analysis to memory",
}

SOURCE_LABELS = {
    "inventory": "Installed packages",
    "graph": "Dependency graph",
    "compatibility": "Compatibility checks",
    "evidence": "PyPI metadata",
}

DRY_RUN_STYLE = {
    "ok": ("#2F855A", "OK"),
    "conflict": ("#A63D40", "CONFLICT"),
    "would_break": ("#A63D40", "WOULD BREAK"),
    "not_found": ("#B7791F", "NOT FOUND"),
    "unsupported": ("#B7791F", "UNSUPPORTED"),
    "skipped": ("#7C879B", "SKIPPED"),
    "error": ("#B7791F", "ERROR"),
}
DRY_RUN_SEVERITY = ["conflict", "would_break", "not_found", "unsupported", "error", "skipped", "ok"]

EVIDENCE_DISPLAY_CHARS = 400

CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.risk-card {
  background: #FFFFFF; border: 1px solid #DBE1EB; border-left: 6px solid var(--risk);
  border-radius: 10px; padding: 1.1rem 1.3rem; margin: .5rem 0 1rem;
}
.risk-card .level {
  font-size: .78rem; font-weight: 600; letter-spacing: .12em;
  text-transform: uppercase; color: var(--risk);
}
.risk-card .change {font-size: 1.4rem; font-weight: 600; color: #12192A; margin-top: .15rem;}
.risk-card .question {font-size: .9rem; color: #7C879B; margin-top: .2rem;}
.chip {
  display: inline-block; padding: .15rem .65rem; margin: .55rem .35rem 0 0;
  border-radius: 999px; font-size: .75rem; background: #E8EBF7; color: #2A3880;
}
.badge {
  display: inline-block; padding: .1rem .55rem; border-radius: 6px; font-size: .75rem;
  font-weight: 600; color: #FFFFFF; background: var(--badge); margin-right: .4rem;
}
.step-meta {color: #7C879B; font-size: .8rem;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------- session state ----------

for _key, _default in (("current", None), ("query", ""), ("next_id", 1), ("dryruns", {})):
    if _key not in st.session_state:
        st.session_state[_key] = _default


# ---------- cached data ----------

@st.cache_data(ttl=60, show_spinner=False)
def cached_projects() -> list[dict]:
    return project_summary()


@st.cache_data(ttl=60, show_spinner=False)
def cached_packages(project_name: str) -> list[dict]:
    return packages_for_project(project_name)


@st.cache_data(ttl=60, show_spinner=False)
def cached_shared() -> list[dict]:
    return shared_packages()


@st.cache_data(ttl=60, show_spinner=False)
def cached_locate(package_name: str) -> list[dict]:
    return locate_package(package_name)


@st.cache_data(ttl=30, show_spinner=False)
def cached_health() -> tuple[tuple[bool, str], tuple[bool, str]]:
    return check_database(), check_llm()


# ---------- helpers ----------

def set_query(text: str) -> None:
    st.session_state.query = text


def describe_change(report: ImpactReport) -> str:
    change = f"{report.action.capitalize()} {report.package_name}"
    if report.target_version:
        change += f" to {report.target_version}"
    return change


def badge(status: str) -> str:
    color, label = DRY_RUN_STYLE.get(status, ("#7C879B", status.upper()))
    return f"<span class='badge' style='--badge:{color}'>{label}</span>"


def _q(value: object) -> str:
    """Escape a value for use inside a Graphviz quoted string."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def dependency_dot(
    package_name: str, rows: list[dict], affected: set[str] | None, color: str, tint: str
) -> str:
    """Graphviz diagram: every project that has the package, pointing at it."""
    lines = [
        "digraph {",
        "rankdir=LR;",
        'bgcolor="transparent";',
        'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, '
        'color="#C6CFDD", fillcolor="#FFFFFF", fontcolor="#12192A"];',
        'edge [color="#7C879B", fontname="Helvetica", fontsize=9, fontcolor="#4C566B"];',
        f'pkg [label="{_q(package_name)}", fillcolor="{color}", color="{color}", fontcolor="#FFFFFF"];',
    ]
    for i, row in enumerate(rows):
        project = row["project_name"]
        is_hit = affected is None or project in affected
        if is_hit:
            node_style = f'fillcolor="{tint}", color="{color}"'
            edge_style = f'color="{color}", penwidth=2'
        else:
            node_style = 'fillcolor="#F3F5F8", fontcolor="#7C879B"'
            edge_style = "style=dashed"
        lines.append(f'p{i} [label="{_q(project)}", {node_style}];')
        lines.append(f'p{i} -> pkg [label="{_q(row["version"])}", {edge_style}];')
    lines.append("}")
    return "\n".join(lines)


def run_with_progress(query: str) -> tuple[AgentState, list[tuple[str, float]]]:
    """Run the LangGraph agent node by node, showing each step as it completes."""
    graph = build_graph()
    state: dict = {"user_query": query}
    steps: list[tuple[str, float]] = []

    with st.status("Running the agent...", expanded=True) as status:
        started = time.perf_counter()
        step_started = started
        for update in graph.stream({"user_query": query}, stream_mode="updates"):
            for node, delta in update.items():
                if delta:
                    state.update(delta)
                now = time.perf_counter()
                label = STEP_LABELS.get(node, node)
                steps.append((label, now - step_started))
                st.markdown(
                    f":material/check_circle: {label} "
                    f"<span class='step-meta'>{now - step_started:.1f}s</span>",
                    unsafe_allow_html=True,
                )
                step_started = now
        status.update(
            label=f"Analysis complete in {time.perf_counter() - started:.1f}s",
            state="complete",
            expanded=False,
        )
    return state, steps  # type: ignore[return-value]


def run_dry_runs(report: ImpactReport) -> list[dict]:
    """Human-approved verification: pip's resolver in dry-run mode, one venv at a time."""
    locations = {loc["project_name"]: loc for loc in cached_locate(report.package_name)}
    results: list[dict] = []
    with st.status("Running pip dry runs (nothing will be installed)...", expanded=True) as status:
        for project in report.affected_projects:
            loc = locations.get(project)
            if not loc:
                continue
            st.write(f"Checking {project}...")
            usage = analyze_project_usage(report.package_name, project, loc["project_path"])
            results.append(dry_run(report.action, report.package_name, report.target_version, usage))
        status.update(label="Dry run finished", state="complete", expanded=False)
    return results


def overall_status(results: list[dict]) -> str:
    known = [r["status"] for r in results if r["status"] in DRY_RUN_SEVERITY]
    return min(known, key=DRY_RUN_SEVERITY.index) if known else "error"


def report_to_markdown(entry: dict) -> str:
    report: ImpactReport = entry["report"]
    state: AgentState = entry["state"]
    lines = [
        "# Change impact report",
        "",
        f"**Question:** {entry['query']}",
        f"**Analyzed:** {entry['timestamp']}",
        f"**Risk:** {report.risk_level.upper()}",
        f"**Affected projects:** {', '.join(report.affected_projects) or 'none'}",
        "",
        "## Report",
        "",
        report.narrative,
        "",
        "## Risk reasons",
        "",
    ]
    lines += [f"- {reason}" for reason in report.risk_reasons]
    results = st.session_state.dryruns.get(entry["id"])
    if results:
        lines += ["", "## Dry run verification", ""]
        for r in results:
            lines.append(f"- **{r['project']}**: {r['status'].upper()}. {r['summary']}")
    lines += ["", "## Evidence", ""]
    for f in state.get("findings", []):
        text = f.text if len(f.text) <= EVIDENCE_DISPLAY_CHARS else f.text[:EVIDENCE_DISPLAY_CHARS] + "..."
        lines.append(f"- [{f.source}] {text}")
    return "\n".join(lines)


def render_compatibility(state: AgentState) -> None:
    checks = state.get("project_checks", [])
    if not checks:
        st.info("The package is not installed in any scanned project, so there was nothing to check.")
        return
    rows = []
    for c in checks:
        if c.get("error"):
            rows.append({"Project": c["project"], "Python": "?", "Installed": "?", "Declared directly": "?",
                         "Required by": "?", "Python check": "?", "Wheel": "?", "Conflicts": c["error"]})
            continue
        python_check = "OK" if c.get("python_ok") else ("FAIL" if c.get("python_ok") is False else "n/a")
        conflicts = ", ".join(f"{x['package']} ({x['specifier']})" for x in c.get("conflicts") or [])
        rows.append({
            "Project": c["project"],
            "Python": c.get("python_version") or "?",
            "Installed": c.get("installed_version") or "not installed",
            "Declared directly": "yes" if c.get("is_direct") else "no (transitive)",
            "Required by": f"{len(c.get('required_by') or [])} direct / {c.get('dependent_count', 0)} total",
            "Python check": python_check,
            "Wheel": c.get("wheel_status") or "n/a",
            "Conflicts": conflicts or "none",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    for c in checks:
        if c.get("chains"):
            chain = " \u2192 ".join(c["chains"][0])
            st.caption(f"**{c['project']}**: installed because {chain}")

def render_verify(entry: dict, key: str) -> None:
    report: ImpactReport = entry["report"]
    state: AgentState = entry["state"]
    results = st.session_state.dryruns.get(entry["id"])

    if state.get("is_noop"):
        st.info("Nothing would change, so there is nothing to verify.")
        return
    if not report.affected_projects:
        st.info("No scanned project is affected, so there is nothing to verify.")
        return
    if report.action != "remove" and not report.target_version:
        st.info("A dry run needs a target version. Ask again with a version number.")
        return

    st.markdown(
        "**Human approval required.** This asks pip's resolver whether the change can be applied "
        "while keeping every dependent package at its installed version. It runs with `--dry-run`, "
        "so **nothing is installed or removed**."
    )
    approved = st.checkbox(
        f"I approve running a dry run on: {', '.join(report.affected_projects)}",
        key=f"{key}-approve",
    )
    if st.button("Verify with dry run", type="primary", disabled=not approved, key=f"{key}-verify"):
        results = run_dry_runs(report)
        st.session_state.dryruns[entry["id"]] = results
        memory_id = entry.get("memory_id")
        if memory_id and results:
            summary = "; ".join(f"{r['project']}: {r['status']}" for r in results)
            try:
                update_dry_run(memory_id, overall_status(results), summary)
            except Exception as exc:
                st.warning(f"Dry run finished but could not be saved to memory: {exc}")

    if results:
        st.markdown(f"**Overall result:** {badge(overall_status(results))}", unsafe_allow_html=True)
        for r in results:
            st.markdown(f"{badge(r['status'])} **{html.escape(r['project'])}**: {html.escape(r['summary'])}",
                        unsafe_allow_html=True)
            if r.get("command"):
                st.code(r["command"], language="text")
            for line in (r.get("changes") or []) + (r.get("details") or []):
                st.markdown(f"- {line}")


def render_result(entry: dict, key: str) -> None:
    report: ImpactReport = entry["report"]
    state: AgentState = entry["state"]
    color = RISK_COLORS[report.risk_level]
    tint = RISK_TINTS[report.risk_level]

    chips = "".join(
        f"<span class='chip'>{html.escape(SIGNAL_LABELS.get(s, s))}</span>"
        for s in state.get("signals", [])
    )
    if state.get("is_noop"):
        chips += "<span class='chip'>No change needed</span>"
    if state.get("memories"):
        chips += "<span class='chip'>Similar past analysis found</span>"

    st.markdown(
        f"<div class='risk-card' style='--risk:{color}'>"
        f"<div class='level'>{report.risk_level} risk</div>"
        f"<div class='change'>{html.escape(describe_change(report))}</div>"
        f"<div class='question'>&ldquo;{html.escape(entry['query'])}&rdquo;</div>"
        f"{chips}</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projects affected", len(report.affected_projects))
    c2.metric("Target version", report.target_version or "n/a")
    c3.metric("Findings gathered", len(state.get("findings", [])))
    c4.metric("Time taken", f"{entry['duration']:.1f}s")

    t_report, t_compat, t_verify, t_map, t_why, t_evidence, t_trace = st.tabs(
        ["Report", "Compatibility", "Verify", "Impact map", "Why this risk", "Evidence", "Agent trace"]
    )

    with t_report:
        st.markdown(report.narrative)
        st.download_button(
            "Download report (.md)",
            data=report_to_markdown(entry),
            file_name=f"impact-{report.package_name}-{entry['id']}.md",
            mime="text/markdown",
            key=f"{key}-download",
        )

    with t_compat:
        render_compatibility(state)

    with t_verify:
        render_verify(entry, key)

    with t_map:
        rows = cached_locate(report.package_name)
        if rows:
            st.graphviz_chart(
                dependency_dot(report.package_name, rows, set(report.affected_projects), color, tint)
            )
            st.caption(
                "Highlighted projects are affected by this change. Dashed, grey projects have "
                "the package in their own environment and are not affected."
            )
        else:
            st.info("This package is not installed in any scanned project.")

    with t_why:
        for reason in report.risk_reasons:
            st.markdown(f"- {reason}")

    with t_evidence:
        findings = state.get("findings", [])
        for source, label in SOURCE_LABELS.items():
            items = [f for f in findings if f.source == source]
            if not items:
                continue
            st.markdown(f"**{label}** ({len(items)})")
            for f in items:
                text = f.text
                if len(text) > EVIDENCE_DISPLAY_CHARS:
                    text = text[:EVIDENCE_DISPLAY_CHARS] + "..."
                st.markdown(f"- {text}")

    with t_trace:
        st.markdown("**Steps the agent ran**")
        for label, seconds in entry["steps"]:
            st.markdown(
                f":material/check_circle: {label} <span class='step-meta'>{seconds:.1f}s</span>",
                unsafe_allow_html=True,
            )
        memories = state.get("memories") or []
        if memories:
            st.markdown("**Recalled from memory**")
            for m in memories:
                dry = f", dry run {m['dry_run_status']}" if m.get("dry_run_status") else ""
                st.markdown(f"- {m['created_at']}: \u201c{m['query']}\u201d rated "
                            f"{str(m['risk_level']).upper()}{dry} (distance {m['distance']:.2f})")
        st.markdown("**What the agent understood from your question**")
        st.json(get_change_request(state).model_dump())
        st.caption(f"Saved to memory as record #{state.get('memory_id')}")


# ---------- page ----------

st.title("What will this change break?")
st.caption(
    "A read-only agent that checks your real Python environments, dependency metadata and PyPI "
    "before you change a package, and verifies it with pip's resolver only when you approve."
)

tab_analyze, tab_inventory, tab_explorer, tab_history = st.tabs(
    ["Analyze a change", "Inventory", "Package explorer", "History"]
)

# ----- Analyze -----
with tab_analyze:
    st.caption("Try an example")
    example_cols = st.columns(len(EXAMPLES))
    for col, example in zip(example_cols, EXAMPLES):
        col.button(example, on_click=set_query, args=(example,), key=f"example-{example}")

    with st.form("ask", border=False):
        query = st.text_input(
            "Describe the change you're considering",
            key="query",
            placeholder="e.g. Can I upgrade pandas to 3.0 in AutoDiag_RAG?",
        )
        submitted = st.form_submit_button("Analyze impact", type="primary")

    if submitted:
        if not query.strip():
            st.warning("Type a question first.")
        else:
            try:
                started = time.perf_counter()
                state, steps = run_with_progress(query.strip())
                report = to_report(state)
            except Exception as exc:
                st.error(f"The agent failed: {exc}")
                st.info("Check the System status panel in the sidebar: Postgres (Docker) and Ollama must both be running.")
            else:
                st.session_state.current = {
                    "id": st.session_state.next_id,
                    "memory_id": state.get("memory_id"),
                    "query": query.strip(),
                    "report": report,
                    "state": state,
                    "steps": steps,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "duration": time.perf_counter() - started,
                }
                st.session_state.next_id += 1

    if st.session_state.current:
        render_result(st.session_state.current, key="current")
    else:
        st.info(
            "Ask about upgrading, downgrading, installing or removing a package. "
            "The agent will tell you which projects are affected, how risky it is, and why."
        )

# ----- Inventory -----
with tab_inventory:
    try:
        projects = cached_projects()
        shared = cached_shared()
    except Exception as exc:
        projects, shared = [], []
        st.error(f"Could not load inventory from the database: {exc}")

    if projects:
        drift = [s for s in shared if s["version_count"] > 1]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Projects", len(projects))
        m2.metric("Installed packages", sum(p["packages"] for p in projects))
        m3.metric("Shared packages", len(shared))
        m4.metric("Version drift", len(drift))

        st.subheader("Projects")
        st.dataframe(
            pd.DataFrame(projects).rename(
                columns={"project": "Project", "packages": "Packages", "path": "Location"}
            ),
            hide_index=True,
        )

        st.subheader("Packages by project")
        left, right = st.columns([1, 2])
        selected = left.selectbox("Project", [p["project"] for p in projects])
        search = right.text_input("Filter packages", placeholder="e.g. torch")
        package_rows = cached_packages(selected)
        if search.strip():
            package_rows = [r for r in package_rows if search.strip().lower() in r["name"].lower()]
        packages_df = pd.DataFrame(package_rows, columns=["name", "version", "requires_python"])
        st.dataframe(
            packages_df.rename(
                columns={"name": "Package", "version": "Version", "requires_python": "Requires Python"}
            ),
            hide_index=True,
        )
        st.download_button(
            "Download as CSV",
            data=packages_df.to_csv(index=False),
            file_name=f"{selected}-packages.csv",
            mime="text/csv",
        )

        st.subheader("Shared dependencies")
        st.caption(
            "Packages installed in more than one project have the widest blast radius. "
            "Drift means projects are running different versions of the same package."
        )
        if shared:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Package": s["package"],
                            "Projects": s["project_count"],
                            "Used by": ", ".join(s["projects"]),
                            "Versions": ", ".join(s["versions"]),
                            "Drift": "Yes" if s["version_count"] > 1 else "",
                        }
                        for s in shared
                    ]
                ),
                hide_index=True,
            )
        else:
            st.info("No package is shared between projects.")
    else:
        st.info("No scanned projects yet. Run `python -m app.discovery.scan` first.")

# ----- Package explorer -----
with tab_explorer:
    package_query = st.text_input("Package name", placeholder="e.g. numpy", key="explore_package")
    if package_query.strip():
        name = package_query.strip()
        try:
            rows = cached_locate(name)
        except Exception as exc:
            rows = []
            st.error(f"Lookup failed: {exc}")
        if not rows:
            st.info(f"'{name}' is not installed in any scanned project.")
        else:
            versions = sorted({r["version"] for r in rows})
            e1, e2 = st.columns(2)
            e1.metric("Installed in", f"{len(rows)} project(s)")
            e2.metric("Distinct versions", len(versions))
            if len(versions) > 1:
                st.warning(f"Version drift: {name} is installed as {', '.join(versions)}.")
            st.graphviz_chart(dependency_dot(name, rows, None, ACCENT, ACCENT_TINT))
            st.dataframe(
                pd.DataFrame(rows)[["project_name", "version", "requires_python", "project_path"]].rename(
                    columns={
                        "project_name": "Project",
                        "version": "Version",
                        "requires_python": "Requires Python",
                        "project_path": "Location",
                    }
                ),
                hide_index=True,
            )
    else:
        st.info("Type a package name to see every project that has it installed.")

# ----- History (from the database) -----
with tab_history:
    try:
        records = list_recent(100)
    except Exception as exc:
        records = []
        st.error(f"Could not load history from the database: {exc}")

    if not records:
        st.info("Analyses you run will appear here, and they are kept across restarts.")
    else:
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Analyses stored", len(records))
        h2.metric("High risk", sum(1 for r in records if r["risk_level"] == "high"))
        h3.metric("Medium risk", sum(1 for r in records if r["risk_level"] == "medium"))
        h4.metric("Verified by dry run", sum(1 for r in records if r["dry_run_status"]))

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "When": r["created_at"],
                        "Question": r["query"],
                        "Risk": r["risk_level"].upper(),
                        "Projects": ", ".join(r["projects"]) or "none",
                        "Dry run": (r["dry_run_status"] or "not run").upper(),
                    }
                    for r in records
                ]
            ),
            hide_index=True,
        )

        st.subheader("Recent reports")
        for r in records[:20]:
            with st.expander(f"{r['risk_level'].upper()} · {r['query']} · {r['created_at']}"):
                st.markdown(r["report"])
                if r["dry_run_status"]:
                    st.markdown(f"**Dry run:** {badge(r['dry_run_status'])} {html.escape(r['dry_run_summary'] or '')}",
                                unsafe_allow_html=True)

# ---------- sidebar (rendered last so it reflects this run) ----------

with st.sidebar:
    st.markdown("### Change Impact Agent")
    st.caption("Local, read-only analysis of what a package change would break.")

    st.markdown("#### System status")
    (db_ok, db_msg), (llm_ok, llm_msg) = cached_health()
    for ok, label, message in ((db_ok, "Database", db_msg), (llm_ok, "LLM", llm_msg)):
        dot = ":green[●]" if ok else ":red[●]"
        st.markdown(f"{dot} **{label}**: {message}")

    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Refresh after running `python -m app.discovery.scan`.")

    st.markdown("#### Memory")
    try:
        stored = len(list_recent(1000))
    except Exception:
        stored = 0
    st.caption(f"{stored} analyses stored")
    st.caption("History is stored in PostgreSQL (analysis_memory) and survives restarts.")