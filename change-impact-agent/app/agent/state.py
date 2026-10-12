from typing import Literal, Optional, Required, TypedDict

from app.agent.schemas import ChangeRequest, ImpactFinding

RiskLevel = Literal["low", "medium", "high"]


class AgentState(TypedDict, total=False):
    user_query: Required[str]
    change_request: ChangeRequest
    memories: list[dict]
    findings: list[ImpactFinding]
    affected_projects: list[str]
    project_checks: list[dict]
    scope_note: str
    risk_level: RiskLevel
    risk_reasons: list[str]
    signals: list[str]
    is_noop: bool
    report: str
    memory_id: Optional[int]


def get_change_request(state: AgentState) -> ChangeRequest:
    """Return the parsed change request, or fail clearly if parse_change hasn't run."""
    change_request = state.get("change_request")
    if change_request is None:
        raise ValueError("No change_request in state. parse_change must run before this node.")
    return change_request