"""SQL validation — ensures LLM-generated queries are SELECT-only and safe."""

import re


BLOCKED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "EXEC", "EXECUTE", "MERGE", "TRUNCATE", "INTO",
    "GRANT", "REVOKE", "OPENROWSET", "OPENQUERY",
    "SHUTDOWN", "KILL", "WAITFOR", "BULK",
]

BLOCKED_PREFIXES = ["xp_", "sp_"]


def _strip_comments(sql: str) -> str:
    """Remove SQL comments (-- line comments and /* block comments */)."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


def _normalize(sql: str) -> str:
    """Strip comments and collapse whitespace."""
    sql = _strip_comments(sql)
    sql = re.sub(r"\s+", " ", sql).strip()
    return sql


def _has_row_limit(sql_upper: str) -> bool:
    """Check if query already has TOP or OFFSET...FETCH."""
    if re.search(r"\bTOP\s+\d+", sql_upper):
        return True
    if re.search(r"\bOFFSET\b.*\bFETCH\b", sql_upper):
        return True
    return False


def _extract_table_references(sql: str) -> list[str]:
    """Extract table references from SQL (after FROM / JOIN keywords).

    Handles fully qualified names like [db].[schema].[table] and unbracketed names.
    """
    tables = []
    pattern = r"(?:FROM|JOIN)\s+([\[\w\]\.]+)"
    for match in re.finditer(pattern, sql, re.IGNORECASE):
        tables.append(match.group(1))
    return tables


def _normalize_table_name(name: str) -> str:
    """Normalize table name for comparison — strip brackets, lowercase."""
    return name.replace("[", "").replace("]", "").lower().strip()


def validate_query(sql: str, allowed_tables: list[str]) -> tuple[bool, str, str]:
    """Validate an LLM-generated SQL query for safety.

    Args:
        sql: The raw SQL string from the LLM.
        allowed_tables: List of fully qualified table names that are permitted.

    Returns:
        (is_valid, sanitized_query, rejection_reason)
        - is_valid: True if the query passed all checks.
        - sanitized_query: The cleaned query (with row limit enforced). Empty if invalid.
        - rejection_reason: Human-readable reason for rejection. Empty if valid.
    """
    if not sql or not sql.strip():
        return False, "", "Empty query."

    normalized = _normalize(sql)
    upper = normalized.upper()

    # Must start with SELECT
    if not upper.startswith("SELECT"):
        return False, "", "Query must start with SELECT."

    # Semicolon check — prevents multi-statement injection
    if ";" in normalized:
        return False, "", "Query must not contain semicolons."

    # Keyword blocklist
    for keyword in BLOCKED_KEYWORDS:
        pattern = r"\b" + keyword + r"\b"
        if re.search(pattern, upper):
            return False, "", f"Blocked keyword found: {keyword}"

    # Blocked prefixes (xp_, sp_)
    for prefix in BLOCKED_PREFIXES:
        if re.search(r"\b" + prefix, normalized, re.IGNORECASE):
            return False, "", f"Blocked prefix found: {prefix}"

    # Table whitelist check
    referenced_tables = _extract_table_references(normalized)
    allowed_normalized = [_normalize_table_name(t) for t in allowed_tables]

    for table_ref in referenced_tables:
        ref_normalized = _normalize_table_name(table_ref)
        ref_parts = ref_normalized.split(".")
        matched = False
        for allowed in allowed_normalized:
            allowed_parts = allowed.split(".")
            # Exact match
            if ref_normalized == allowed:
                matched = True
                break
            # Suffix match: all parts of the reference must match the
            # corresponding trailing parts of the allowed name.
            # e.g. "dbo.tablename" matches "db.dbo.tablename",
            # but "other_db.dbo.tablename" does NOT match "db.dbo.tablename".
            if len(ref_parts) < len(allowed_parts):
                tail = allowed_parts[-len(ref_parts):]
                if ref_parts == tail:
                    matched = True
                    break
        if not matched:
            return False, "", f"Table not in whitelist: {table_ref}"

    # Force row limit if not present — inject TOP directly instead of
    # wrapping in a subquery (which would break ORDER BY clauses).
    if not _has_row_limit(upper):
        normalized = re.sub(
            r"^SELECT\b", "SELECT TOP 10000", normalized, count=1, flags=re.IGNORECASE
        )

    return True, normalized, ""
