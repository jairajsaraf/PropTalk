"""SQLite backend — an in-memory engine loaded from the same synthetic CSVs
as the pandas backend, standing in for a real SQL database in this demo.

Safety is enforced at the ENGINE level, not just by sql_guard's text-level
checks:
  - sqlite3.Connection.set_authorizer(...) — an allowlist callback that
    permits only SELECT/read access to whitelisted tables and a safe
    subset of functions, denying everything else (INSERT, UPDATE, DELETE,
    DDL, ATTACH, PRAGMA, ...) at the C level before it ever runs.
  - PRAGMA query_only = ON — a second, independent switch that makes the
    connection reject any write regardless of what the authorizer does.
  - set_progress_handler(...) — a wall-clock time budget so a runaway
    query (e.g. a recursive CTE) is interrupted instead of hanging.
  - setlimit(SQLITE_LIMIT_LENGTH, ...) — caps any single string/blob, since
    one huge randomblob() is a single VM step the time budget can't see.
  - fetchmany(MAX_ROWS) — the row cap is enforced here, not only by
    sql_guard's text-level LIMIT injection, which can be fooled.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pandas as pd

import csv_backend
from csv_backend import DATE_COLUMNS, _get_schema_str
from sql_guard import MAX_ROWS, validate_query

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

QUERY_TIME_BUDGET_SECONDS = 5
_PROGRESS_HANDLER_STEPS = 1000  # VM instructions between progress-handler calls
_MAX_VALUE_BYTES = 1_000_000  # largest string/blob any expression may produce

_execute_lock = threading.Lock()


def _make_authorizer(allowed_tables: set[str]):
    """Build a set_authorizer callback implementing a read-only allowlist.

    Anything not explicitly allowed here is denied, including writes, DDL,
    ATTACH/DETACH, PRAGMA, and reads of tables outside the whitelist (e.g.
    sqlite_master).
    """

    def authorizer(action_code, arg1, arg2, db_name, trigger_name):
        if action_code == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action_code == sqlite3.SQLITE_READ:
            # arg1 = table name, arg2 = column name. A CTE's own rows are
            # also reported as SQLITE_READ, but with db_name=None (they
            # aren't a persisted table in any attached database) — allow
            # those unconditionally so WITH RECURSIVE still works, and
            # bound it with the progress handler instead. A real table
            # (db_name="main") must be on the whitelist; this is what
            # denies sqlite_master/sqlite_temp_master schema reads.
            if db_name is None:
                return sqlite3.SQLITE_OK
            if arg1 in allowed_tables:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        if action_code == sqlite3.SQLITE_FUNCTION:
            # arg2 = function name; block extension loading explicitly even
            # though enable_load_extension is never turned on.
            if (arg2 or "").lower() == "load_extension":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if action_code == sqlite3.SQLITE_RECURSIVE:
            # Allowed so WITH RECURSIVE still works for legitimate queries;
            # bounded by the progress handler's time budget, not by denying
            # recursion outright.
            return sqlite3.SQLITE_OK
        # Everything else — INSERT, UPDATE, DELETE, DROP, CREATE, ATTACH,
        # DETACH, PRAGMA, TRANSACTION, SAVEPOINT, TRIGGER, etc. — is denied.
        return sqlite3.SQLITE_DENY

    return authorizer


def create_connection() -> sqlite3.Connection:
    """Build an in-memory SQLite engine from config.TABLE_REGISTRY, load the
    synthetic CSVs into it, and lock it down. Uncached; the app uses
    _build_connection, which is the same function cached per process.
    """
    from config import TABLE_REGISTRY

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    sqlite_table_names: set[str] = set()
    for t in TABLE_REGISTRY:
        df = csv_backend._load_data(t.csv_filename, DATE_COLUMNS.get(t.display_name, []))
        df.to_sql(t.sqlite_table, conn, if_exists="replace", index=False)
        sqlite_table_names.add(t.sqlite_table)

    # Independent write-blocking switch, on top of the authorizer below.
    conn.execute("PRAGMA query_only = ON")
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, _MAX_VALUE_BYTES)
    conn.set_authorizer(_make_authorizer(sqlite_table_names))
    return conn


# Cached as a Streamlit resource so the engine is built once per server
# process, not re-loaded on every script rerun.
_build_connection = st.cache_resource(create_connection) if HAS_STREAMLIT else create_connection


def execute_query(query: str, conn: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Execute an already-validated SELECT query against the shared engine.

    Args:
        query: SQL that has already passed sql_guard.validate_query.
        conn: Engine to run on; defaults to the shared cached connection.

    Returns:
        DataFrame with at most MAX_ROWS rows.

    Raises:
        ValueError: on a timeout (progress-handler interrupt) or any
            execution error from the engine (including an authorizer
            denial, as defense in depth if a bad query ever reached here).
    """
    conn = conn or _build_connection()
    deadline = time.monotonic() + QUERY_TIME_BUDGET_SECONDS

    def _progress() -> int:
        return 1 if time.monotonic() > deadline else 0

    with _execute_lock:
        conn.set_progress_handler(_progress, _PROGRESS_HANDLER_STEPS)
        try:
            cursor = conn.execute(query)
            rows = cursor.fetchmany(MAX_ROWS)
            columns = [d[0] for d in cursor.description or []]
            cursor.close()
        except sqlite3.Error as exc:
            # A progress-handler interrupt can land in execute() or in the
            # fetch, and surfaces as OperationalError("interrupted").
            if "interrupted" in str(exc).lower():
                raise ValueError(
                    f"Query execution timed out after {QUERY_TIME_BUDGET_SECONDS} "
                    "seconds. Try a simpler query."
                ) from exc
            raise ValueError(str(exc)) from exc
        finally:
            conn.set_progress_handler(None, _PROGRESS_HANDLER_STEPS)

    return pd.DataFrame.from_records(rows, columns=columns)


class SqliteBackend:
    """SQLite-based backend conforming to the DataBackend protocol."""

    def __init__(self, tables: list[dict]) -> None:
        """Initialize with a list of {display_name, table_id, csv_filename,
        sqlite_table} dicts."""
        self._tables = tables
        self._file_map = {t["table_id"]: t["csv_filename"] for t in tables}
        self._sqlite_table_map = {t["table_id"]: t["sqlite_table"] for t in tables}

    def get_tables(self) -> list[dict]:
        return [{"display_name": t["display_name"], "table_id": t["table_id"]}
                for t in self._tables]

    def get_schema(self, table_id: str) -> str:
        # Schema is derived from the source DataFrame (same as the pandas
        # backend) rather than via PRAGMA table_info, since the engine's
        # authorizer denies PRAGMA entirely.
        df = self._load_source_data(table_id)
        return _get_schema_str(df)

    def execute(self, query: str, table_id: str) -> pd.DataFrame:
        allowed = self.get_allowed_table_names()
        is_valid, sanitized, reason = validate_query(query, allowed)
        if not is_valid:
            raise ValueError(f"Query rejected: {reason}")
        return execute_query(sanitized)

    def get_query_language(self) -> str:
        return "sql"

    def get_allowed_table_names(self) -> list[str]:
        return list(self._sqlite_table_map.values())

    def get_sql_table_name(self, table_id: str) -> str:
        """Return the bare SQLite table name for a table_id (used in prompts)."""
        return self._sqlite_table_map[table_id]

    def _load_source_data(self, table_id: str) -> pd.DataFrame:
        filename = self._file_map[table_id]
        date_cols = DATE_COLUMNS.get(table_id, [])
        return csv_backend._load_data(filename, date_cols)
