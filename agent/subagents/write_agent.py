import os

from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

from agent.state import AgentState
from agent.prompts import build_write_agent_prompt
from agent.schema_loader import load_all_schemas, format_schema_for_prompt
from db.tools import db_create, db_update, db_delete


async def write_agent_node(state: AgentState) -> dict:
    """
    Handles INSERT / UPDATE / DELETE operations using direct Python tools.
    Role-based permission checks are enforced inside each tool function.
    """
    schemas = load_all_schemas()
    schema_text = format_schema_for_prompt(schemas)
    system_prompt = build_write_agent_prompt(schema_text)

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

    inner_agent = create_react_agent(
        llm, [db_create, db_update, db_delete], prompt=system_prompt
    )

    result = await inner_agent.ainvoke(
        {"messages": [HumanMessage(content=f"[Target database: {db_alias}]\n\n{user_text}")]}
    )

    last_ai = next(
        (m for m in reversed(result["messages"]) if isinstance(m, AIMessage)),
        None,
    )
    reply = last_ai.content if last_ai else "Operation completed."

    return {
        "final_response": reply,
        "messages": [AIMessage(content=reply, name="write_agent")],
    }
