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
# Streaming helper — shared by chat input and auto-demo runner
# ---------------------------------------------------------------------------

def _stream_response(prompt: str, db_alias: str) -> str:
    """Send a chat message to the API and stream the response into the UI.
    Returns the full accumulated response text."""
    placeholder = st.empty()
    full_response = ""

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
                        if "token" in event:
                            full_response += event["token"]
                            placeholder.markdown(full_response + "▌")
                        elif "error" in event:
                            st.error(event["error"])
                    except json.JSONDecodeError:
                        pass
    except Exception as exc:
        st.error(f"Connection error: {exc}")

    placeholder.empty()
    _render_content(full_response)
    return full_response


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
        if st.button("🚀 Load Demo", use_container_width=True):
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
        if st.button("⬆️ Upload"):
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
    if st.button("🔍 View Schema", disabled=not selected_db):
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
    if st.button("📜 View Audit Log"):
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
    if st.button("🗑️ Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
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
        reply = _stream_response(next_query, selected_db)
    st.session_state.messages.append({"role": "assistant", "content": reply})

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
        reply = _stream_response(prompt, selected_db)
    st.session_state.messages.append({"role": "assistant", "content": reply})
