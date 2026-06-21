from abc import ABC, abstractmethod
from typing import Any


class BaseDriver(ABC):
    """Abstract interface all database drivers must implement."""

    placeholder: str = "?"  # SQL parameter placeholder; subclasses override for their dialect

    @abstractmethod
    def connect(self) -> None:
        """Open a database connection."""

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a query and return all result rows as a list of dicts."""

    @abstractmethod
    def fetch_schema(self) -> dict[str, list[str]]:
        """Return {table_name: [column_names]} for every table in the database."""

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
