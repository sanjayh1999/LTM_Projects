from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChangeRequest(BaseModel):
    """Structured form of a natural-language change request."""

    package_name: str = Field(
        description="The name of the package being changed, e.g. 'numpy'. "
        "Always lowercase, no version info."
    )
    action: Literal["upgrade", "downgrade", "remove", "install"] = Field(
        description="What kind of change the user wants to make."
    )
    target_version: Optional[str] = Field(
        default=None,
        description="The version being moved to, if the user mentioned one, "
        "e.g. '2.4.6'. Use null if no version was mentioned.",
    )
    project_hint: Optional[str] = Field(
        default=None,
        description="The project or environment name the user mentioned, if any, "
        "e.g. 'AutoDiag_RAG'. Use null if the user didn't name one.",
    )


class ImpactFinding(BaseModel):
    """One concrete fact the agent gathered while investigating the change."""

    source: Literal["inventory", "graph", "evidence", "compatibility"]
    text: str


class ImpactReport(BaseModel):
    """Final output of the agent for a single change request."""

    package_name: str
    action: str
    target_version: Optional[str] = None
    risk_level: Literal["low", "medium", "high"]
    risk_reasons: list[str]
    affected_projects: list[str]
    narrative: str