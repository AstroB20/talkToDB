"""
FastAPI backend — serves the A2A LangGraph multi-agent system over HTTP with SSE streaming.

How to run:
    uvicorn api.main:app --port 8000 --reload

Endpoints:
    GET  /health              — liveness check + current role
    GET  /databases           — list all available datasets (config + auto-discovered)
    GET  /schema/{db_alias}   — fetch table/column schema for one dataset
    POST /upload              — upload a CSV or JSON file into the data/ directory
    POST /chat                — stream agent response (SSE)
    GET  /audit               — tail the audit log
    GET  /graph               — A2A agent topology (nodes + edges)
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import AsyncIterator

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from db import list_databases, load_driver
from agent.graph import stream_agent_response

app = FastAPI(title="TalktoDB", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_DATA_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "data"))
_AUDIT_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "audit.log")
_ALLOWED_EXTENSIONS = {".csv", ".json"}


class ChatRequest(BaseModel):
    message: str
    db_alias: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "role": os.environ.get("AGENT_ROLE", "analyst")}


@app.get("/databases")
def get_databases():
    return list_databases()


@app.get("/schema/{db_alias}")
def get_schema(db_alias: str):
    try:
        driver = load_driver(db_alias)
        schema = driver.fetch_schema()
        driver.close()
        return {"db_alias": db_alias, "schema": schema}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a CSV or JSON file into the data/ directory.
    The file stem becomes the dataset alias immediately available for querying.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Only .csv and .json are accepted.",
        )

    # Sanitise filename — strip any directory components
    safe_name = Path(file.filename).name
    dest = _DATA_DIR / safe_name

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    alias = dest.stem
    return {
        "message": f"File '{safe_name}' uploaded successfully.",
        "alias": alias,
        "driver": suffix.lstrip("."),
    }


@app.delete("/upload/{filename}")
def delete_file(filename: str):
    """Remove an uploaded file from the data/ directory."""
    # Sanitise — no path traversal
    safe_name = Path(filename).name
    dest = _DATA_DIR / safe_name
    if not dest.exists():
        raise HTTPException(status_code=404, detail=f"File '{safe_name}' not found.")
    dest.unlink()
    return {"message": f"File '{safe_name}' deleted."}


@app.post("/chat")
async def chat(request: ChatRequest):
    async def event_generator() -> AsyncIterator[dict]:
        try:
            async for event in stream_agent_response(
                request.message,
                request.db_alias,
            ):
                yield {"data": json.dumps(event)}
        except PermissionError as exc:
            yield {"data": json.dumps({"type": "error", "message": str(exc)})}
        except Exception as exc:
            yield {"data": json.dumps({"type": "error", "message": f"Agent error: {exc}"})}
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())


@app.get("/audit")
def get_audit(limit: int = Query(default=50, le=500)):
    if not os.path.exists(_AUDIT_PATH):
        return []
    entries = []
    with open(_AUDIT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries[-limit:]


@app.get("/graph")
def get_graph_info():
    """Return the A2A agent graph topology for debugging / documentation."""
    return {
        "nodes": [
            {"id": "orchestrator", "role": "Routes intent to sub-agents"},
            {"id": "schema_agent", "role": "Answers questions about dataset structure"},
            {"id": "query_agent",  "role": "Executes SELECT queries via db_read tool"},
            {"id": "write_agent",  "role": "Executes INSERT/UPDATE/DELETE via write tools"},
            {"id": "viz_agent",    "role": "Formats query results as table or chart"},
        ],
        "edges": [
            {"from": "START",        "to": "orchestrator",  "type": "always"},
            {"from": "orchestrator", "to": "schema_agent",  "type": "conditional", "intent": "schema"},
            {"from": "orchestrator", "to": "query_agent",   "type": "conditional", "intent": "read"},
            {"from": "orchestrator", "to": "write_agent",   "type": "conditional", "intent": "write"},
            {"from": "orchestrator", "to": "END",           "type": "conditional", "intent": "end"},
            {"from": "query_agent",  "to": "viz_agent",     "type": "always"},
            {"from": "schema_agent", "to": "END",           "type": "always"},
            {"from": "write_agent",  "to": "END",           "type": "always"},
            {"from": "viz_agent",    "to": "END",           "type": "always"},
        ],
    }

