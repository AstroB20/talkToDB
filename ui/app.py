"""
Streamlit chat UI for TalktoDB.

How to run:
    streamlit run ui/app.py
"""

import json
import os
import re

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

_API_BASE = os.environ.get("API_URL", "http://localhost:8000")

# Demo dataset — Titanic from a public GitHub mirror
_DEMO_CSV_URL = "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv"
_DEMO_ALIAS   = "titanic"
_DEMO_QUERIES = [
    "Show me the number of survivors vs non-survivors broken down by passenger class as a bar chart.",
    "What is the average fare paid by passengers in each class?",
    "List the top 10 youngest passengers who survived.",
]

# ---------------------------------------------------------------------------
# Agent node display metadata
# ---------------------------------------------------------------------------

_NODE_LABELS = {
    "orchestrator": ("🧭", "Orchestrator", "Classifying your intent and routing to the right agent"),
    "schema_agent": ("📋", "Schema Agent", "Looking up database structure"),
    "query_agent":  ("🔍", "Query Agent",  "Translating your question into a SQL query"),
    "write_agent":  ("✏️",  "Write Agent",  "Preparing a data modification"),
    "viz_agent":    ("📊", "Viz Agent",    "Formatting results into a chart or table"),
}


# ---------------------------------------------------------------------------
# Streaming helper — shared by chat input and auto-demo runner
# ---------------------------------------------------------------------------

def _stream_response(prompt: str, db_alias: str) -> tuple[str, list[dict]]:
    """Send a chat message to the API and stream the response into the UI.
    Renders a collapsible trace of every agent step, then the final answer.
    Returns (full_response_text, trace_events)."""

    # --- Accumulators -------------------------------------------------------
    trace_events: list[dict] = []   # all non-token events, for replay in expander
    full_response = ""

    # --- Live placeholders --------------------------------------------------
    status_placeholder = st.empty()   # "Agent is thinking…" spinner text
    token_placeholder  = st.empty()   # streaming token preview

    try:
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{_API_BASE}/chat",
                json={"message": prompt, "db_alias": db_alias},
                headers={"Accept": "text/event-stream"},
            ) as stream:
                for line in stream.iter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get("type")

                    if etype == "node_enter":
                        node = event["node"]
                        emoji, label, desc = _NODE_LABELS.get(node, ("⚙️", node, ""))
                        status_placeholder.markdown(f"{emoji} **{label}** — {desc}…")
                        trace_events.append(event)

                    elif etype == "tool_call":
                        tool = event.get("tool", "")
                        status_placeholder.markdown(f"🔧 Calling **{tool}**…")
                        trace_events.append(event)

                    elif etype == "tool_result":
                        trace_events.append(event)

                    elif etype == "token":
                        full_response += event.get("text", "")
                        token_placeholder.markdown(full_response + "▌")

                    elif etype == "error":
                        st.error(event.get("message", "Unknown error"))

    except Exception as exc:
        st.error(f"Connection error: {exc}")

    # --- Clear live placeholders -------------------------------------------
    status_placeholder.empty()
    token_placeholder.empty()

    # --- Render trace in an expander ---------------------------------------
    if trace_events:
        with st.expander("🔍 How I got this answer", expanded=False):
            _render_trace(trace_events)

    # --- Render final response --------------------------------------------
    _render_content(full_response)
    return full_response, trace_events


def _render_trace(trace_events: list[dict]) -> None:
    """Render the agent execution trace inside an expander."""
    for event in trace_events:
        etype = event.get("type")

        if etype == "node_enter":
            node = event["node"]
            emoji, label, desc = _NODE_LABELS.get(node, ("⚙️", node, ""))
            st.markdown(f"**{emoji} {label}** — *{desc}*")

        elif etype == "tool_call":
            tool  = event.get("tool", "")
            inp   = event.get("input", {})
            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🔧 **Tool called:** `{tool}`")
            # Show relevant input fields — skip db_alias noise, highlight query
            query = inp.get("sql_query") or inp.get("query", "")
            if query:
                st.code(query, language="sql")
            else:
                clean = {k: v for k, v in inp.items() if k != "db_alias"}
                if clean:
                    st.json(clean)

        elif etype == "tool_result":
            tool   = event.get("tool", "")
            output = event.get("output", "")
            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;✅ **`{tool}` returned:**")
            # Try to pretty-print JSON results, otherwise just show text
            try:
                parsed = json.loads(output)
                if isinstance(parsed, list) and parsed:
                    df = pd.DataFrame(parsed)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.json(parsed)
            except (json.JSONDecodeError, ValueError):
                st.text(output[:500] + ("…" if len(output) > 500 else ""))

        st.markdown("---")


