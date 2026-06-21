import os
from pathlib import Path
from typing import Any

import duckdb

from db.base import BaseDriver


class JSONDriver(BaseDriver):
    """
    SQL access to a JSON file via DuckDB.

    The file is loaded into an in-memory DuckDB table named after the file stem
    (e.g. ``products.json`` → table ``products``).  SELECT queries run against
    that table; INSERT / UPDATE / DELETE changes are flushed back to the
    original JSON file automatically.

    Expected JSON format: a top-level array of objects, e.g.
        [{"id": 1, "name": "Widget"}, ...]
    """

    placeholder = "?"

    def __init__(self, file_path: str) -> None:
        self._file_path = os.path.abspath(file_path)
        self._table = Path(file_path).stem
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        self._conn = duckdb.connect()
        self._conn.execute(
            f"CREATE TABLE \"{self._table}\" AS "
            f"SELECT * FROM read_json_auto('{self._file_path}')"
        )

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self.connect()
        return self._conn

    def execute(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        conn = self._get_conn()
        rel = conn.execute(query, list(params))

        is_write = query.strip().upper().split()[0] in ("INSERT", "UPDATE", "DELETE")
        if is_write:
            # Persist changes back to the JSON file as a top-level array
            conn.execute(
                f"COPY \"{self._table}\" TO '{self._file_path}' (FORMAT JSON, ARRAY true)"
            )
            return []

        if rel.description:
            cols = [d[0] for d in rel.description]
            return [dict(zip(cols, row)) for row in rel.fetchall()]
        return []

    def fetch_schema(self) -> dict[str, list[str]]:
        conn = self._get_conn()
        result = conn.execute(f"DESCRIBE \"{self._table}\"")
        cols = [row[0] for row in result.fetchall()]
        return {self._table: cols}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
