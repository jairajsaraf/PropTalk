"""SQL validation — ensures LLM-generated queries are SELECT-only and safe.

This is a text-level, regex-based guard. It is intentionally not the only
line of defense: sqlite_backend.py additionally locks the engine itself
down with set_authorizer and PRAGMA query_only, because a regex can be
bypassed.
"""

import re

BLOCKED_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "EXEC", "EXECUTE", "MERGE", "TRUNCATE", "INTO",
    "GRANT", "REVOKE",
    "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX",
    "LOAD_EXTENSION",
]


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


MAX_ROWS = 10000

_LIMIT_OFFSET_RE = re.compile(r"\bLIMIT\s+(\d+)\s+OFFSET\s+(\d+)\b", re.IGNORECASE)
_LIMIT_COMMA_RE = re.compile(r"\bLIMIT\s+(\d+)\s*,\s*(\d+)\b", re.IGNORECASE)
_LIMIT_PLAIN_RE = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)
_LIMIT_KEYWORD_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")  # single-quoted literal, '' escapes


def _has_row_limit(sql: str) -> bool:
    """Check for a LIMIT clause outside string literals.

    Any form counts (LIMIT -1, LIMIT (5)): appending a second LIMIT would be
    a syntax error, and the engine caps the rows it fetches regardless.
    """
    return bool(_LIMIT_KEYWORD_RE.search(_LITERAL_RE.sub("''", sql)))


def _cap_row_limit(sql: str) -> str:
    """Cap numeric LIMIT clauses so none exceeds MAX_ROWS, leaving the text
    of string literals untouched."""
    parts, pos = [], 0
    for literal in _LITERAL_RE.finditer(sql):
        parts += [_cap_segment(sql[pos:literal.start()]), literal.group(0)]
        pos = literal.end()
    parts.append(_cap_segment(sql[pos:]))
    return "".join(parts)


def _cap_segment(sql: str) -> str:
    """Cap a LIMIT in SQL text that contains no string literal.

    Handles plain 'LIMIT n', 'LIMIT n OFFSET m', and SQLite's legacy
    'LIMIT offset, n' comma form (where the *second* number is the count).
    """
    # Pick the form by matching, not by whether a rewrite changed the text:
    # a comma form whose count is already under the cap must not fall
    # through to the plain rule, which would cap its offset instead.
    if _LIMIT_OFFSET_RE.search(sql):
        def _cap_offset_form(m):
            count, offset = int(m.group(1)), int(m.group(2))
            return f"LIMIT {min(count, MAX_ROWS)} OFFSET {offset}"
        return _LIMIT_OFFSET_RE.sub(_cap_offset_form, sql, count=1)

    if _LIMIT_COMMA_RE.search(sql):
        def _cap_comma_form(m):
            offset, count = int(m.group(1)), int(m.group(2))
            return f"LIMIT {offset}, {min(count, MAX_ROWS)}"
        return _LIMIT_COMMA_RE.sub(_cap_comma_form, sql, count=1)

    def _cap_plain(m):
        return f"LIMIT {min(int(m.group(1)), MAX_ROWS)}"

    return _LIMIT_PLAIN_RE.sub(_cap_plain, sql, count=1)


def _extract_table_references(sql: str) -> list[str]:
    """Extract table references from SQL (after FROM / JOIN keywords).

    Handles bracketed/bare identifiers and comma-separated table lists
    (old-style joins). Does NOT handle double-quoted or backtick-quoted
    identifiers; the engine's authorizer is the backstop for those.
    """
    tables = []
    table_token = r"[\[\w\]\.]+"

    # An alias must not be a keyword: otherwise "FROM t JOIN x" reads JOIN
    # as t's alias, consumes it, and x is never checked.
    keyword = (r"(?:JOIN|INNER|LEFT|RIGHT|FULL|CROSS|OUTER|NATURAL|ON|USING|WHERE"
               r"|GROUP|ORDER|LIMIT|HAVING|UNION|EXCEPT|INTERSECT|WINDOW)\b")
    alias = rf"(?:\s+(?:AS\s+)?(?!{keyword})\w+)?"
    pattern = rf"(?:FROM|JOIN)\s+({table_token}{alias}(?:\s*,\s*{table_token}{alias})*)"
    for block_match in re.finditer(pattern, sql, re.IGNORECASE):
        block = block_match.group(1)
        for part in block.split(","):
            part = part.strip()
            if part:
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
        allowed_tables: List of table names that are permitted (bare
            SQLite table names, e.g. "deed_transactions").

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

    # Table whitelist check
    referenced_tables = _extract_table_references(normalized)
    allowed_normalized = [_normalize_table_name(t) for t in allowed_tables]

    # Reject queries with no table references (e.g. SELECT sqlite_version())
    if not referenced_tables:
        return False, "", "Query must reference at least one whitelisted table."

    for table_ref in referenced_tables:
        ref_normalized = _normalize_table_name(table_ref)
        if ref_normalized not in allowed_normalized:
            return False, "", f"Table not in whitelist: {table_ref}"

    # Enforce row limit: inject LIMIT if missing, or cap an existing one.
    if not _has_row_limit(normalized):
        normalized = f"{normalized} LIMIT {MAX_ROWS}"
    else:
        normalized = _cap_row_limit(normalized)

    return True, normalized, ""
