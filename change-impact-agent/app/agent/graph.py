from __future__ import annotations

import sys
import warnings
from typing import cast

# Silence a harmless deprecation notice raised inside LangGraph's own imports
warnings.filterwarnings("ignore", message=".*allowed_objects")

from langgraph.graph import END, START, StateGraph  # noqa: E402

from app.agent.assess_risk import assess_risk  # noqa: E402
from app.agent.investigate import investigate  # noqa: E402
from app.agent.memory import recall_memory, save_memory  # noqa: E402
from app.agent.parse import parse_change  # noqa: E402
from app.agent.report import write_noop_report, write_report  # noqa: E402
from app.agent.schemas import ImpactReport  # noqa: E402
from app.agent.state import AgentState, get_change_request  # noqa: E402


def route_after_risk(state: AgentState) -> str:
    """Conditional edge: skip the LLM entirely when the change would not modify anything."""
    return "noop_report" if state.get("is_noop") else "write_report"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("parse_change", parse_change)
    graph.add_node("recall_memory", recall_memory)
    graph.add_node("investigate", investigate)
    graph.add_node("assess_risk", assess_risk)
    graph.add_node("write_report", write_report)
    graph.add_node("noop_report", write_noop_report)
    graph.add_node("save_memory", save_memory)

    graph.add_edge(START, "parse_change")
    graph.add_edge("parse_change", "recall_memory")
    graph.add_edge("recall_memory", "investigate")
    graph.add_edge("investigate", "assess_risk")
    graph.add_conditional_edges(
        "assess_risk",
        route_after_risk,
        {"write_report": "write_report", "noop_report": "noop_report"},
    )
    graph.add_edge("write_report", "save_memory")
    graph.add_edge("noop_report", "save_memory")
    graph.add_edge("save_memory", END)

    return graph.compile()


def to_report(state: AgentState) -> ImpactReport:
    change_request = get_change_request(state)
    risk_level = state.get("risk_level")
    if risk_level is None:
        raise ValueError("assess_risk did not produce a risk_level.")
    return ImpactReport(
        package_name=change_request.package_name,
        action=change_request.action,
        target_version=change_request.target_version,
        risk_level=risk_level,
        risk_reasons=state.get("risk_reasons", []),
        affected_projects=state.get("affected_projects", []),
        narrative=state.get("report", ""),
    )


def run_agent(user_query: str) -> tuple[ImpactReport, AgentState]:
    app = build_graph()
    final_state = cast(AgentState, app.invoke({"user_query": user_query}))
    return to_report(final_state), final_state


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What happens if I upgrade numpy to 3.0.0?"
    report, state = run_agent(query)

    print(f"\n=== Question ===\n{query}")
    print(f"\n=== Parsed ===\n{get_change_request(state)}")
    print(f"\n=== Memory ===\nsimilar past analyses: {len(state.get('memories', []))}   "
          f"saved as record id: {state.get('memory_id')}")
    print(f"\n=== Risk: {report.risk_level.upper()} ===")
    for reason in report.risk_reasons:
        print(f"  - {reason}")
    print(f"\n=== Affected projects ===\n{', '.join(report.affected_projects) or 'none'}")
    print(f"\n=== Report ===\n{report.narrative}\n")