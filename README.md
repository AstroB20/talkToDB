<p align="center">
  <img src="https://img.shields.io/badge/LangGraph-Multi--Agent-blueviolet?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiPjxjaXJjbGUgY3g9IjEyIiBjeT0iNSIgcj0iMyIvPjxjaXJjbGUgY3g9IjUiIGN5PSIxOSIgcj0iMyIvPjxjaXJjbGUgY3g9IjE5IiBjeT0iMTkiIHI9IjMiLz48bGluZSB4MT0iMTIiIHkxPSI4IiB4Mj0iNSIgeTI9IjE2Ii8+PGxpbmUgeDE9IjEyIiB5MT0iOCIgeDI9IjE5IiB5Mj0iMTYiLz48L3N2Zz4=" alt="LangGraph Multi-Agent"/>
  <img src="https://img.shields.io/badge/Gemini_2.5_Flash-LLM-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini 2.5 Flash"/>
  <img src="https://img.shields.io/badge/DuckDB-Queries-FFC107?style=for-the-badge&logo=duckdb&logoColor=black" alt="DuckDB"/>
  <img src="https://img.shields.io/badge/Streamlit-UI-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit"/>
</p>

<h1 align="center">🗣️ TalktoDB</h1>

<p align="center">
  <strong>Talk to your data in plain English.</strong><br/>
  A multi-agent system that translates natural language into SQL, executes it, and presents results as prose, tables, or interactive charts — automatically.
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#features">Features</a> •
  <a href="#smart-visualisation">Visualisation</a> •
  <a href="#api-reference">API</a> •
  <a href="#deployment">Deploy</a>
</p>

---

## Demo

> **"Show me survival rate by passenger class as a bar chart"**

The system routes through five coordinated agents:

```
Orchestrator → intent: read → Query Agent → SQL → DuckDB → Viz Agent → Plotly bar chart
```

No configuration. No manual SQL. Just drop a CSV and ask questions.

---

## Features

| Category | What you get |
|----------|-------------|
| 🧠 **Natural Language → SQL** | Powered by Gemini 2.5 Flash via LangGraph's multi-agent orchestration |
| 📑 **Report Agent** | One click generates a full multi-section analysis — 6 parallel sub-questions, auto-visualised, with an executive summary |
| 📊 **Smart Visualisation** | Auto-selects from 12 chart types based on data shape alone — no hints needed |
| 🔬 **Dataset Profiler** | Instant column-level stats on upload: types, null rates, ranges, top values |
| 📁 **Zero-Config Data** | Drop any `.csv` or `.json` into `data/` — instantly queryable, no setup |
| ⚡ **Real-Time Streaming** | Tokens stream agent → FastAPI (SSE) → Streamlit with buffered delivery |
| 🔀 **Conditional Routing** | Scalar answers skip the viz agent entirely; only tabular/multi-row data gets charted |
| ✏️ **Full CRUD** | Read, insert, update, delete — changes written back to the source file |
| 🛡️ **Guardrails** | Read-only SQL validation, CTE support, 2000-row cap, retry + keyword fallback on LLM failures |
| 🔐 **Role-Based Access** | `analyst` (read-only), `editor` (read/write), `admin` (full) |
| 📜 **Audit Trail** | Every operation logged as JSONL with timestamp, query, row count, and status |
| 🐳 **One-Command Deploy** | Docker Compose for local, Cloud Run for production |

---

## Architecture

<img width="1111" height="846" alt="image" src="https://github.com/user-attachments/assets/a2c9a0ca-53d7-45e1-88ce-1762323dadb0" />

### Agent Responsibilities

| Agent | Role | LLM? | Tools |
|-------|------|:----:|-------|
| **Orchestrator** | Classifies intent → routes to the correct specialist | ✅ | — |
| **Schema Agent** | Answers questions about table structure, columns, types | ✅ | — |
| **Query Agent** | Translates NL to SQL, executes via `db_read`, decides if viz is needed | ✅ | `db_read` |
| **Viz Agent** | Picks chart type or writes prose based on data shape | ✅ | — |
| **Write Agent** | Handles INSERT / UPDATE / DELETE with confirmation flow | ✅ | `db_create`, `db_update`, `db_delete` |
| **Report Agent** | Decomposes a topic into sub-questions, fans out in parallel, synthesizes findings | ✅ | *(calls query + viz agents)* |

