import json
import os

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from agent.state import AgentState
from agent.prompts import build_query_agent_prompt
from agent.schema_loader import load_all_schemas, format_schema_for_prompt
from db.tools import db_read


def _should_visualise(raw_results: str, user_question: str) -> bool:
    """
    Decide if the query results need the viz agent.

    Skip viz when the result is:
    - A single scalar (one row, one column) — e.g. "How many people..."
    - A single row — e.g. "What is the average fare?"
    - An error or empty result
    - The user asked a yes/no or count question

    Let the LLM-based agents handle the nuance, but this provides a fast-path
    heuristic that avoids an unnecessary LLM call for trivial answers.
    """
    try:
        parsed = json.loads(raw_results)
    except (json.JSONDecodeError, ValueError):
        return False  # Not valid JSON — can't visualise

    if not isinstance(parsed, list) or len(parsed) == 0:
        return False

    # Single scalar value (one row, one column) — just report the number
    if len(parsed) == 1 and len(parsed[0]) == 1:
        return False

    # Single row with few columns — a summary answer, not tabular data
    if len(parsed) == 1 and len(parsed[0]) <= 3:
        return False

    # Multiple rows or multiple columns — likely needs formatting/charting
    return True


def _format_scalar_answer(raw_results: str, user_question: str) -> str:
    """
    For simple scalar/summary results, format a clean human-readable sentence
    without needing the viz agent.
    """
    try:
        parsed = json.loads(raw_results)
    except (json.JSONDecodeError, ValueError):
        return raw_results

    if not parsed:
        return "The query returned no results."

    row = parsed[0]

    # Single scalar value — surface the number in a clean sentence
    if len(row) == 1:
        key, value = next(iter(row.items()))
        # Format numbers nicely
        if isinstance(value, float):
            value = f"{value:,.2f}"
        elif isinstance(value, int):
            value = f"{value:,}"
        # Use the column name as context if it's informative, else just the value
        key_clean = key.replace("_", " ").strip()
        if key_clean.lower() in ("count", "count(*)", "total", "num", "n"):
            return f"There are **{value}** matching records."
        return f"**{key_clean}:** {value}"

    # Multiple columns in one row — format as a readable summary list
    parts = []
    for key, value in row.items():
        key_clean = key.replace("_", " ").strip()
        if isinstance(value, float):
            value = f"{value:,.2f}"
        elif isinstance(value, int):
            value = f"{value:,}"
        parts.append(f"**{key_clean}:** {value}")
    return "\n\n".join(parts)


async def query_agent_node(state: AgentState) -> dict:
    """
    Translates the user's read request into a SELECT query, calls db_read
    directly (no MCP hop), and stores the raw JSON results for the viz_agent.
    Decides whether viz_agent is needed based on result shape.
    """
    schemas = load_all_schemas()
    schema_text = format_schema_for_prompt(schemas)
    system_prompt = build_query_agent_prompt(schema_text)

    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    user_text = last_human.content if last_human else ""
    db_alias = state.get("db_alias", "")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GEMINI_API_KEY"],
    )

    inner_agent = create_react_agent(llm, [db_read], prompt=system_prompt)

    try:
        result = await inner_agent.ainvoke(
            {"messages": [HumanMessage(content=f"[Target database: {db_alias}]\n\n{user_text}")]}
        )
    except Exception as exc:
        error_msg = f"Query failed: {exc}"
        return {
            "query_results": "[]",
            "needs_viz": False,
            "final_response": error_msg,
            "messages": [AIMessage(content=error_msg, name="query_agent")],
        }

    messages = result.get("messages", [])

    # Prefer the raw JSON from the last db_read ToolMessage — that is the actual
    # data.  The final AIMessage is only the LLM's narrative summary of results.
    raw_results = "[]"
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.content and msg.content.strip().startswith("["):
            raw_results = msg.content
            break

    # Fall back to the last AIMessage content if no tool result was found
    # (e.g., LLM decided not to call the tool and answered directly)
    if raw_results == "[]":
        last_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)),
            None,
        )
        fallback_content = last_ai.content if last_ai else "[]"
        # If it's not JSON, it's a direct narrative answer — return as-is
        try:
            json.loads(fallback_content)
            raw_results = fallback_content
        except (json.JSONDecodeError, ValueError):
            return {
                "query_results": "[]",
                "needs_viz": False,
                "final_response": fallback_content,
                "messages": [AIMessage(content=fallback_content, name="query_agent")],
            }

    # Decide: does this result need visualisation?
    needs_viz = _should_visualise(raw_results, user_text)

    if needs_viz:
        return {
            "query_results": raw_results,
            "needs_viz": True,
            "messages": [AIMessage(content=raw_results, name="query_agent")],
        }
    else:
        # Simple answer — format it directly without viz agent
        final = _format_scalar_answer(raw_results, user_text)
        return {
            "query_results": raw_results,
            "needs_viz": False,
            "final_response": final,
            "messages": [AIMessage(content=final, name="query_agent")],
        }
