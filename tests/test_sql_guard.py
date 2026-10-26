"""sql_guard: what the text-level guard accepts, rejects, and rewrites.

Includes a bypass corpus. Where the guard is fooled, the corresponding
engine-level backstop is tested in test_sqlite_backend.py.
"""

import pytest

from sql_guard import MAX_ROWS, validate_query

ALLOWED = ["deed_transactions", "mls_listings"]


def _valid(sql: str) -> str:
    ok, sanitized, reason = validate_query(sql, ALLOWED)
    assert ok, reason
    return sanitized


def _rejected(sql: str) -> str:
    ok, sanitized, reason = validate_query(sql, ALLOWED)
    assert not ok, f"expected rejection, got: {sanitized}"
    assert sanitized == ""
    return reason


@pytest.mark.parametrize("sql", [
    "SELECT * FROM deed_transactions",
    "SELECT city, COUNT(*) AS n FROM deed_transactions GROUP BY city ORDER BY n DESC LIMIT 10",
    "select * from mls_listings where City = 'Katy'",
    "SELECT d.city FROM deed_transactions d JOIN mls_listings m ON d.city = m.City",
    "SELECT * FROM DEED_TRANSACTIONS",
])
def test_accepts_plain_selects(sql: str) -> None:
    _valid(sql)


@pytest.mark.parametrize("sql, reason", [
    ("", "Empty query"),
    ("   ", "Empty query"),
    ("DELETE FROM deed_transactions", "must start with SELECT"),
    ("UPDATE deed_transactions SET city = 'X'", "must start with SELECT"),
    ("DROP TABLE deed_transactions", "must start with SELECT"),
    ("ATTACH DATABASE '/tmp/x.db' AS x", "must start with SELECT"),
    ("PRAGMA query_only = OFF", "must start with SELECT"),
    # A CTE that writes (SQLite allows WITH ... DELETE).
    ("WITH x AS (SELECT 1) DELETE FROM deed_transactions", "must start with SELECT"),
    # Comment tricks: a comment cannot hide the leading keyword or split SELECT.
    ("/* hi */ DELETE FROM deed_transactions", "must start with SELECT"),
    ("SEL/**/ECT * FROM deed_transactions", "must start with SELECT"),
    # Multi-statement.
    ("SELECT * FROM deed_transactions; DROP TABLE deed_transactions", "semicolons"),
    ("SELECT * FROM deed_transactions;", "semicolons"),
    # Keyword blocklist inside an otherwise valid SELECT, any case.
    ("SELECT * FROM deed_transactions WHERE 1=1 dElEtE", "DELETE"),
    ("SELECT load_extension('evil') FROM deed_transactions", "LOAD_EXTENSION"),
    ("SELECT * INTO copy FROM deed_transactions", "INTO"),
    ("SELECT 1 AS pragma FROM deed_transactions", "PRAGMA"),
    ("SELECT 1 AS attach FROM deed_transactions", "ATTACH"),
    # Whitelist.
    ("SELECT * FROM sqlite_master", "not in whitelist"),
    ("SELECT name FROM pragma_table_info('deed_transactions')", "not in whitelist"),
    ("SELECT * FROM deed_transactions JOIN secrets ON 1=1", "not in whitelist"),
    ("SELECT * FROM deed_transactions LEFT JOIN secrets ON 1=1", "not in whitelist"),
    ("SELECT * FROM deed_transactions JOIN mls_listings ON 1=1 JOIN secrets ON 1=1",
     "not in whitelist"),
    ("SELECT * FROM deed_transactions, secrets", "not in whitelist"),
    ("SELECT * FROM main.deed_transactions", "not in whitelist"),
    ("SELECT sqlite_version()", "at least one whitelisted table"),
])
def test_rejects(sql: str, reason: str) -> None:
    assert reason.lower() in _rejected(sql).lower()


def test_comments_are_stripped_from_the_executed_query() -> None:
    sanitized = _valid("SELECT * FROM deed_transactions -- ; DROP TABLE deed_transactions")
    assert "DROP" not in sanitized
    sanitized = _valid("SELECT * FROM deed_transactions /* ; DELETE FROM x */ WHERE 1=1")
    assert "DELETE" not in sanitized


@pytest.mark.parametrize("sql, expected_tail", [
    ("SELECT * FROM deed_transactions", f"LIMIT {MAX_ROWS}"),
    ("SELECT * FROM deed_transactions LIMIT 50", "LIMIT 50"),
    ("SELECT * FROM deed_transactions LIMIT 999999", f"LIMIT {MAX_ROWS}"),
    ("SELECT * FROM deed_transactions limit 999999 offset 5", f"LIMIT {MAX_ROWS} OFFSET 5"),
    # SQLite's comma form is LIMIT <offset>, <count>: the count is capped.
    ("SELECT * FROM deed_transactions LIMIT 5, 999999", f"LIMIT 5, {MAX_ROWS}"),
    ("SELECT * FROM deed_transactions LIMIT 999999, 20", "LIMIT 999999, 20"),
    ("SELECT * FROM deed_transactions LIMIT 50 OFFSET 999999", "LIMIT 50 OFFSET 999999"),
])
def test_row_limit_is_added_or_capped(sql: str, expected_tail: str) -> None:
    assert _valid(sql).endswith(expected_tail)


# --- Known gaps: the guard is fooled; the engine is the backstop. ----------

def test_gap_limit_inside_string_literal_suppresses_row_cap() -> None:
    """The guard sees 'LIMIT' in a literal and adds no LIMIT clause.
    Backstop: fetchmany(MAX_ROWS) in sqlite_backend (tested there)."""
    sanitized = _valid("SELECT * FROM deed_transactions WHERE city <> 'LIMIT 1'")
    assert not sanitized.endswith(f"LIMIT {MAX_ROWS}")


def test_gap_double_quoted_identifier_escapes_whitelist() -> None:
    """Table extraction ignores "quoted" identifiers, so a non-whitelisted
    table slips through. Backstop: the engine authorizer (tested there)."""
    _valid('SELECT * FROM deed_transactions, "sqlite_master"')


def test_false_positive_semicolon_in_literal() -> None:
    """Over-blocking, not a hole: a ';' inside a string is still rejected."""
    _rejected("SELECT * FROM deed_transactions WHERE city = 'A;B'")


def test_false_positive_read_only_cte_is_rejected() -> None:
    """Over-blocking: read-only CTEs are rejected because the query must
    start with SELECT."""
    _rejected("WITH c AS (SELECT * FROM deed_transactions) SELECT * FROM c")
