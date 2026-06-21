import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.state import AgentState
from agent.prompts import build_viz_agent_prompt


def viz_agent_node(state: AgentState) -> dict:
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

    system_prompt = build_viz_agent_prompt()

    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.environ["GEMINI_API_KEY"],
    )

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"Here are the query results to visualise:\n\n{raw_results}"
            ),
        ]
    )

    reply = response.content
    return {
        "final_response": reply,
        "messages": [AIMessage(content=reply, name="viz_agent")],
    }
