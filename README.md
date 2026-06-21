# TalktoDB-

A LangGraph-powered agent that lets you query and manage CSV and JSON datasets using plain English. Drop any file from Kaggle (or anywhere else) into the `data/` folder — or upload it through the UI — and start asking questions immediately.

---

## Features

- **Natural language → SQL** — powered by Gemini 1.5 Flash via a LangGraph multi-agent graph
- **CSV & JSON support** — files are queried with DuckDB; full SQL available
- **Auto-discovery** — any `.csv` or `.json` file in `data/` is instantly available, no config needed
- **File upload** — drag-and-drop upload directly from the Streamlit sidebar or via the API
- **Streaming responses** — tokens stream from agent → FastAPI → Streamlit in real time
- **Smart visualisation** — agent returns interactive tables or Plotly charts based on the result shape
- **Full CRUD** — read, insert, update, and delete rows; changes are written back to the source file
- **Audit log** — every operation appended to `logs/audit.log` as JSONL
- **Built-in demo** — one click loads the Titanic dataset and runs three example queries

---

## Architecture

```
Streamlit UI  ──(HTTP/SSE)──►  FastAPI Backend  ──►  LangGraph Agent (Gemini)
                                     │                        │
                               POST /upload            Direct Python tools
                                     │                 (db_read / db_create
                                  data/                 db_update / db_delete)
                             *.csv  *.json                     │
                                                           DuckDB
```

The agent graph routes each user message through five nodes:

```
START → orchestrator → schema_agent  → END
                     → query_agent   → viz_agent → END
                     → write_agent               → END
```

---

## Project Structure

````
LangGraph/
├── .env.example
├── requirements.txt
├── docker-compose.yml
├── Dockerfile.api
├── Dockerfile.ui
├── config/
│   ├── databases.yaml         # Optional: give custom aliases to specific files
│   └── access_control.yaml   # Role definitions (reserved for future use)
├── data/                      # Drop CSV / JSON files here — auto-discovered
├── logs/                      # audit.log written here at runtime
├── db/
│   ├── __init__.py            # load_driver() + list_databases() + auto-discovery
│   ├── base.py                # Abstract driver interface
│   ├── csv_driver.py          # DuckDB-backed CSV driver
│   ├── json_driver.py         # DuckDB-backed JSON driver
│   └── tools.py               # LangChain @tool functions used directly by agents
├── mcp_server/
│   ├── auth.py                # Role definitions (reserved for future use)
│   └── audit.py               # Append-only JSONL audit logger
├── agent/
│   ├── graph.py               # LangGraph StateGraph definition
│   ├── state.py               # AgentState TypedDict
│   ├── schema_loader.py       # Loads schema from all available datasets
│   ├── prompts.py             # System prompt builders for each agent node
│   ├── output_formatter.py    # Parses ```data``` blocks from responses
│   └── subagents/
│       ├── orchestrator.py    # Classifies intent and routes
│       ├── schema_agent.py    # Answers structure questions
│       ├── query_agent.py     # Runs SELECT queries via db_read
│       ├── write_agent.py     # Runs INSERT / UPDATE / DELETE
│       └── viz_agent.py       # Formats results as table or chart
├── api/
│   └── main.py                # FastAPI: /chat, /upload, /databases, /schema, /audit
└── ui/
    └── app.py                 # Streamlit chat UI with upload + demo button
````

---

## Quickstart

### 1. Prerequisites

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/app/apikey)

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set your key:

```env
GEMINI_API_KEY=your_key_here
```

### 4. Add a dataset

Drop any CSV or JSON file into the `data/` folder:

```powershell
# Example — download the Titanic dataset from Kaggle or anywhere
Copy-Item titanic.csv data/
```

The file is available immediately as alias `titanic` (the file stem). No config required.

### 5. Run

**Two terminals:**

```powershell
# Terminal 1 — API
uvicorn api.main:app --port 8000 --reload

# Terminal 2 — UI
streamlit run ui/app.py
```

