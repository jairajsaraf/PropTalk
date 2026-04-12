"""Shared backend interface so app.py doesn't need scattered mode checks."""

from typing import Protocol

import pandas as pd


class DataBackend(Protocol):
    def get_tables(self) -> list[dict]:
        """Return list of {display_name, table_id} dicts."""
        ...

    def get_schema(self, table_id: str) -> str:
        """Return formatted schema string for LLM context."""
        ...

    def execute(self, query: str, table_id: str) -> pd.DataFrame:
        """Execute a query/expression and return results."""
        ...

    def get_query_language(self) -> str:
        """Return 'sql' or 'pandas' so prompts.py picks the right template."""
        ...

    def get_allowed_table_names(self) -> list[str]:
        """Return table identifiers for sql_guard whitelist (SQL mode only)."""
        ...
