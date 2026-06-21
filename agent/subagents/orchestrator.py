import json
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.state import AgentState
from agent.prompts import build_orchestrator_prompt
from agent.schema_loader import load_all_schemas, format_schema_for_prompt


def orchestrator_node(state: AgentState) -> dict:
    """
    Classifies the user's intent and sets `next` to route to the correct sub-agent.
    This node's LLM output is internal — not streamed to the user.
    """
    schemas = load_all_schemas()
    schema_text = format_schema_for_prompt(schemas)
    system_prompt = build_orchestrator_prompt(schema_text)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GEMINI_API_KEY"],
        temperature=0,
    )

    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    user_text = last_human.content if last_human else ""

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_text),
        ]
    )

    raw = response.content.strip()
    # Strip markdown fences if the LLM wrapped the JSON anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(raw)
        intent: str = parsed.get("intent", "end")
    except (json.JSONDecodeError, AttributeError):
        intent = "end"

    intent_to_next = {
        "schema": "schema_agent",
        "read":   "query_agent",
        "write":  "write_agent",
        "end":    "__end__",
    }
    next_node = intent_to_next.get(intent, "__end__")

    return {"intent": intent, "next": next_node}
