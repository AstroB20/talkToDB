"""
Report Agent — autonomous multi-section analysis of a dataset.

Workflow:
  1. Decompose: LLM generates 5-7 focused sub-questions from schema + optional focus topic
  2. Fan-out:   all sub-questions run in parallel via asyncio.gather
               (each goes query_agent → viz_agent through the existing node functions)
  3. Synthesize: LLM writes an executive summary connecting all findings
  4. Return:   structured report with sections + summary
"""

import asyncio
import json
import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.state import AgentState
from agent.schema_loader import load_all_schemas, format_schema_for_prompt
from agent.subagents.query_agent import query_agent_node
from agent.subagents.viz_agent import viz_agent_node


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_decompose_prompt(schema_text: str, focus: str) -> str:
    focus_clause = f"\n\nThe user wants to focus on: **{focus}**" if focus.strip() else ""
    return f"""You are a data analyst planning a comprehensive report on a dataset.{focus_clause}

## Dataset Schema
{schema_text}

## Your job
Generate exactly 6 focused analytical sub-questions about this dataset that together form a complete analysis.

Rules:
- Each question must be answerable with a SELECT query against the schema above
- Use only columns that actually exist in the schema
- Mix question types: distributions, comparisons, rankings, breakdowns, correlations
- Questions should complement each other — avoid duplicates or near-duplicates
- Prefer questions that will produce interesting charts (multi-row results)
- If a focus topic is given, weight questions toward that topic but still cover the dataset broadly

Respond with ONLY a JSON array of strings — no extra text:
["question 1", "question 2", "question 3", "question 4", "question 5", "question 6"]
"""


def _build_synthesize_prompt() -> str:
    return """You are a data analyst writing an executive summary for a report.

You will receive a list of findings — each is a question paired with the answer/chart description.

Write a concise executive summary (3-5 sentences) that:
- Identifies the most important patterns or insights across ALL findings
- Connects related findings to tell a coherent story
- Calls out any surprising or counterintuitive results
- Uses specific numbers from the findings where relevant

Write in plain prose. No bullet points. No headers. No markdown formatting beyond bold for key numbers.
"""


# ---------------------------------------------------------------------------
# Sub-question runner — query + viz for a single question
# ---------------------------------------------------------------------------

async def _run_sub_question(question: str, db_alias: str) -> dict:
    """
    Run a single sub-question through query_agent → viz_agent.
    Returns {"question": str, "content": str, "error": bool}
    """
    base_state: AgentState = {
        "messages":     [HumanMessage(content=question)],
        "db_alias":     db_alias,
        "user_question": question,
        "intent":       "read",
        "query_results": "",
        "needs_viz":    True,
        "final_response": "",
        "next":         "query_agent",
    }

    try:
        query_output = await query_agent_node(base_state)

        # Merge query output into state for viz
        merged: AgentState = {**base_state, **query_output}

        if query_output.get("needs_viz", False):
            viz_output = await viz_agent_node(merged)
            content = viz_output.get("final_response", "")
        else:
            content = query_output.get("final_response", "")

        return {"question": question, "content": content, "error": False}

    except Exception as exc:
        return {"question": question, "content": f"Could not answer: {exc}", "error": True}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_report(db_alias: str, focus: str = "") -> dict:
    """
    Generate a full multi-section report for a dataset.

    Args:
        db_alias: Dataset to analyse.
        focus:    Optional topic to focus the analysis on (empty = full analysis).

    Returns:
        {
          "title": str,
          "focus": str,
          "summary": str,
          "sections": [{"question": str, "content": str, "error": bool}, ...]
        }
    """
    schemas = load_all_schemas()
    schema_text = format_schema_for_prompt(schemas)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GEMINI_API_KEY"],
        temperature=0.3,
    )

    # Step 1 — decompose into sub-questions
    decompose_resp = await llm.ainvoke([
        SystemMessage(content=_build_decompose_prompt(schema_text, focus)),
        HumanMessage(content=f"Generate 6 sub-questions for dataset: {db_alias}"),
    ])
    raw = decompose_resp.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        questions: list[str] = json.loads(raw)
        if not isinstance(questions, list):
            raise ValueError("Expected a JSON array")
        questions = [q for q in questions if isinstance(q, str) and q.strip()][:7]
    except Exception:
        # Fallback: extract quoted strings if JSON parse failed
        import re
        questions = re.findall(r'"([^"]{10,})"', raw)[:6]

    if not questions:
        return {
            "title": f"Report: {db_alias}",
            "focus": focus,
            "summary": "Could not generate sub-questions for this dataset.",
            "sections": [],
        }

    # Step 2 — run all sub-questions in parallel
    tasks = [_run_sub_question(q, db_alias) for q in questions]
    sections: list[dict] = await asyncio.gather(*tasks)

    # Step 3 — synthesize executive summary from successful findings
    successful = [s for s in sections if not s["error"] and s["content"].strip()]
    summary = ""
    if successful:
        findings_text = "\n\n".join(
            f"Q: {s['question']}\nA: {s['content'][:500]}"  # truncate for context
            for s in successful
        )
        try:
            synth_resp = await llm.ainvoke([
                SystemMessage(content=_build_synthesize_prompt()),
                HumanMessage(content=findings_text),
            ])
            summary = synth_resp.content.strip()
        except Exception as exc:
            summary = f"Summary unavailable: {exc}"

    title = f"Analysis: {db_alias}" + (f" — {focus}" if focus.strip() else "")

    return {
        "title": title,
        "focus": focus,
        "summary": summary,
        "sections": list(sections),
    }
