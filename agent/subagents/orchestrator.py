import json
import os
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.state import AgentState
from agent.prompts import build_orchestrator_prompt
from agent.schema_loader import load_all_schemas, format_schema_for_prompt


# ---------------------------------------------------------------------------
# Keyword fallback — used when the LLM call fails
# ---------------------------------------------------------------------------

_READ_PATTERNS = re.compile(
    r"\b(show|list|find|get|fetch|select|count|how many|how much|average|avg|"
    r"sum|total|top|bottom|max|min|rank|what is|what was|what are|who|which|"
    r"give me|tell me|display|compare|breakdown|distribution|histogram|chart|"
    r"graph|plot|visuali[sz]e)\b",
    re.IGNORECASE,
)
_SCHEMA_PATTERNS = re.compile(
    r"\b(schema|columns?|tables?|fields?|structure|describe|what columns|"
    r"what tables|data types?|available data)\b",
    re.IGNORECASE,
)
_WRITE_PATTERNS = re.compile(
    r"\b(insert|add|create|update|change|modify|edit|delete|remove|drop|"
    r"set|put|write|record)\b",
    re.IGNORECASE,
)


def _keyword_fallback(text: str) -> str:
    """Best-effort intent from keywords when the LLM is unavailable."""
    if _SCHEMA_PATTERNS.search(text):
        return "schema"
    if _WRITE_PATTERNS.search(text):
        return "write"
    if _READ_PATTERNS.search(text):
        return "read"
    return "end"


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def orchestrator_node(state: AgentState) -> dict:
    """
    Classifies the user's intent and sets `next` to route to the correct sub-agent.
    This node's LLM output is internal — not streamed to the user.
    """
    print("[orchestrator] start — loading schemas", flush=True)
    t0 = time.time()
    schemas = load_all_schemas()
    print(f"[orchestrator] schemas loaded in {time.time()-t0:.2f}s: {list(schemas.keys())}", flush=True)
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
    print(f"[orchestrator] calling LLM with user_text={user_text!r}", flush=True)

    intent = "end"
    for attempt in range(2):
        try:
            t1 = time.time()
            response = llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_text),
                ]
            )
            print(f"[orchestrator] LLM responded in {time.time()-t1:.2f}s — raw={response.content!r}", flush=True)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(raw)
            intent = parsed.get("intent", "end")
            break  # success — exit retry loop
        except json.JSONDecodeError as exc:
            print(f"[orchestrator] JSON parse error (attempt {attempt+1}): {exc} — raw={raw!r}", flush=True)
            intent = "end"
            break  # malformed JSON won't improve on retry
        except Exception as exc:
            print(f"[orchestrator] LLM call failed (attempt {attempt+1}): {type(exc).__name__}: {exc}", flush=True)
            if attempt == 1:
                # Both attempts failed — use keyword fallback so the user gets a response
                intent = _keyword_fallback(user_text)
                print(f"[orchestrator] keyword fallback → intent={intent!r}", flush=True)

    intent_to_next = {
        "schema": "schema_agent",
        "read":   "query_agent",
        "write":  "write_agent",
        "end":    "__end__",
    }
    next_node = intent_to_next.get(intent, "__end__")
    print(f"[orchestrator] intent={intent!r} → next={next_node!r}", flush=True)
    return {"intent": intent, "next": next_node}