# ---------------------------------------------------------------------------
# Rendering helper — defined before the chat loop uses it
# ---------------------------------------------------------------------------

def _render_content(content: str) -> None:
    """
    Render agent response text. Fenced ```data``` blocks are parsed and
    displayed as Streamlit DataFrames or Plotly charts.
    All other text is rendered as markdown.
    """
    # Split on data blocks, keeping the delimiters as separate elements
    parts = re.split(r"(```data\n.*?\n```)", content, flags=re.DOTALL)

    for part in parts:
        if part.startswith("```data\n"):
            raw = part[8:-3].strip()  # strip the fence markers
            try:
                block = json.loads(raw)
                data = block.get("data", [])
                if not data:
                    continue

                df = pd.DataFrame(data)
                block_type = block.get("type", "table")

                if block_type == "table":
                    st.dataframe(df, use_container_width=True)

                elif block_type == "chart":
                    chart_type = block.get("chart_type", "bar")
                    x_col = block.get("x")
                    y_col = block.get("y")

                    if chart_type == "bar" and x_col and y_col:
                        fig = px.bar(df, x=x_col, y=y_col)
                    elif chart_type == "line" and x_col and y_col:
                        fig = px.line(df, x=x_col, y=y_col)
                    elif chart_type == "pie" and x_col and y_col:
                        fig = px.pie(df, names=x_col, values=y_col)
                    else:
                        fig = px.bar(df)

                    st.plotly_chart(fig, use_container_width=True)

            except (json.JSONDecodeError, Exception):
                st.markdown(part)  # fallback: render raw as markdown
        else:
            if part.strip():
                st.markdown(part)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="TalktoDB", page_icon="🗄️", layout="wide")
