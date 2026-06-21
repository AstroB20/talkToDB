from typing import Annotated, Literal
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # Full conversation history — LangGraph merges via add_messages reducer
    messages: Annotated[list, add_messages]

    # The database alias chosen in the UI
    db_alias: str

    # Orchestrator sets this to route to the right sub-agent
    # "schema" | "read" | "write" | "end"
    intent: str

    # Raw JSON string of query results; set by query_agent, consumed by viz_agent
    query_results: str

    # Final rendered response assembled by the terminal agent (schema/write/viz)
    final_response: str

    # Which node to go to next — used by conditional_edge routing
    next: Literal["schema_agent", "query_agent", "write_agent", "__end__"]