---

## Report Agent

The Report Agent is a fully autonomous analysis mode — no questions required. Toggle to **📑 Report** in the UI, optionally provide a focus topic, and click **▶ Generate Report**.

### How it works

```
1. Decompose   — LLM generates 6 focused sub-questions from the schema + optional focus
2. Fan-out     — all 6 run in parallel via asyncio.gather()
                 each: query_agent (NL→SQL→DuckDB) → viz_agent (chart/prose)
3. Synthesize  — LLM writes a 3-5 sentence executive summary connecting all findings
4. Render      — structured document: summary box + numbered sections with inline charts
```

### Example output for Titanic (no focus specified)

> **Analysis: titanic**
>
> *Executive summary:* 3rd class passengers made up the majority of the ship's manifest but had the lowest survival rate at 24%, compared to 63% for 1st class. Women survived at a dramatically higher rate (74%) than men (19%) across all classes. The fare distribution was heavily right-skewed — most passengers paid under £30 while a small group paid over £500. Southampton was the primary embarkation port, accounting for 72% of all passengers...

Each section includes the sub-question as a header, a chart or table, and a 1-2 sentence insight.

### Optional focus topic

| Input | What gets analysed |
|-------|-------------------|
| *(blank)* | Full exploratory analysis — distributions, comparisons, rankings, breakdowns |
| `"survival factors"` | Questions weighted toward variables that predict survival |
| `"passenger demographics"` | Age, gender, class, embarkation distributions |
| `"fare and class"` | Pricing structure, class distribution, fare vs class correlations |

---

## Dataset Profiler

Click **📊 Profile** in the sidebar to get an instant column-level breakdown of the active dataset — before asking a single question.

```
titanic — 891 rows × 12 columns

Age        DOUBLE   · ⚠️ 19.9% null  · 88 unique  · range 0.42 – 80.00 · avg 29.70
Pclass     INTEGER  · 0% null        · 3 unique   · top: 3, 1, 2
Sex        VARCHAR  · 0% null        · 2 unique   · top: male, female
Survived   INTEGER  · 0% null        · 2 unique   · top: 0, 1
Embarked   VARCHAR  · ⚠️ 0.2% null   · 3 unique   · top: S, C, Q
Fare       DOUBLE   · 0% null        · 248 unique · range 0.00 – 512.33 · avg 32.20
```

Null rates above 5% are flagged with ⚠️. High-cardinality columns (>50 unique values) skip the top-values list to keep the display clean.

---

## Smart Visualisation

The system makes an intelligent two-stage decision:

### Stage 1 — Does this need a chart at all?

```python
# Heuristic in query_agent (fast path — no LLM call needed)
Single scalar (1 row, 1 col)  →  prose answer     "There are 261 matching records."
Single summary row (≤3 cols)  →  prose answer     "Average Fare: $32.20"
Multi-row / multi-col         →  route to viz_agent for chart selection
```

### Stage 2 — Which chart type?

The viz agent selects from 12 chart types based on data shape and user intent:

| Chart | When |
|-------|------|
| `bar` | Comparing discrete categories |
| `bar_h` | Long category names or >8 categories |
| `stacked_bar` | Categories split into sub-groups |
| `grouped_bar` | Side-by-side when absolute values matter |
| `line` | Time series or ordered sequences |
| `area` | Cumulative magnitude over time |
| `pie` / `donut` | Proportions of a whole (≤6 slices) |
| `histogram` | Distribution of a single numeric column |
| `scatter` | Relationship between two numeric columns |
| `heatmap` | Dense 2D data or correlation matrices |
| `box` | Distribution spread + outliers per category |
| `table` | Raw listings or when no chart fits |

The agent also **decodes values** (0/1 → "Survived"/"Did not survive"), **renames columns** (Pclass → "Passenger Class"), and **formats numbers** (fares as currency, ages in months for infants).

---

## Project Structure

