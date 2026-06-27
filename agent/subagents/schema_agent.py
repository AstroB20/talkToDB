import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.state import AgentState
from agent.prompts import build_schema_agent_prompt
from agent.schema_loader import load_all_schemas, format_schema_for_prompt


async def schema_agent_node(state: AgentState) -> dict:
    """
    Answers questions about database structure — tables, columns, relationships.
    Does not call any tools; uses its schema-enriched context to respond directly.
    """
    schemas = load_all_schemas()
    schema_text = format_schema_for_prompt(schemas)
    system_prompt = build_schema_agent_prompt(schema_text)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GEMINI_API_KEY"],
        streaming=True,
    )

    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    user_text = last_human.content if last_human else ""

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_text),
            ]
        )
        reply = response.content
    except Exception as exc:
        reply = f"I couldn't retrieve schema information right now. Error: {exc}"

    return {
        "final_response": reply,
        "messages": [AIMessage(content=reply, name="schema_agent")],
    }