Open [http://localhost:8501](http://localhost:8501) and start asking questions.

---

## Demo

Click **▶ Try the Demo** in the sidebar. It will:

1. Download the Titanic CSV from GitHub automatically
2. Upload it as the `titanic` dataset
3. Auto-run three example queries — a bar chart, a table, and a filtered list — so you can see the full pipeline in action

---

## Docker

```powershell
docker compose up --build
```

- API → [http://localhost:8000](http://localhost:8000) (docs at `/docs`)
- UI → [http://localhost:8501](http://localhost:8501)

Uploaded files are stored on the host via the `./data` volume mount and survive container restarts.

---

## API Endpoints

| Method | Path                 | Description                          |
| ------ | -------------------- | ------------------------------------ |
| GET    | `/health`            | Liveness check                       |
| GET    | `/databases`         | List all available datasets          |
| GET    | `/schema/{alias}`    | Column schema for a dataset          |
| POST   | `/upload`            | Upload a `.csv` or `.json` file      |
| DELETE | `/upload/{filename}` | Remove an uploaded file              |
| POST   | `/chat`              | Stream agent response (SSE)          |
| GET    | `/audit`             | Tail the audit log (last 50 entries) |
| GET    | `/graph`             | Agent topology (nodes + edges)       |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Dataset Config (optional)

Files dropped in `data/` are auto-discovered with no configuration. To give a file a custom alias or description, or to reference a file outside `data/`, add an entry to `config/databases.yaml`:

```yaml
databases:
  sales_q1:
    driver: csv
    file: "data/sales_jan_2026.csv"
    description: "Q1 2026 sales data"
```

---

## Supported File Formats

| Format | Query engine | Write-back format          |
| ------ | ------------ | -------------------------- |
| CSV    | DuckDB       | CSV with header row        |
| JSON   | DuckDB       | Top-level array of objects |

SQL is standard DuckDB SQL. The table name is always the file stem (e.g. `sales_data.csv` → `SELECT * FROM sales_data`).

---

## Agent Tools

| Tool        | Operation | Notes                              |
| ----------- | --------- | ---------------------------------- |
| `db_read`   | SELECT    | Rejects non-SELECT queries         |
| `db_create` | INSERT    | Writes back to source file         |
| `db_update` | UPDATE    | `where_conditions` required        |
| `db_delete` | DELETE    | Requires explicit `confirmed=True` |

---

## Visualisation

The agent embeds structured output in fenced ` ```data ``` ` blocks. The UI parses and renders them automatically:

| Data shape                     | Rendered as       |
| ------------------------------ | ----------------- |
| Two columns, one numeric       | Plotly bar chart  |
| Time/sequence column + numeric | Plotly line chart |
| Small set of named proportions | Plotly pie chart  |
| Anything else                  | Interactive table |

---

## Audit Log

Every operation is appended to `logs/audit.log` as JSONL:

```json
{
  "timestamp": "2026-06-21T10:23:45+00:00",
  "operation": "read",
  "db_alias": "titanic",
  "query": "SELECT Pclass, COUNT(*) FROM titanic GROUP BY Pclass",
  "row_count": 3,
  "success": true
}
```

View the last 100 entries from the Streamlit sidebar under **📜 View Audit Log**.

---

## Deploying to GCP Cloud Run

See the one-time setup instructions at the top of `cloudbuild.yaml`. After setup, every push to `main` triggers a full build and deploy automatically via Cloud Build. The public UI URL is printed at the end of each build log.

> **Note on uploaded files in Cloud Run:** containers are ephemeral. Mount a Cloud Storage FUSE bucket to `/app/data` for persistent file storage in production.

---

## Features

- **Natural language → SQL** — powered by Gemini 1.5 Flash via LangGraph ReAct
- **MCP tool server** — CRUD tools exposed over HTTP/SSE as a standalone service
- **Role-based access control** — `analyst`, `editor`, `admin` roles; configured in a YAML file
- **BigQuery native** — connects to Google BigQuery with service account or ADC authentication
- **Auto schema discovery** — tables and columns detected at startup, injected into the agent's context
- **Streaming responses** — tokens stream from agent → FastAPI → Streamlit in real time
- **Smart visualisation** — agent returns tables or Plotly charts depending on result shape
- **Audit log** — every operation appended to `logs/audit.log` as JSONL

---

## Architecture

```
Streamlit UI  ──(HTTP/SSE)──►  FastAPI Backend  ──►  LangGraph Agent (Gemini)
                                                             │
                                                    (HTTP/SSE MCP client)
                                                             │
                                                       MCP Server
                                                   ┌────────┴────────┐
                                                db_read          db_create
                                                db_update        db_delete
                                                             │
                                                        BigQuery
```

---

## Project Structure

````
LangGraph/
├── .env.example               # Environment variable template
├── requirements.txt
├── config/
│   ├── databases.yaml         # BigQuery connection settings
│   └── access_control.yaml   # Per-role CRUD permissions
├── logs/                      # audit.log written here at runtime
├── db/
│   ├── __init__.py            # load_driver() + list_databases()
│   ├── base.py                # Abstract driver interface
│   └── bigquery_driver.py     # BigQuery implementation
├── mcp_server/
│   ├── server.py              # FastMCP HTTP/SSE server with 4 tools
│   ├── auth.py                # Role permission enforcement
│   └── audit.py              # Append-only JSONL audit logger
├── agent/
│   ├── graph.py               # LangGraph ReAct graph + MCP client
│   ├── schema_loader.py       # Auto-detects schema from DB metadata
│   ├── prompts.py             # Role-aware system prompt builder
│   └── output_formatter.py   # Parses ```data``` blocks from responses
├── api/
│   └── main.py                # FastAPI: /chat, /databases, /schema, /audit
└── ui/
    └── app.py                 # Streamlit chat UI with chart rendering
````

---

## Quickstart

### 1. Prerequisites

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/app/apikey)
- A GCP project with BigQuery enabled
- Authentication: either a service account JSON key or `gcloud auth application-default login`

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set:

```env
GEMINI_API_KEY=your_key_here
AGENT_ROLE=analyst              # analyst | editor | admin
GCP_PROJECT_ID=your-project-id
BQ_DATASET=your_dataset         # limits schema discovery to this dataset
GOOGLE_APPLICATION_CREDENTIALS= # path to service account JSON, or leave blank for ADC
```

### 4. Configure BigQuery connection

Edit `config/databases.yaml` — update the project/dataset if your env var names differ:

```yaml
databases:
  my_bigquery:
    driver: bigquery
    project: "${GCP_PROJECT_ID}"
    dataset: "${BQ_DATASET}"
    location: US
    credentials_file: "${GOOGLE_APPLICATION_CREDENTIALS}"
    description: "BigQuery data warehouse"
```

### 5. Run (three separate terminals)

**Terminal 1 — MCP server**

```powershell
python mcp_server/server.py
```

**Terminal 2 — FastAPI backend**

```powershell
uvicorn api.main:app --port 8000
```

**Terminal 3 — Streamlit UI**

```powershell
streamlit run ui/app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Access Control

Roles and their permissions are defined in `config/access_control.yaml`:

| Role    | Read | Create | Update | Delete |
| ------- | :--: | :----: | :----: | :----: |
| analyst |  ✅  |   ❌   |   ❌   |   ❌   |
| editor  |  ✅  |   ✅   |   ✅   |   ❌   |
| admin   |  ✅  |   ✅   |   ✅   |   ✅   |

Set the active role via the `AGENT_ROLE` environment variable (in `.env`) before starting the servers. The agent is automatically given only the MCP tools its role permits.

---

## MCP Tools

| Tool        | Operation | SQL Statement | Notes                       |
| ----------- | --------- | ------------- | --------------------------- |
| `db_read`   | Read      | SELECT        | Rejects non-SELECT queries  |
| `db_create` | Create    | INSERT        | Fully parameterised         |
| `db_update` | Update    | UPDATE        | `where_conditions` required |
| `db_delete` | Delete    | DELETE        | Requires `confirmed=True`   |

---

## API Endpoints

| Method | Path                 | Description                          |
| ------ | -------------------- | ------------------------------------ |
| GET    | `/health`            | Liveness check + current role        |
| GET    | `/databases`         | List all configured DB aliases       |
| GET    | `/schema/{db_alias}` | Table/column schema for one database |
| POST   | `/chat`              | Stream agent response (SSE)          |
| GET    | `/audit`             | Tail the audit log (last 50 entries) |

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Visualisation

The agent embeds structured data in fenced ` ```data ``` ` blocks in its response. The Streamlit UI parses these and renders them automatically:

- **Tabular results** → `st.dataframe` (interactive, sortable table)
- **Numeric comparisons / counts** → Plotly bar chart
- **Trends over time** → Plotly line chart
- **Proportions** → Plotly pie chart

The agent decides which format to use based on the result shape.

---

## Audit Log

Every database operation is appended to `logs/audit.log` as a JSONL entry:

```json
{
  "timestamp": "2026-06-15T10:23:45+00:00",
  "role": "admin",
  "operation": "delete",
  "db_alias": "my_bigquery",
  "query": "DELETE FROM orders WHERE id = @p0",
  "row_count": -1,
  "success": true
}
```

View the last 100 entries from the Streamlit sidebar, or query `/audit` directly.

---

## Extending

**Add a new role**

1. Add an entry to `config/access_control.yaml` with the desired `allowed_operations`
2. Set `AGENT_ROLE=your_new_role` in `.env`

**Add visualisation tools (planned)**

- HTML report generation tool
- Markdown export tool
- These will be added as additional MCP tools in `mcp_server/server.py`
