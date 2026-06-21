import json
import os
from datetime import datetime, timezone
from typing import Optional


_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "audit.log")


def log_operation(
    operation: str,
    db_alias: str,
    query: str,
    row_count: int,
    success: bool,
    error: Optional[str] = None,
) -> None:
    """Append a single JSONL entry to the audit log."""
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
    entry: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "role": os.environ.get("AGENT_ROLE", "analyst"),
        "operation": operation,
        "db_alias": db_alias,
        "query": query,
        "row_count": row_count,
        "success": success,
    }
    if error:
        entry["error"] = error
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
