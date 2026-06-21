import os
from functools import lru_cache

import yaml


@lru_cache(maxsize=1)
def _load_config() -> dict:
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "access_control.yaml"
    )
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_role() -> str:
    return os.environ.get("AGENT_ROLE", "analyst")


def get_allowed_operations() -> list[str]:
    role = get_role()
    return _load_config()["roles"].get(role, {}).get("allowed_operations", [])


def require_permission(operation: str) -> None:
    """Raise PermissionError if the current role cannot perform the operation."""
    if operation not in get_allowed_operations():
        raise PermissionError(
            f"Role '{get_role()}' is not authorized to perform '{operation}' operations."
        )
