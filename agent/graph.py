"""
A2A multi-agent graph — Orchestrator + four specialist sub-agents.

Graph topology:
    START → orchestrator → [schema_agent | query_agent | write_agent | END]
                                              ↓
                                         viz_agent → END

The orchestrator classifies intent and sets `next` to route.
query_agent always forwards to viz_agent for formatting.
schema_agent and write_agent respond directly to END.
"""

import os
import sys
from typing import AsyncIterator

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agent.state import AgentState
from agent.subagents.orchestrator import orchestrator_node
from agent.subagents.schema_agent import schema_agent_node
from agent.subagents.query_agent import query_agent_node
from agent.subagents.write_agent import write_agent_node
from agent.subagents.viz_agent import viz_agent_node

load_dotenv()


# ---------------------------------------------------------------------------
# Routing function — reads `next` set by orchestrator
# ---------------------------------------------------------------------------

def _route(state: AgentState) -> str:
    return state.get("next", "__end__")


# ---------------------------------------------------------------------------
# Build the compiled graph (compiled once, reused across requests)
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("schema_agent", schema_agent_node)
    builder.add_node("query_agent", query_agent_node)
    builder.add_node("write_agent", write_agent_node)
    builder.add_node("viz_agent", viz_agent_node)

    # Entry point
    builder.add_edge(START, "orchestrator")

    # Orchestrator routes conditionally
    builder.add_conditional_edges(
        "orchestrator",
        _route,
        {
            "schema_agent": "schema_agent",
            "query_agent":  "query_agent",
            "write_agent":  "write_agent",
            "__end__":      END,
        },
    )

    # query_agent always flows to viz_agent for formatting
    builder.add_edge("query_agent", "viz_agent")

    # Terminal nodes go straight to END
    builder.add_edge("schema_agent", END)
    builder.add_edge("write_agent",  END)
    builder.add_edge("viz_agent",    END)

    return builder.compile()


_graph = _build_graph()


# ---------------------------------------------------------------------------
# Public streaming interface (used by FastAPI)
# ---------------------------------------------------------------------------

async def stream_agent_response(
    user_message: str,
    db_alias: str,
) -> AsyncIterator[dict]:
    """
    Stream typed events from the agent graph.

    Yields dicts with a `type` key:
      - {"type": "node_enter", "node": str}          — an agent node started
      - {"type": "tool_call",  "tool": str, "input": dict}  — a tool was invoked
      - {"type": "tool_result","tool": str, "output": str}  — tool returned
      - {"type": "token",      "text": str}           — a streamed text token
    """
    _USER_FACING_NODES = {"schema_agent", "write_agent", "viz_agent"}
    _ALL_NODES = {"orchestrator", "schema_agent", "query_agent", "write_agent", "viz_agent"}
    _seen_nodes: set[str] = set()

    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_message)],
        "db_alias": db_alias,
        "intent": "",
        "query_results": "",
        "final_response": "",
        "next": "",
    }

    async for event in _graph.astream_events(initial_state, version="v2"):
        event_type = event["event"]
        node = event.get("metadata", {}).get("langgraph_node", "")

        # Emit a node_enter once per node, for all known nodes
        if event_type == "on_chain_start" and node in _ALL_NODES and node not in _seen_nodes:
            _seen_nodes.add(node)
            yield {"type": "node_enter", "node": node}

        # Tool calls — emit for any node (tool calls only happen in query/write agents)
        elif event_type == "on_tool_start" and node:
            tool_name = event.get("name", "")
            tool_input = event.get("data", {}).get("input", {})
            yield {"type": "tool_call", "tool": tool_name, "input": tool_input}

        # Tool results
        elif event_type == "on_tool_end" and node:
            tool_name = event.get("name", "")
            tool_output = event.get("data", {}).get("output", "")
            # output may be a ToolMessage object — get its content string
            if hasattr(tool_output, "content"):
                tool_output = tool_output.content
            yield {"type": "tool_result", "tool": tool_name, "output": str(tool_output)}

        # Streamed tokens — only from user-facing nodes
        elif event_type == "on_chat_model_stream" and node in _USER_FACING_NODES:
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield {"type": "token", "text": chunk.content}
