"""
Dataset profiler — pure DuckDB, no LLM required.

Produces a lightweight "dataset passport" for any registered alias:
  - Row and column count
  - Per-column: type, null%, min, max, mean/stddev (numerics), cardinality,
    top-3 most-frequent values
"""

from __future__ import annotations

import json
from typing import Any

from db import load_driver


# Columns whose min/max/mean are meaningless to surface (e.g. free-text IDs)
_HIGH_CARDINALITY_THRESHOLD = 50  # unique values — above this skip top-values list


def profile_dataset(db_alias: str) -> dict[str, Any]:
    """
    Return a structured profile of the dataset registered under *db_alias*.

    Structure::

        {
          "alias": "titanic",
          "row_count": 891,
          "col_count": 12,
          "columns": [
            {
              "name": "Age",
              "dtype": "DOUBLE",
              "null_pct": 19.87,
              "min": 0.42,
              "max": 80.0,
              "mean": 29.7,
              "stddev": 14.53,
              "cardinality": 88,
              "top_values": [24.0, 22.0, 18.0]   # only when cardinality <= threshold
            },
            ...
          ]
        }
    """
    driver = load_driver(db_alias)
    try:
        table = _get_table_name(driver)
        conn = driver._get_conn()

        row_count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

        # DuckDB SUMMARIZE gives us type, min, max, avg, std, null%, unique count
        summary_rows = conn.execute(f'SUMMARIZE "{table}"').fetchall()
        summary_cols = [d[0] for d in conn.execute(f'SUMMARIZE "{table}"').description]

        columns = []
        for row in summary_rows:
            r = dict(zip(summary_cols, row))
            col_name = r.get("column_name", r.get("column", ""))
            dtype    = str(r.get("column_type", r.get("type", ""))).upper()
            null_pct = _safe_float(r.get("null_percentage", r.get("null%")))
            cardinality = _safe_int(r.get("approx_unique", r.get("unique")))

            col_info: dict[str, Any] = {
                "name":        col_name,
                "dtype":       dtype,
                "null_pct":    round(null_pct, 1) if null_pct is not None else None,
                "cardinality": cardinality,
            }

            is_numeric = any(t in dtype for t in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "REAL", "NUMERIC", "BIGINT", "HUGEINT"))
            is_date    = any(t in dtype for t in ("DATE", "TIME", "TIMESTAMP"))

            if is_numeric:
                col_info["min"]    = _safe_float(r.get("min"))
                col_info["max"]    = _safe_float(r.get("max"))
                col_info["mean"]   = _safe_float(r.get("avg", r.get("mean")))
                col_info["stddev"] = _safe_float(r.get("std", r.get("stddev")))
            elif is_date:
                col_info["min"] = str(r.get("min", ""))
                col_info["max"] = str(r.get("max", ""))
            else:
                # String / categorical — surface top values if cardinality is low enough
                if cardinality is not None and cardinality <= _HIGH_CARDINALITY_THRESHOLD:
                    try:
                        top = conn.execute(
                            f'SELECT "{col_name}", COUNT(*) AS n '
                            f'FROM "{table}" '
                            f'WHERE "{col_name}" IS NOT NULL '
                            f'GROUP BY 1 ORDER BY 2 DESC LIMIT 5'
                        ).fetchall()
                        col_info["top_values"] = [str(t[0]) for t in top]
                    except Exception:
                        pass

            columns.append(col_info)

        return {
            "alias":     db_alias,
            "row_count": row_count,
            "col_count": len(columns),
            "columns":   columns,
        }

    finally:
        driver.close()


def _get_table_name(driver) -> str:
    """Extract the table name from the driver (all current drivers expose ._table)."""
    return driver._table


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
