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
import plotly.graph_objects as go
import streamlit as st

_API_BASE = os.environ.get("API_URL", "http://localhost:8000")

# Demo dataset — Titanic from a public GitHub mirror
_DEMO_CSV_URL = "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv"
_DEMO_ALIAS   = "titanic"
_DEMO_QUERIES = [
    "Compare survival rates between men and women across each passenger class.",
    "Which ports did passengers embark from, and how many boarded at each?",
    "What did passengers pay for their tickets — show the full distribution of fares.",
]

# ---------------------------------------------------------------------------
# Agent node display metadata
# ---------------------------------------------------------------------------

_NODE_LABELS = {
    "orchestrator": ("🧭", "Orchestrator", "Classifying intent"),
    "schema_agent": ("📋", "Schema Agent", "Looking up structure"),
    "query_agent":  ("🔍", "Query Agent",  "Writing SQL"),
    "write_agent":  ("✏️",  "Write Agent",  "Modifying data"),
    "viz_agent":    ("📊", "Viz Agent",    "Formatting results"),
}


# ---------------------------------------------------------------------------
# Custom CSS — injected once
# ---------------------------------------------------------------------------

def _inject_css():
    st.markdown("""
    <style>
    /* Tighter chat spacing */
    .stChatMessage { padding: 0.6rem 1rem; }

    /* Sidebar polish */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    section[data-testid="stSidebar"] * {
        color: #e0e0e0 !important;
    }
    section[data-testid="stSidebar"] .stButton>button {
        border: 1px solid #4a4a6a;
        border-radius: 8px;
        transition: all 0.2s ease;
    }
    section[data-testid="stSidebar"] .stButton>button:hover {
        border-color: #7c7cff;
        background: rgba(124, 124, 255, 0.1);
    }

    /* Trace expander styling */
    .streamlit-expanderHeader {
        font-size: 0.85rem;
        color: #888;
    }

    /* Agent status pill during streaming */
    .agent-status {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        background: rgba(124, 124, 255, 0.08);
        border: 1px solid rgba(124, 124, 255, 0.2);
        font-size: 0.85rem;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }

    /* Chart containers */
    .stPlotlyChart {
        border-radius: 12px;
        overflow: hidden;
    }

    /* Dataframe styling */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

_PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=50, b=40),
    font=dict(size=12),
)


def _render_content(content: str) -> None:
    """
    Render agent response. Fenced ```data``` blocks become DataFrames or
    Plotly charts; everything else renders as markdown.
    """
    if not content or not content.strip():
        return

    parts = re.split(r"(```data\n.*?\n```)", content, flags=re.DOTALL)

    for part in parts:
        if part.startswith("```data\n"):
            raw = part[8:-3].strip()
            try:
                block = json.loads(raw)
                data = block.get("data", [])
                if not data:
                    continue

                df = pd.DataFrame(data)
                block_type = block.get("type", "table")
                title = block.get("title", "")

                col_renames = block.get("columns")
                if col_renames and isinstance(col_renames, dict):
                    df = df.rename(columns=col_renames)

                if block_type == "table":
                    st.dataframe(df, use_container_width=True, hide_index=True)

                elif block_type == "chart":
                    chart_type = block.get("chart_type", "bar")
                    # Apply column renames to axis references so they stay in sync
                    x_col     = col_renames.get(block.get("x"), block.get("x")) if col_renames else block.get("x")
                    y_col     = col_renames.get(block.get("y"), block.get("y")) if col_renames else block.get("y")
                    color_col = col_renames.get(block.get("color"), block.get("color")) if col_renames else block.get("color")
                    size_col = block.get("size")
                    nbins = block.get("nbins", 20)

                    fig = None

                    if chart_type == "bar" and x_col and y_col:
                        fig = px.bar(df, x=x_col, y=y_col, color=color_col, title=title)
                    elif chart_type == "bar_h" and x_col and y_col:
                        fig = px.bar(df, x=y_col, y=x_col, color=color_col, orientation="h", title=title)
                    elif chart_type == "stacked_bar" and x_col and y_col:
                        fig = px.bar(df, x=x_col, y=y_col, color=color_col, barmode="stack", title=title)
                    elif chart_type == "grouped_bar" and x_col and y_col:
                        fig = px.bar(df, x=x_col, y=y_col, color=color_col, barmode="group", title=title)
                    elif chart_type == "line" and x_col and y_col:
                        fig = px.line(df, x=x_col, y=y_col, color=color_col, title=title, markers=True)
                    elif chart_type == "area" and x_col and y_col:
                        fig = px.area(df, x=x_col, y=y_col, color=color_col, title=title)
                    elif chart_type == "pie" and x_col and y_col:
                        fig = px.pie(df, names=x_col, values=y_col, title=title, hole=0)
                    elif chart_type == "donut" and x_col and y_col:
                        fig = px.pie(df, names=x_col, values=y_col, title=title, hole=0.45)
                    elif chart_type == "histogram" and x_col:
                        fig = px.histogram(df, x=x_col, nbins=nbins, color=color_col, title=title)
                    elif chart_type == "scatter" and x_col and y_col:
                        fig = px.scatter(
                            df, x=x_col, y=y_col, color=color_col,
                            size=size_col if size_col and size_col in df.columns else None,
                            title=title,
                        )
                    elif chart_type == "box" and x_col and y_col:
                        fig = px.box(df, x=x_col, y=y_col, color=color_col, title=title)
                    elif chart_type == "heatmap":
                        numeric_df = df.set_index(df.columns[0]) if len(df.columns) > 1 else df
                        fig = go.Figure(data=go.Heatmap(
                            z=numeric_df.values,
                            x=list(numeric_df.columns),
                            y=list(numeric_df.index),
                            colorscale="Viridis",
                        ))
                        if title:
                            fig.update_layout(title=title)
                    else:
                        fig = px.bar(df, title=title) if len(df.columns) >= 2 else None

                    if fig:
                        fig.update_layout(**_PLOTLY_LAYOUT)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.dataframe(df, use_container_width=True, hide_index=True)

            except (json.JSONDecodeError, Exception):
                st.markdown(part)
        else:
            if part.strip():
                st.markdown(part)


def _render_profile(db_alias: str) -> None:
    """Fetch and render the dataset profile in the sidebar."""
    try:
        resp = httpx.get(f"{_API_BASE}/profile/{db_alias}", timeout=10)
        resp.raise_for_status()
        profile = resp.json()
    except Exception as exc:
        st.error(f"Profile unavailable: {exc}")
        return

    row_count = profile.get("row_count", 0)
    col_count = profile.get("col_count", 0)
    columns   = profile.get("columns", [])

    st.markdown(f"**{db_alias}** — {row_count:,} rows · {col_count} columns")

    for col in columns:
        name        = col["name"]
        dtype       = col.get("dtype", "")
        null_pct    = col.get("null_pct")
        cardinality = col.get("cardinality")

        # Build a one-line summary string
        parts = [f"`{dtype}`"]
        if null_pct is not None:
            null_str = f"⚠️ {null_pct}% null" if null_pct > 5 else f"{null_pct}% null"
            parts.append(null_str)
        if cardinality is not None:
            parts.append(f"{cardinality:,} unique")

        # Numeric range / stats
        if col.get("mean") is not None:
            lo  = col.get("min")
            hi  = col.get("max")
            avg = col.get("mean")
            parts.append(f"range {_fmt_num(lo)} – {_fmt_num(hi)} · avg {_fmt_num(avg)}")
        elif col.get("min") is not None:
            parts.append(f"{col['min']} → {col['max']}")

        # Top categorical values
        top = col.get("top_values")
        if top:
            parts.append("top: " + ", ".join(f"*{v}*" for v in top[:3]))

        st.caption(f"**{name}** — " + " · ".join(parts))

    if st.button("✕ Close", key="btn_close_profile", use_container_width=True):
        st.session_state._show_profile = False
        st.rerun()


def _fmt_num(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"{f:,.2f}" if f != int(f) else f"{int(f):,}"
    except (TypeError, ValueError):
        return str(v)


def _render_report_view(selected_db: str, db_options: dict) -> None:
    """Full-page report generation UI."""

    if not db_options:
        st.info("Upload a dataset first to generate a report.")
        return

    st.markdown("---")

    focus = st.text_input(
        "Focus topic (optional)",
        placeholder="e.g. 'survival factors' or 'passenger demographics' — leave blank for full analysis",
        key="report_focus",
    )

    col_btn, col_hint = st.columns([2, 5])
    with col_btn:
        start = st.button(
            "▶ Generate Report",
            key="btn_generate_report",
            type="primary",
            use_container_width=True,
            disabled=not selected_db,
        )
    with col_hint:
        st.caption(f"Will run 6 parallel analyses on **{selected_db}** and synthesize findings.")

    # Show cached report if available and dataset hasn't changed
    cached = st.session_state.get("report_result")
    cached_db = st.session_state.get("report_db")

    if start:
        st.session_state.pop("report_result", None)
        with st.spinner("Running 6 analyses in parallel — this takes 20-40 seconds…"):
            try:
                resp = httpx.post(
                    f"{_API_BASE}/report",
                    json={"db_alias": selected_db, "focus": focus},
                    timeout=180.0,
                )
                resp.raise_for_status()
                result = resp.json()
                st.session_state.report_result = result
                st.session_state.report_db = selected_db
                cached = result
                cached_db = selected_db
            except Exception as exc:
                st.error(f"Report failed: {exc}")
                return

    if cached and cached_db == selected_db:
        _render_report_document(cached)


def _render_report_document(report: dict) -> None:
    """Render the structured report document."""
    st.markdown("---")
    st.markdown(f"## {report.get('title', 'Report')}")

    summary = report.get("summary", "")
    if summary:
        st.info(summary)

    sections = report.get("sections", [])
    if not sections:
        st.warning("No sections were generated.")
        return

    for i, section in enumerate(sections, 1):
        question = section.get("question", f"Section {i}")
        content  = section.get("content", "")
        error    = section.get("error", False)

        st.markdown(f"### {i}. {question}")

        if error:
            st.warning(content or "This section could not be generated.")
        elif content.strip():
            _render_content(content)
        else:
            st.caption("No result returned for this section.")

        st.markdown("---")


def _render_trace(trace_events: list[dict]) -> None:
    """Compact trace view inside an expander."""
    for event in trace_events:
        etype = event.get("type")

        if etype == "node_enter":
            node = event["node"]
            emoji, label, _ = _NODE_LABELS.get(node, ("⚙️", node, ""))
            st.caption(f"{emoji} {label}")

        elif etype == "tool_call":
            inp = event.get("input", {})
            query = inp.get("sql_query") or inp.get("query", "")
            if query:
                st.code(query, language="sql")
            else:
                clean = {k: v for k, v in inp.items() if k != "db_alias"}
                if clean:
                    st.json(clean)

        elif etype == "tool_result":
            output = event.get("output", "")
            try:
                parsed = json.loads(output)
                if isinstance(parsed, list) and parsed:
                    df = pd.DataFrame(parsed[:10])  # Show at most 10 rows in trace
                    st.dataframe(df, use_container_width=True, hide_index=True, height=180)
                    if len(parsed) > 10:
                        st.caption(f"… {len(parsed)} rows total")
                else:
                    st.text(str(parsed)[:300])
            except (json.JSONDecodeError, ValueError):
                st.text(output[:300] + ("…" if len(output) > 300 else ""))


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------

def _stream_response(prompt: str, db_alias: str) -> tuple[str, list[dict]]:
    """Stream the agent response. Returns (full_response_text, trace_events)."""

    trace_events: list[dict] = []
    full_response = ""
    _last_render_len = 0
    _UI_RENDER_THRESHOLD = 60

    status_placeholder = st.empty()
    token_placeholder  = st.empty()

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
                        status_placeholder.markdown(
                            f'<div class="agent-status">{emoji} {label} — {desc}</div>',
                            unsafe_allow_html=True,
                        )
                        trace_events.append(event)

                    elif etype == "tool_call":
                        tool = event.get("tool", "")
                        status_placeholder.markdown(
                            f'<div class="agent-status">🔧 Running {tool}</div>',
                            unsafe_allow_html=True,
                        )
                        trace_events.append(event)

                    elif etype == "tool_result":
                        trace_events.append(event)

                    elif etype == "token":
                        full_response += event.get("text", "")
                        if len(full_response) - _last_render_len >= _UI_RENDER_THRESHOLD:
                            token_placeholder.markdown(full_response + " ●")
                            _last_render_len = len(full_response)

                    elif etype == "error":
                        st.error(event.get("message", "Unknown error"))

    except Exception as exc:
        st.error(f"Connection error: {exc}")

    status_placeholder.empty()
    token_placeholder.empty()

    # Show trace in a compact expander
    if trace_events:
        with st.expander("🔍 Agent trace", expanded=False):
            _render_trace(trace_events)

    # Render the final response (or a fallback if empty)
    if full_response.strip():
        _render_content(full_response)
    elif not any(e.get("type") == "error" for e in trace_events):
        st.markdown("*No response generated. Try rephrasing your question.*")

    return full_response, trace_events


# ---------------------------------------------------------------------------
# Page config & layout
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="TalktoDB",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)
_inject_css()

# ---------------------------------------------------------------------------
# Mode toggle — Chat vs Report
# ---------------------------------------------------------------------------

if "app_mode" not in st.session_state:
    st.session_state.app_mode = "chat"

col_title, col_toggle = st.columns([5, 2])
with col_title:
    if st.session_state.app_mode == "chat":
        st.markdown("## 🗄️ TalktoDB")
        st.caption("Ask questions about your data in plain English")
    else:
        st.markdown("## 📑 Report Agent")
        st.caption("Autonomous multi-section analysis — no questions needed")

with col_toggle:
    st.markdown("<br>", unsafe_allow_html=True)
    mode_choice = st.radio(
        "Mode",
        options=["💬 Chat", "📑 Report"],
        index=0 if st.session_state.app_mode == "chat" else 1,
        horizontal=True,
        label_visibility="collapsed",
        key="mode_radio",
    )
    st.session_state.app_mode = "chat" if mode_choice == "💬 Chat" else "report"

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Settings")

    # ── Dataset selector (moved to top — most important) ──────────────────
    try:
        db_resp = httpx.get(f"{_API_BASE}/databases", timeout=5)
        db_resp.raise_for_status()
        databases = db_resp.json()
        db_options = {d["alias"]: f"{d['alias']}  ({d['driver']})" for d in databases}
    except Exception:
        db_options = {}

    if not db_options:
        st.warning("No datasets found — upload one or load the demo.")

    _demo_db = st.session_state.get("demo_db")
    _default_index = 0
    if _demo_db and _demo_db in db_options:
        _default_index = list(db_options.keys()).index(_demo_db)

    selected_db: str = st.selectbox(
        "📂 Active Dataset",
        options=list(db_options.keys()),
        index=_default_index if db_options else 0,
        format_func=lambda k: db_options.get(k, k),
        disabled=not db_options,
    )

    # Role badge
    try:
        health = httpx.get(f"{_API_BASE}/health", timeout=3).json()
        role = health.get("role", "analyst")
        role_colors = {"admin": "🔴", "editor": "🟡", "analyst": "🟢"}
        st.caption(f"{role_colors.get(role, '⚪')} Role: **{role}**")
    except Exception:
        pass

    st.divider()

    # ── Quick actions ─────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📊 Profile", key="btn_profile", disabled=not selected_db, use_container_width=True):
            st.session_state._show_profile = True
            st.session_state._profile_alias = selected_db
    with c2:
        if st.button("🗑️ Clear", key="btn_clear", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    # ── Dataset Profile ───────────────────────────────────────────────────
    if st.session_state.get("_show_profile") and st.session_state.get("_profile_alias") == selected_db:
        _render_profile(selected_db)

    st.divider()

    # ── Demo ──────────────────────────────────────────────────────────────
    if st.button("🚀 Load Demo (Titanic)", key="btn_load_demo", use_container_width=True):
        with st.spinner("Fetching dataset…"):
            try:
                csv_resp = httpx.get(_DEMO_CSV_URL, timeout=30, follow_redirects=True, verify=False)
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

    # ── Upload ────────────────────────────────────────────────────────────
    with st.expander("⬆️ Upload Dataset"):
        uploaded_file = st.file_uploader(
            "CSV or JSON",
            type=["csv", "json"],
            label_visibility="collapsed",
        )
        if uploaded_file is not None:
            if st.button("Upload", key="btn_upload", use_container_width=True):
                try:
                    resp = httpx.post(
                        f"{_API_BASE}/upload",
                        files={"file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type or "application/octet-stream",
                        )},
                        timeout=30,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    st.success(f"✅ **{result['alias']}** ready")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")

    st.divider()

    # ── Audit ─────────────────────────────────────────────────────────────
    with st.expander("📜 Audit Log"):
        try:
            audit_resp = httpx.get(f"{_API_BASE}/audit?limit=20", timeout=5)
            audit_resp.raise_for_status()
            entries = audit_resp.json()
            if entries:
                st.dataframe(
                    pd.DataFrame(entries)[["timestamp", "operation", "db_alias", "success"]],
                    use_container_width=True,
                    hide_index=True,
                    height=200,
                )
            else:
                st.caption("No entries yet.")
        except Exception:
            st.caption("Unavailable")

# ---------------------------------------------------------------------------
# Chat view
# ---------------------------------------------------------------------------

if st.session_state.app_mode == "chat":

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                trace = msg.get("trace", [])
                if trace:
                    with st.expander("🔍 Agent trace", expanded=False):
                        _render_trace(trace)
            _render_content(msg["content"])

    # Auto-run demo queries
    if st.session_state.get("demo_queries") and selected_db == _DEMO_ALIAS:
        next_query = st.session_state.demo_queries.pop(0)
        if not st.session_state.demo_queries:
            st.session_state.pop("demo_db", None)
            st.session_state.pop("demo_queries", None)

        st.session_state.messages.append({"role": "user", "content": next_query})
        with st.chat_message("user"):
            st.markdown(next_query)
        with st.chat_message("assistant"):
            reply, trace = _stream_response(next_query, selected_db)
        st.session_state.messages.append({"role": "assistant", "content": reply, "trace": trace})

        if st.session_state.get("demo_queries"):
            st.rerun()

    if prompt := st.chat_input("Ask about your data…", disabled=not db_options):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            reply, trace = _stream_response(prompt, selected_db)
        st.session_state.messages.append({"role": "assistant", "content": reply, "trace": trace})


# ---------------------------------------------------------------------------
# Report view
# ---------------------------------------------------------------------------

else:
    _render_report_view(selected_db, db_options)
