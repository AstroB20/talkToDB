import os

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from agent.state import AgentState
from agent.prompts import build_query_agent_prompt
from agent.schema_loader import load_all_schemas, format_schema_for_prompt
from db.tools import db_read


async def query_agent_node(state: AgentState) -> dict:
    """
    Translates the user's read request into a SELECT query, calls db_read
    directly (no MCP hop), and stores the raw JSON results for the viz_agent.
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
        model="gemini-1.5-flash",
        google_api_key=os.environ["GEMINI_API_KEY"],
    )

    inner_agent = create_react_agent(llm, [db_read], state_modifier=system_prompt)

    result = await inner_agent.ainvoke(
        {"messages": [HumanMessage(content=f"[Target database: {db_alias}]\n\n{user_text}")]}
    )

    last_ai = next(
        (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)),
        None,
    )
    raw_results = last_ai.content if last_ai else "[]"

    return {
        "query_results": raw_results,
        "messages": [AIMessage(content=raw_results, name="query_agent")],
    }