```
TalktoDB/
├── .env.example                # Template — just add your Gemini key
├── requirements.txt            # All deps (pip install -r requirements.txt)
├── Dockerfile                  # Monolith image — FastAPI + Streamlit in one container
├── docker-compose.yml          # Local dev: single container, volumes for data/ and logs/
├── start.sh                    # Boots uvicorn + streamlit inside the container
├── cloudbuild.yaml             # GCP Cloud Build CI/CD
│
├── agent/
│   ├── graph.py                # StateGraph definition + streaming logic
│   ├── state.py                # AgentState TypedDict (shared memory)
│   ├── prompts.py              # System prompts for all agents
│   ├── schema_loader.py        # Auto-discovers schemas from data/ files
│   ├── output_formatter.py     # Parses ```data``` blocks → charts/tables
│   └── subagents/
│       ├── orchestrator.py     # Intent classifier (LLM + keyword fallback)
│       ├── schema_agent.py     # Structure Q&A
│       ├── query_agent.py      # NL→SQL + needs_viz decision
│       ├── viz_agent.py        # Chart/prose formatting
│       ├── write_agent.py      # CRUD with confirmation
│       └── report_agent.py     # Autonomous multi-section report orchestrator
│
├── api/
│   └── main.py                 # FastAPI: /chat (SSE), /report, /profile, /upload, /audit
│
├── ui/
│   └── app.py                  # Streamlit: Chat + Report modes, dark theme, Plotly charts
│
├── db/
│   ├── __init__.py             # load_driver() + auto-discovery of data/ files
│   ├── base.py                 # Abstract driver interface
│   ├── csv_driver.py           # DuckDB-backed CSV queries
│   ├── json_driver.py          # DuckDB-backed JSON queries
│   ├── tools.py                # @tool functions: db_read, db_create, db_update, db_delete
│   └── profiler.py             # DuckDB SUMMARIZE → per-column stats
│
├── mcp_server/
│   ├── auth.py                 # Role permission enforcement
│   └── audit.py                # JSONL audit logger
│
├── config/
│   ├── databases.yaml          # Optional: custom aliases for data files
│   └── access_control.yaml     # Role → operation mappings
│
├── data/                       # Drop CSV / JSON here — auto-discovered
└── logs/                       # audit.log written at runtime
```

---

## Quickstart

### Prerequisites

