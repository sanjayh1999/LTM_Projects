import sys

from app.agent.llm import get_llm
from app.agent.schemas import ChangeRequest
from app.agent.state import AgentState

PARSE_SYSTEM_PROMPT = """You extract structured change requests from a sentence describing \
a software dependency change the user wants to make on their own machine.

Rules:
- package_name must be the actual PyPI package name, lowercase, no version numbers.
- action must be exactly one of: upgrade, downgrade, remove, install.
- target_version is the version being moved TO, only if the user stated one explicitly. \
Otherwise leave it null.
- project_hint is the project or environment name the user mentioned, only if stated \
explicitly. Otherwise leave it null.
"""


def parse_change(state: AgentState) -> dict:
    """LangGraph node: turn state['user_query'] into a ChangeRequest."""
    llm = get_llm()
    structured_llm = llm.with_structured_output(ChangeRequest)
    change_request = structured_llm.invoke(
        [
            ("system", PARSE_SYSTEM_PROMPT),
            ("human", state["user_query"]),
        ]
    )
    return {"change_request": change_request}


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "What happens if I upgrade numpy to 2.4.6 in AutoDiag_RAG?"
    result = parse_change({"user_query": query})
    print(f"--- parse_change('{query}') ---")
    print(result["change_request"])