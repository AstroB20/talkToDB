"""
A2A multi-agent graph — Orchestrator + four specialist sub-agents.

Graph topology:
    START → orchestrator → [schema_agent | query_agent | write_agent | END]
                                              ↓ (conditional)
                                     [viz_agent | END]

The orchestrator classifies intent and sets `next` to route.
query_agent conditionally forwards to viz_agent only when results need
visual formatting (charts, tables). Simple scalar answers skip viz entirely.
schema_agent and write_agent respond directly to END.
"""

import asyncio
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

_STREAM_TIMEOUT_SECONDS = 120


def _validate_env() -> None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Add it to your .env file or environment before starting the server."
        )


_validate_env()


# ---------------------------------------------------------------------------
# Routing function — reads `next` set by orchestrator
# ---------------------------------------------------------------------------

def _route(state: AgentState) -> str:
    return state.get("next", "__end__")


def _route_after_query(state: AgentState) -> str:
    """Route after query_agent: go to viz_agent only if the agent says it's needed."""
    if state.get("needs_viz", True):
        return "viz_agent"
    return "__end__"


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

    # query_agent conditionally flows to viz_agent or straight to END
    builder.add_conditional_edges(
        "query_agent",
        _route_after_query,
        {
            "viz_agent": "viz_agent",
            "__end__":   END,
        },
    )

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
    _USER_FACING_NODES = {"schema_agent", "query_agent", "write_agent", "viz_agent"}
    _ALL_NODES = {"orchestrator", "schema_agent", "query_agent", "write_agent", "viz_agent"}
    _seen_nodes: set[str] = set()

    print(f"[graph] stream_agent_response called — db_alias={db_alias!r} message={user_message!r}", flush=True)

    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_message)],
        "db_alias": db_alias,
        "user_question": user_message,
        "intent": "",
        "query_results": "",
        "needs_viz": True,
        "final_response": "",
        "next": "",
    }

    async def _stream():
        token_buffer = ""
        _TOKEN_FLUSH_SIZE = 20
        # Track which terminal nodes have already emitted tokens via streaming.
        # If a node finishes without any tokens (short responses, sync invoke),
        # we fall back to final_response from the on_chain_end state update.
        _nodes_with_tokens: set[str] = set()

        async for event in _graph.astream_events(initial_state, version="v2"):
            event_type = event["event"]
            node = event.get("metadata", {}).get("langgraph_node", "")

            # Emit a node_enter once per node, for all known nodes
            if event_type == "on_chain_start" and node in _ALL_NODES and node not in _seen_nodes:
                if token_buffer:
                    yield {"type": "token", "text": token_buffer}
                    token_buffer = ""
                _seen_nodes.add(node)
                yield {"type": "node_enter", "node": node}

            # Tool calls
            elif event_type == "on_tool_start" and node:
                if token_buffer:
                    yield {"type": "token", "text": token_buffer}
                    token_buffer = ""
                tool_name = event.get("name", "")
                tool_input = event.get("data", {}).get("input", {})
                yield {"type": "tool_call", "tool": tool_name, "input": tool_input}

            # Tool results
            elif event_type == "on_tool_end" and node:
                if token_buffer:
                    yield {"type": "token", "text": token_buffer}
                    token_buffer = ""
                tool_name = event.get("name", "")
                tool_output = event.get("data", {}).get("output", "")
                if hasattr(tool_output, "content"):
                    tool_output = tool_output.content
                yield {"type": "tool_result", "tool": tool_name, "output": str(tool_output)}

            # Streamed tokens — buffer and flush in chunks
            elif event_type == "on_chat_model_stream" and node in _USER_FACING_NODES:
                chunk = event["data"]["chunk"]
                if chunk.content:
                    token_buffer += chunk.content
                    _nodes_with_tokens.add(node)
                    if len(token_buffer) >= _TOKEN_FLUSH_SIZE:
                        yield {"type": "token", "text": token_buffer}
                        token_buffer = ""

            # Fallback: when a terminal node finishes, grab final_response from
            # its output if no tokens were streamed for it (e.g. sync invoke on
            # a short response didn't emit on_chat_model_stream events).
            elif event_type == "on_chain_end" and node in _USER_FACING_NODES:
                if token_buffer:
                    yield {"type": "token", "text": token_buffer}
                    token_buffer = ""
                if node not in _nodes_with_tokens:
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        final = output.get("final_response", "")
                        if final:
                            yield {"type": "token", "text": final}

        # Flush any remaining tokens at end of stream
        if token_buffer:
            yield {"type": "token", "text": token_buffer}

    try:
        async with asyncio.timeout(_STREAM_TIMEOUT_SECONDS):
            async for event in _stream():
                yield event
    except asyncio.TimeoutError:
        yield {"type": "error", "message": f"Request timed out after {_STREAM_TIMEOUT_SECONDS}s."}
