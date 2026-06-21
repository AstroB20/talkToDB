import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db import list_databases, load_driver


def load_all_schemas() -> dict[str, dict[str, list[str]]]:
    """Return {db_alias: {table: [columns]}} for every configured database."""
    schemas: dict[str, dict[str, list[str]]] = {}
    for db_info in list_databases():
        alias = db_info["alias"]
        try:
            driver = load_driver(alias)
            schemas[alias] = driver.fetch_schema()
            driver.close()
        except Exception as exc:
            schemas[alias] = {"_error": [str(exc)]}
    return schemas


def format_schema_for_prompt(schemas: dict[str, dict]) -> str:
    lines: list[str] = []
    for db_alias, tables in schemas.items():
        lines.append(f"Database: {db_alias}")
        if "_error" in tables:
            lines.append(f"  (Schema unavailable: {tables['_error'][0]})")
        else:
            for table, columns in tables.items():
                lines.append(f"  Table `{table}`: {', '.join(columns)}")
        lines.append("")
    return "\n".join(lines)
