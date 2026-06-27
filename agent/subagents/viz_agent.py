import json
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.state import AgentState
from agent.prompts import build_viz_agent_prompt


async def viz_agent_node(state: AgentState) -> dict:
    """
    Receives raw query results from query_agent and formats them for the UI.
    Decides automatically between table, bar chart, line chart, or pie chart
    based on the data shape, then writes a plain-English summary.
    """
    raw_results = state.get("query_results", "[]")

    if not raw_results or raw_results.strip() in ("[]", ""):
        reply = "The query returned no results."
        return {
            "final_response": reply,
            "messages": [AIMessage(content=reply, name="viz_agent")],
        }

    # If query_results isn't valid JSON (e.g. the query_agent returned an error
    # message or the LLM explained it couldn't run the query), pass it through
    # directly rather than asking the viz LLM to format garbage.
    try:
        parsed = json.loads(raw_results)
        if not isinstance(parsed, list) or len(parsed) == 0:
            reply = "The query returned no results."
            return {
                "final_response": reply,
                "messages": [AIMessage(content=reply, name="viz_agent")],
            }
    except (json.JSONDecodeError, ValueError):
        # Not JSON — likely a descriptive answer from query_agent; return as-is
        return {
            "final_response": raw_results,
            "messages": [AIMessage(content=raw_results, name="viz_agent")],
        }

    system_prompt = build_viz_agent_prompt()

    # Include the user's original question so the viz LLM understands context
    user_question = state.get("user_question", "")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GEMINI_API_KEY"],
        streaming=True,
    )

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=(
                        f"## User's original question\n{user_question}\n\n"
                        f"## Raw query results\n{raw_results}"
                    )
                ),
            ]
        )
        reply = response.content
    except Exception as exc:
        reply = f"Could not format results: {exc}"

    return {
        "final_response": reply,
        "messages": [AIMessage(content=reply, name="viz_agent")],
    }