st.title("🗄️ TalktoDB")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    # ── Demo ───────────────────────────────────────────────────────────────
    with st.expander("▶ Try the Demo", expanded=False):
        st.caption(
            "Loads the **Titanic** dataset from GitHub and runs three "
            "example queries so you can see the agent in action."
        )
        if st.button("🚀 Load Demo", use_container_width=True, key="load_demo"):
            with st.spinner("Downloading Titanic dataset..."):
                try:
                    csv_resp = httpx.get(_DEMO_CSV_URL, timeout=30, follow_redirects=True)
                    csv_resp.raise_for_status()
                    upload_resp = httpx.post(
                        f"{_API_BASE}/upload",
                        files={"file": (f"{_DEMO_ALIAS}.csv", csv_resp.content, "text/csv")},
                        timeout=30,
                    )
                    upload_resp.raise_for_status()
                    st.session_state.messages = []
                    st.session_state.demo_db = _DEMO_ALIAS
                    st.session_state.demo_queries = list(_DEMO_QUERIES)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Demo failed: {exc}")

    st.divider()

    # ── Upload Dataset ─────────────────────────────────────────────────────
    st.subheader("Upload Dataset")
    uploaded_file = st.file_uploader(
        "Drop a CSV or JSON file (e.g. from Kaggle)",
        type=["csv", "json"],
        label_visibility="collapsed",
    )
    if uploaded_file is not None:
        if st.button("⬆️ Upload", key="upload"):
            try:
                resp = httpx.post(
                    f"{_API_BASE}/upload",
                    files={
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type or "application/octet-stream",
                        )
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()
                st.success(f"✅ Uploaded as alias **'{result['alias']}'**")
                st.rerun()
            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    st.divider()

    # ── Dataset selector ───────────────────────────────────────────────────
    # Fetch dataset list from the API
    try:
        db_resp = httpx.get(f"{_API_BASE}/databases", timeout=5)
        db_resp.raise_for_status()
        databases = db_resp.json()
        db_options = {d["alias"]: f"{d['alias']}  ({d['driver']})" for d in databases}
    except Exception:
        db_options = {}
        st.error("⚠️ Cannot reach the API server. Is it running on port 8000?")

    # Pre-select the demo dataset if the demo was just loaded
    _demo_db = st.session_state.get("demo_db")
    _default_index = 0
    if _demo_db and _demo_db in db_options:
        _default_index = list(db_options.keys()).index(_demo_db)

    selected_db: str = st.selectbox(
        "Target Dataset",
        options=list(db_options.keys()),
        index=_default_index,
        format_func=lambda k: db_options.get(k, k),
        disabled=not db_options,
    )

    # Show current role
    try:
        health = httpx.get(f"{_API_BASE}/health", timeout=3).json()
        st.info(f"Role: **{health.get('role', 'unknown')}**")
    except Exception:
        pass

    st.divider()

    # Schema inspector
    if st.button("🔍 View Schema", disabled=not selected_db, key="view_schema"):
        try:
            schema_resp = httpx.get(f"{_API_BASE}/schema/{selected_db}", timeout=5)
            schema_resp.raise_for_status()
            schema = schema_resp.json().get("schema", {})
            for table, cols in schema.items():
                with st.expander(f"📋 {table}"):
                    for col in cols:
                        st.text(f"  • {col}")
        except Exception as exc:
            st.error(str(exc))

    # Audit log viewer
    if st.button("📜 View Audit Log", key="view_audit_log"):
        try:
            audit_resp = httpx.get(f"{_API_BASE}/audit?limit=100", timeout=5)
            audit_resp.raise_for_status()
            entries = audit_resp.json()
            if entries:
                st.dataframe(pd.DataFrame(entries), use_container_width=True)
            else:
                st.info("No audit entries yet.")
        except Exception as exc:
            st.error(str(exc))

    # Clear chat history
    if st.button("🗑️ Clear Chat", key="clear_chat"):
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            trace = msg.get("trace", [])
            if trace:
                with st.expander("🔍 How I got this answer", expanded=False):
                    _render_trace(trace)
        _render_content(msg["content"])

# ---------------------------------------------------------------------------
# Auto-run demo queries (fires once per query after demo is loaded)
# ---------------------------------------------------------------------------

if st.session_state.get("demo_queries") and selected_db == _DEMO_ALIAS:
    next_query = st.session_state.demo_queries.pop(0)
    if not st.session_state.demo_queries:
        # All demo queries consumed — clean up demo state
        st.session_state.pop("demo_db", None)
        st.session_state.pop("demo_queries", None)

    st.session_state.messages.append({"role": "user", "content": next_query})
    with st.chat_message("user"):
        st.markdown(next_query)
    with st.chat_message("assistant"):
        reply, trace = _stream_response(next_query, selected_db)
    st.session_state.messages.append({"role": "assistant", "content": reply, "trace": trace})

    # Pause briefly so Streamlit renders each message before firing the next
    if st.session_state.get("demo_queries"):
        st.rerun()

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input(
    "Ask about your data...", disabled=not db_options
):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        reply, trace = _stream_response(prompt, selected_db)
    st.session_state.messages.append({"role": "assistant", "content": reply, "trace": trace})


# ---------------------------------------------------------------------------
# Rendering helper — defined before the chat loop uses it
# ---------------------------------------------------------------------------

def _render_content(content: str) -> None:
    """
    Render agent response text. Fenced ```data``` blocks are parsed and
    displayed as Streamlit DataFrames or Plotly charts.
    All other text is rendered as markdown.
    """
    # Split on data blocks, keeping the delimiters as separate elements
    parts = re.split(r"(```data\n.*?\n```)", content, flags=re.DOTALL)

    for part in parts:
        if part.startswith("```data\n"):
            raw = part[8:-3].strip()  # strip the fence markers
            try:
                block = json.loads(raw)
                data = block.get("data", [])
                if not data:
                    continue

                df = pd.DataFrame(data)
                block_type = block.get("type", "table")

                if block_type == "table":
                    st.dataframe(df, use_container_width=True)

                elif block_type == "chart":
                    chart_type = block.get("chart_type", "bar")
                    x_col = block.get("x")
                    y_col = block.get("y")

                    if chart_type == "bar" and x_col and y_col:
                        fig = px.bar(df, x=x_col, y=y_col)
                    elif chart_type == "line" and x_col and y_col:
                        fig = px.line(df, x=x_col, y=y_col)
                    elif chart_type == "pie" and x_col and y_col:
                        fig = px.pie(df, names=x_col, values=y_col)
                    else:
                        fig = px.bar(df)

                    st.plotly_chart(fig, use_container_width=True)

            except (json.JSONDecodeError, Exception):
                st.markdown(part)  # fallback: render raw as markdown
        else:
            if part.strip():
                st.markdown(part)

