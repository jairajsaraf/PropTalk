"""SQL Server backend — connection, schema introspection, query execution."""

from __future__ import annotations

import os

import pandas as pd

from sql_guard import validate_query

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# Table whitelist: display name -> fully qualified SQL Server name
# NOTE: Server hostname is NEVER hardcoded — it comes from os.getenv("SQL_SERVER")
TABLE_WHITELIST = {
    "Deed Transactions": "[DataMart1].[dbo].[Fact_Deed_Owner_Transfer_CoreLogic]",
    "HAR Listings": "[Research_Dev].[dbo].[Listings_Bridge_Interactive_Extract]",
    "Code Lookups": "[DataMart1].[dbo].[Dim_CoreLogic_Code]",
    "MLS Statistics": "[DataMart1].[dbo].[Fact_List_Mo_lsour_sta_kpi]",
    "Property Tax Stats": "[Research_Dev].[CoreLogic].[State_Property_Tax_Statistics]",
    "Investor Deed Activity": "[Research_Dev].[dbo].[Single_Family_Investor_Deed_Activity]",
    "Data Center Properties": "[Research_Dev].[dbo].[DataCenter_Properties_Verified]",
}


class SqlBackend:
    """SQL Server backend conforming to the DataBackend protocol."""

    def __init__(self, tables: list[dict]) -> None:
        """Initialize with a list of {display_name, table_id, fq_sql_name} dicts."""
        self._tables = tables
        self._fq_map = {t["table_id"]: t["fq_sql_name"] for t in tables}

    def get_tables(self) -> list[dict]:
        return [{"display_name": t["display_name"], "table_id": t["table_id"]}
                for t in self._tables]

    def get_schema(self, table_id: str) -> str:
        fq_name = self._fq_map[table_id]
        return get_schema(fq_name)

    def execute(self, query: str, table_id: str) -> pd.DataFrame:
        allowed = self.get_allowed_table_names()
        is_valid, sanitized, reason = validate_query(query, allowed)
        if not is_valid:
            raise ValueError(f"Query rejected: {reason}")
        return execute_query(sanitized)

    def get_query_language(self) -> str:
        return "sql"

    def get_allowed_table_names(self) -> list[str]:
        return list(self._fq_map.values())

    def get_fq_name(self, table_id: str) -> str:
        """Return the fully qualified SQL name for a table_id."""
        return self._fq_map[table_id]


def get_allowed_table_names() -> list[str]:
    """Return the list of fully qualified table names from the whitelist."""
    return list(TABLE_WHITELIST.values())


def is_available() -> bool:
    """Check if SQL Server mode is possible (pyodbc installed and SQL_SERVER set)."""
    return PYODBC_AVAILABLE and bool(os.getenv("SQL_SERVER"))


def _build_connection_string() -> str:
    """Build a pyodbc connection string from environment variables."""
    server = os.getenv("SQL_SERVER", "")
    database = os.getenv("SQL_DATABASE", "DataMart1")
    trusted = os.getenv("SQL_TRUSTED_CONNECTION", "").lower() in ("yes", "true", "1")
    user = os.getenv("SQL_USER", "")
    password = os.getenv("SQL_PASSWORD", "")

    parts = [
        "DRIVER={ODBC Driver 17 for SQL Server}",
        f"SERVER={server}",
        f"DATABASE={database}",
    ]
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={user}")
        parts.append(f"PWD={password}")

    return ";".join(parts)


def get_connection():
    """Get a pyodbc connection to SQL Server.

    Cached with @st.cache_resource when running inside Streamlit.
    """
    if not PYODBC_AVAILABLE:
        raise RuntimeError("pyodbc is not installed.")

    conn_str = _build_connection_string()
    conn = pyodbc.connect(conn_str, timeout=10)
    return conn


# Apply Streamlit caching if available
if HAS_STREAMLIT:
    get_connection = st.cache_resource(get_connection)


def get_schema(table_name: str, conn=None) -> str:
    """Get schema info for a table: column names, types, and sample values.

    Args:
        table_name: Fully qualified table name (e.g. [DataMart1].[dbo].[TableName]).
        conn: Optional pyodbc connection. If None, gets one via get_connection().

    Returns:
        Formatted string with column info for LLM context.
    """
    if conn is None:
        conn = get_connection()

    # Parse database, schema, table from fully qualified name
    parts = table_name.replace("[", "").replace("]", "").split(".")
    if len(parts) == 3:
        db_name, schema_name, tbl_name = parts
    elif len(parts) == 2:
        schema_name, tbl_name = parts
        db_name = os.getenv("SQL_DATABASE", "DataMart1")
    else:
        tbl_name = parts[0]
        db_name = os.getenv("SQL_DATABASE", "DataMart1")
        schema_name = "dbo"

    # Query column metadata
    col_query = f"""
    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
    FROM [{db_name}].INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = '{schema_name}' AND TABLE_NAME = '{tbl_name}'
    ORDER BY ORDINAL_POSITION
    """
    columns_df = pd.read_sql(col_query, conn)

    lines = []
    for _, row in columns_df.iterrows():
        col_name = row["COLUMN_NAME"]
        data_type = row["DATA_TYPE"]
        nullable = "nullable" if row["IS_NULLABLE"] == "YES" else "not null"
        max_len = row.get("CHARACTER_MAXIMUM_LENGTH")
        type_str = f"{data_type}({int(max_len)})" if pd.notna(max_len) and max_len else data_type

        # Get sample values
        try:
            sample_query = f"SELECT TOP 3 DISTINCT [{col_name}] FROM {table_name} WHERE [{col_name}] IS NOT NULL"
            samples = pd.read_sql(sample_query, conn)
            sample_vals = ", ".join(str(v) for v in samples.iloc[:, 0].tolist())
        except Exception:
            sample_vals = ""

        line = f"- {col_name} ({type_str}, {nullable})"
        if sample_vals:
            line += f" — examples: {sample_vals}"
        lines.append(line)

    return "\n".join(lines)


def execute_query(query: str, conn=None) -> pd.DataFrame:
    """Execute a validated SQL query and return results as a DataFrame.

    Args:
        query: The SQL query to execute (should already be validated by sql_guard).
        conn: Optional pyodbc connection.

    Returns:
        DataFrame with query results.

    Raises:
        Exception on query timeout or execution error.
    """
    if conn is None:
        conn = get_connection()

    return pd.read_sql(query, conn)