- **Python 3.11+**
- **Gemini API key** — [get one free](https://aistudio.google.com/app/apikey)

### 1. Clone & install

```bash
git clone <your-repo-url> && cd TalktoDB
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env → set GEMINI_API_KEY=your_key_here
```

### 3. Add data

```bash
# Drop any CSV or JSON into data/
cp ~/Downloads/titanic.csv data/
# Available immediately as alias "titanic" — no config needed
```

### 4. Run

```bash
# Terminal 1 — API
uvicorn api.main:app --port 8000 --reload

# Terminal 2 — UI
streamlit run ui/app.py
```

Open **http://localhost:8501** → select your dataset → ask a question.

### 5. (Optional) Docker

```bash
docker compose up --build
# API → http://localhost:8000/docs
# UI  → http://localhost:8501
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe + current role |
| `GET` | `/databases` | List all discovered datasets |
| `GET` | `/schema/{alias}` | Column names + types for a dataset |
| `GET` | `/profile/{alias}` | Per-column stats: type, null%, range, cardinality, top values |
| `POST` | `/upload` | Upload a CSV or JSON file |
| `DELETE` | `/upload/{filename}` | Remove an uploaded file |
| `POST` | `/chat` | Stream agent response (SSE) |
| `POST` | `/report` | Generate autonomous multi-section analysis (JSON) |
| `GET` | `/audit` | Last 50 audit log entries |
| `GET` | `/graph` | Agent topology (nodes + edges) |

### Chat endpoint

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many passengers survived?", "db_alias": "titanic"}'
```

Returns a stream of SSE events:

```
data: {"type": "node_enter", "node": "orchestrator"}
data: {"type": "node_enter", "node": "query_agent"}
data: {"type": "tool_call", "tool": "db_read", "input": {...}}
data: {"type": "tool_result", "tool": "db_read", "output": "[{\"count\": 342}]"}
data: {"type": "token", "text": "There are **342** passengers who survived."}
```

### Report endpoint

```bash
curl -X POST http://localhost:8000/report \
  -H "Content-Type: application/json" \
  -d '{"db_alias": "titanic", "focus": "survival factors"}'
```

Returns a JSON document:

```json
{
  "title": "Analysis: titanic — survival factors",
  "focus": "survival factors",
  "summary": "Women had a 74% survival rate vs 19% for men...",
  "sections": [
    {
      "question": "What was the survival rate by passenger class?",
      "content": "```data\n{\"type\": \"chart\", ...}\n```\n1st class had a 63% survival rate...",
      "error": false
    }
  ]
}
```

---

## Resilience & Guardrails

| Layer | Protection |
|-------|-----------|
| **SQL validation** | Only `SELECT` (and CTEs starting with `WITH…SELECT`) pass through `db_read` |
| **Row cap** | Results capped at 2,000 rows to prevent memory blowout |
| **Orchestrator retry** | 2 LLM attempts; on total failure, falls back to regex keyword intent matching |
| **Timeout** | 120-second async timeout around the full graph execution |
| **Write safety** | `db_delete` requires explicit `confirmed=True`; `db_update` requires non-empty `WHERE` |
| **Token buffering** | 20-char chunks prevent UI flicker from single-character SSE events |
| **SSL handling** | `truststore` injection + Windows cert store extraction for corporate proxies |
| **Graceful fallback** | If a node produces no streaming tokens, `on_chain_end` emits `final_response` |

---

## Access Control

Set `AGENT_ROLE` in `.env`:

| Role | Read | Create | Update | Delete |
|------|:----:|:------:|:------:|:------:|
| `analyst` | ✅ | — | — | — |
| `editor` | ✅ | ✅ | ✅ | — |
| `admin` | ✅ | ✅ | ✅ | ✅ |

---

## Audit Log

Every database operation is appended to `logs/audit.log`:

```json
{"timestamp":"2026-06-25T14:23:45+00:00","operation":"read","db_alias":"titanic","query":"SELECT Pclass, COUNT(*) FROM titanic GROUP BY Pclass","row_count":3,"success":true}
```

View from the Streamlit sidebar → **📜 Audit Log** expander, or `GET /audit`.

---

## Deployment

### Docker Compose (local)

```bash
cp .env.example .env   # set GEMINI_API_KEY
docker compose up --build
# UI  → http://localhost:8501
# API → http://localhost:8000/docs
```

Single container running both FastAPI and Streamlit via `start.sh`.

### Google Cloud Run (production)

Push to `main` → Cloud Build auto-triggers via `cloudbuild.yaml`:

```bash
gcloud builds submit --config cloudbuild.yaml
```

The monolith `Dockerfile` bundles both FastAPI and Streamlit; `start.sh` boots both processes. Public traffic is routed to the Streamlit port.

> **⚠️ Ephemeral storage:** Cloud Run containers are stateless. Mount a GCS FUSE bucket to `/app/data` for persistent file storage.

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `GEMINI_API_KEY` | ✅ | — | Google AI Studio API key |
| `AGENT_ROLE` | — | `admin` | Access control role |
| `API_URL` | — | `http://localhost:8000` | Backend URL (used by Streamlit) |

### Custom Dataset Aliases

Files in `data/` are auto-discovered using the filename stem as the alias. For custom names:

```yaml
# config/databases.yaml
databases:
  q1_sales:
    driver: csv
    file: "data/sales_jan_2026.csv"
    description: "Q1 2026 revenue data"
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) StateGraph |
| LLM | [Gemini 2.5 Flash](https://ai.google.dev/) via `langchain-google-genai` |
| Agent pattern | [ReAct](https://arxiv.org/abs/2210.03629) (reason + act loop) |
| Query engine | [DuckDB](https://duckdb.org/) — in-process, zero-config |
| API | [FastAPI](https://fastapi.tiangolo.com/) + SSE streaming |
| UI | [Streamlit](https://streamlit.io/) + [Plotly](https://plotly.com/python/) (dark theme) |
| Data | Pandas DataFrames, CSV/JSON file I/O |

---

## Roadmap

- [ ] Multi-turn conversation memory (context across messages)
- [ ] Schema caching (avoid repeated introspection per request)
- [ ] Proper logging (replace debug prints with `structlog`)
- [ ] Report export as HTML / PDF
- [ ] Additional data sources (Parquet, Excel, SQLite)
- [ ] Natural language data entry ("Add a passenger named John, age 30, class 1")

---

## License

MIT — use freely, attribute kindly.

