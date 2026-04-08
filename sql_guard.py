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
    if re.search(r"\bTOP\s*\(?\s*\d+\s*\)?\b", sql_upper):
        return True
    if re.search(r"\bOFFSET\b.*\bFETCH\b", sql_upper):
        return True
    return False


def _extract_table_references(sql: str) -> list[str]:
    """Extract table references from SQL (after FROM / JOIN keywords).

    Handles fully qualified names like [db].[schema].[table], unbracketed names,
    and comma-separated table lists (old-style joins).
    """
    tables = []
    table_token = r"[\[\w\]\.]+"

    # Match FROM/JOIN followed by one or more comma-separated table references
    # e.g. FROM [db].[dbo].[t1] a, [db].[dbo].[t2] b
    pattern = rf"(?:FROM|JOIN)\s+({table_token}(?:\s+\w+)?(?:\s*,\s*{table_token}(?:\s+\w+)?)*)"
    for block_match in re.finditer(pattern, sql, re.IGNORECASE):
        block = block_match.group(1)
        # Split on commas and extract each table name (strip optional alias)
        for part in block.split(","):
            part = part.strip()
            if part:
                # The table name is the first token; alias (if any) follows
                token_match = re.match(rf"({table_token})", part)
                if token_match:
                    tables.append(token_match.group(1))
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

    # Reject queries with no table references (e.g. SELECT @@version, SELECT DB_NAME())
    if not referenced_tables:
        return False, "", "Query must reference at least one whitelisted table."

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
            # Suffix match: require at least schema.table (2+ parts) to
            # prevent bare table names from matching across schemas/databases.
            # e.g. "dbo.tablename" matches "db.dbo.tablename",
            # but "tablename" alone does NOT match (too ambiguous).
            if len(ref_parts) >= 2 and len(ref_parts) < len(allowed_parts):
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
