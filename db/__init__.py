import os
import re
from pathlib import Path

import yaml

from db.base import BaseDriver
from db.csv_driver import CSVDriver
from db.json_driver import JSONDriver

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "databases.yaml")
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _resolve(value: str) -> str:
    """Expand ${ENV_VAR} placeholders in config string values."""
    if isinstance(value, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)
    return value


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _auto_discover() -> dict:
    """Scan the data/ directory and register any .csv / .json files by file stem."""
    discovered: dict = {}
    data_dir = Path(_DATA_DIR)
    if not data_dir.exists():
        return discovered
    for file_path in sorted(data_dir.iterdir()):
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            discovered[file_path.stem] = {
                "driver": "csv",
                "file": str(file_path),
                "description": f"CSV file: {file_path.name}",
            }
        elif suffix == ".json":
            discovered[file_path.stem] = {
                "driver": "json",
                "file": str(file_path),
                "description": f"JSON file: {file_path.name}",
            }
    return discovered


def _all_databases() -> dict:
    """Merge manually configured databases with auto-discovered files.
    Config entries take precedence over auto-discovered ones."""
    databases = dict(_load_config().get("databases", {}))
    for alias, info in _auto_discover().items():
        if alias not in databases:
            databases[alias] = info
    return databases


def load_driver(db_alias: str) -> BaseDriver:
    """Instantiate and return a CSV or JSON driver for the given alias."""
    cfg = _all_databases().get(db_alias)
    if cfg is None:
        raise ValueError(f"Unknown database alias: '{db_alias}'")

    driver_type = cfg["driver"]
    file_path = _resolve(cfg.get("file", ""))

    if driver_type == "csv":
        return CSVDriver(file_path)
    if driver_type == "json":
        return JSONDriver(file_path)

    raise ValueError(f"Unsupported driver type: '{driver_type}'. Supported: csv, json.")


def list_databases() -> list[dict[str, str]]:
    """Return summary info for all available datasets."""
    return [
        {
            "alias": alias,
            "driver": info["driver"],
            "description": info.get("description", ""),
        }
        for alias, info in _all_databases().items()
    ]
