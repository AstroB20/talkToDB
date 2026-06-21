"""
Direct LangChain tools for CSV/JSON database operations.

These replace the MCP server in the monolith architecture — the query and
write agents import and call these tools directly as Python functions, with
no network hop required.
"""

import json

from langchain_core.tools import tool

from db import load_driver
from mcp_server.audit import log_operation


@tool
def db_read(db_alias: str, sql_query: str) -> str:
    """
    Execute a read-only SELECT query against a CSV or JSON file dataset.

    Args:
        db_alias: Dataset alias — either the file stem (e.g. 'sales_data' for
                  sales_data.csv) or an alias defined in config/databases.yaml.
        sql_query: A valid SELECT statement.  The table name must match the
                   file stem (e.g. SELECT * FROM sales_data LIMIT 10).

    Returns:
        JSON array of result rows as a string.
    """
    if not sql_query.strip().upper().startswith("SELECT"):
        log_operation("read", db_alias, sql_query, 0, False, "Non-SELECT query rejected")
        raise ValueError("Only SELECT statements are permitted in db_read.")

    try:
        driver = load_driver(db_alias)
        rows = driver.execute(sql_query)
        driver.close()
        log_operation("read", db_alias, sql_query, len(rows), True)
        return json.dumps(rows, default=str)
    except Exception as exc:
        log_operation("read", db_alias, sql_query, 0, False, str(exc))
        raise


@tool
def db_create(db_alias: str, table: str, data: dict) -> str:
    """
    Insert a new record into a CSV or JSON file dataset.

    Args:
        db_alias: Dataset alias.
        table: Table name — must match the file stem.
        data: Column-value mapping for the new record.

    Returns:
        Confirmation string.
    """
    cols = ", ".join(f'"{k}"' for k in data.keys())
    placeholders = ", ".join(["?"] * len(data))
    query = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})'

    try:
        driver = load_driver(db_alias)
        driver.execute(query, tuple(data.values()))
        driver.close()
        log_operation("create", db_alias, query, 1, True)
        return f"Inserted 1 record into '{table}'."
    except Exception as exc:
        log_operation("create", db_alias, query, 0, False, str(exc))
        raise


@tool
def db_update(
    db_alias: str,
    table: str,
    updates: dict,
    where_conditions: dict,
) -> str:
    """
    Update records in a CSV or JSON file dataset.

    Args:
        db_alias: Dataset alias.
        table: Table name — must match the file stem.
        updates: Columns and new values to apply.
        where_conditions: Row filter — must not be empty to prevent full-table updates.

    Returns:
        Confirmation string.
    """
    if not where_conditions:
        raise ValueError("'where_conditions' must not be empty — refusing to update all rows.")

    set_clause = ", ".join(f'"{col}" = ?' for col in updates)
    where_clause = " AND ".join(f'"{col}" = ?' for col in where_conditions)
    query = f'UPDATE "{table}" SET {set_clause} WHERE {where_clause}'
    params = tuple(updates.values()) + tuple(where_conditions.values())

    try:
        driver = load_driver(db_alias)
        driver.execute(query, params)
        driver.close()
        log_operation("update", db_alias, query, -1, True)
        return f"Updated records in '{table}' where {where_conditions}."
    except Exception as exc:
        log_operation("update", db_alias, query, 0, False, str(exc))
        raise


@tool
def db_delete(
    db_alias: str,
    table: str,
    where_conditions: dict,
    confirmed: bool = False,
) -> str:
    """
    Delete records from a CSV or JSON file dataset.

    Args:
        db_alias: Dataset alias.
        table: Table name — must match the file stem.
        where_conditions: Row filter — must not be empty to prevent full-table deletes.
        confirmed: Must be explicitly True.  Always ask the user to confirm
                   before setting this to True.

    Returns:
        A confirmation prompt if confirmed=False, or a success message if confirmed=True.
    """
    if not confirmed:
        return (
            "Deletion not executed. "
            f"Please confirm you want to delete rows matching {where_conditions} "
            f"from '{table}', then retry with confirmed=True."
        )

    if not where_conditions:
        raise ValueError("'where_conditions' must not be empty — refusing to delete all rows.")

    where_clause = " AND ".join(f'"{col}" = ?' for col in where_conditions)
    query = f'DELETE FROM "{table}" WHERE {where_clause}'
    params = tuple(where_conditions.values())

    try:
        driver = load_driver(db_alias)
        driver.execute(query, params)
        driver.close()
        log_operation("delete", db_alias, query, -1, True)
        return f"Deleted records from '{table}' where {where_conditions}."
    except Exception as exc:
        log_operation("delete", db_alias, query, 0, False, str(exc))
        raise
