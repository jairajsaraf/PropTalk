"""sqlite_backend: the engine-level controls hold even when sql_guard is
bypassed. Most tests call the raw connection directly, with no guard.
"""

import sqlite3
import time

import pytest

import config
import sqlite_backend
from sql_guard import MAX_ROWS, validate_query

ALLOWED = [t.sqlite_table for t in config.TABLE_REGISTRY]


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite_backend.create_connection()
    yield c
    c.close()


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ALLOWED}


WRITES_AND_ESCAPES = [
    "DELETE FROM deed_transactions",
    "UPDATE deed_transactions SET city = 'X'",
    "INSERT INTO deed_transactions (city) VALUES ('X')",
    "REPLACE INTO deed_transactions (city) VALUES ('X')",
    "DROP TABLE deed_transactions",
    "CREATE TABLE evil (x INTEGER)",
    "CREATE TEMP TABLE evil (x INTEGER)",
    "CREATE INDEX evil ON deed_transactions (city)",
    "ALTER TABLE deed_transactions ADD COLUMN evil INTEGER",
    "WITH x AS (SELECT 1) DELETE FROM deed_transactions",
    "ATTACH DATABASE ':memory:' AS evil",
    "PRAGMA query_only = OFF",
    "PRAGMA table_info(deed_transactions)",
    "VACUUM",
    "BEGIN",
]


@pytest.mark.parametrize("sql", WRITES_AND_ESCAPES)
def test_engine_denies_writes_and_escapes_without_the_guard(conn, sql: str) -> None:
    before = _row_counts(conn)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(sql)
    assert _row_counts(conn) == before


def test_query_only_alone_blocks_writes(conn) -> None:
    """Remove the authorizer: PRAGMA query_only still refuses the write."""
    before = _row_counts(conn)
    conn.set_authorizer(None)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM deed_transactions")
    assert _row_counts(conn) == before


def test_authorizer_alone_blocks_writes(conn) -> None:
    """Turn query_only off: the authorizer still refuses the write."""
    before = _row_counts(conn)
    conn.set_authorizer(None)
    conn.execute("PRAGMA query_only = OFF")
    assert conn.execute("PRAGMA query_only").fetchone()[0] == 0
    conn.set_authorizer(sqlite_backend._make_authorizer(set(ALLOWED)))
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        conn.execute("DELETE FROM deed_transactions")
    assert _row_counts(conn) == before


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sqlite_master",
    "SELECT * FROM sqlite_schema",
    "SELECT * FROM sqlite_temp_master",
    "SELECT name FROM pragma_table_info('deed_transactions')",
    "SELECT name FROM pragma_table_list",
    "SELECT * FROM pragma_database_list",
])
def test_engine_denies_schema_reads(conn, sql: str) -> None:
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(sql).fetchall()


def test_engine_denies_load_extension(conn) -> None:
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        conn.execute("SELECT load_extension('evil')")


def test_quoted_identifier_bypasses_guard_but_engine_denies(conn) -> None:
    ok, sanitized, _ = validate_query('SELECT * FROM deed_transactions, "sqlite_master"', ALLOWED)
    assert ok  # the guard is fooled (see test_sql_guard.py)
    with pytest.raises(ValueError, match="prohibited"):
        sqlite_backend.execute_query(sanitized, conn)


def test_row_cap_holds_when_guard_skips_limit(conn) -> None:
    """LIMIT -1 means "no limit" in SQLite and the guard leaves it alone;
    the engine still fetches at most MAX_ROWS rows of the cross join."""
    sql = ("SELECT a.parcel_id, b.parcel_id FROM deed_transactions a "
           "JOIN deed_transactions b ON 1=1 LIMIT -1")
    ok, sanitized, _ = validate_query(sql, ALLOWED)
    assert ok and str(MAX_ROWS) not in sanitized
    assert len(sqlite_backend.execute_query(sanitized, conn)) == MAX_ROWS


def test_runaway_recursive_query_is_interrupted(conn, monkeypatch) -> None:
    monkeypatch.setattr(sqlite_backend, "QUERY_TIME_BUDGET_SECONDS", 0.5)
    sql = ("WITH RECURSIVE spin(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM spin) "
           "SELECT COUNT(*) FROM spin")
    start = time.monotonic()
    with pytest.raises(ValueError, match="timed out"):
        sqlite_backend.execute_query(sql, conn)
    assert time.monotonic() - start < 3


def test_interrupt_during_fetch_is_reported_as_timeout(conn, monkeypatch) -> None:
    """This query yields its first row quickly, so the interrupt lands in
    the fetch rather than in execute(); it must still be a ValueError."""
    monkeypatch.setattr(sqlite_backend, "QUERY_TIME_BUDGET_SECONDS", 0.3)
    sql = ("SELECT a.parcel_id FROM deed_transactions a, deed_transactions b "
           "WHERE (a.rowid * 7919 + b.rowid) % 50000 = 0")
    with pytest.raises(ValueError, match="timed out"):
        sqlite_backend.execute_query(sql, conn)


def test_oversized_value_is_refused(conn) -> None:
    with pytest.raises(ValueError, match="too big"):
        sqlite_backend.execute_query(
            "SELECT randomblob(200000000) FROM deed_transactions LIMIT 1", conn)


def test_progress_handler_is_cleared_after_a_query(conn, monkeypatch) -> None:
    monkeypatch.setattr(sqlite_backend, "QUERY_TIME_BUDGET_SECONDS", 0.01)
    sqlite_backend.execute_query("SELECT 1 FROM deed_transactions LIMIT 1", conn)
    time.sleep(0.05)  # past the old deadline: a leftover handler would interrupt
    assert conn.execute("SELECT COUNT(*) FROM deed_transactions").fetchone()[0] == 5000


@pytest.mark.parametrize("sql, rows", [
    ("SELECT city, COUNT(*) AS n FROM deed_transactions GROUP BY city ORDER BY n DESC LIMIT 3", 3),
    (("SELECT strftime('%Y-%m', sale_date) AS m, COUNT(*) FROM deed_transactions "
      "WHERE strftime('%Y', sale_date) = '2024' GROUP BY m"), 12),
    (("WITH c AS (SELECT * FROM mls_listings WHERE StandardStatus = 'Closed') "
      "SELECT COUNT(*) FROM c"), 1),
    (("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x < 5) "
      "SELECT x FROM n"), 5),
    ("SELECT COUNT(*) FROM DEED_TRANSACTIONS", 1),
])
def test_legitimate_queries_run(conn, sql: str, rows: int) -> None:
    assert len(sqlite_backend.execute_query(sql, conn)) == rows


def test_backend_execute_applies_the_guard() -> None:
    backend = sqlite_backend.SqliteBackend(config.get_sqlite_tables())
    with pytest.raises(ValueError, match="Query rejected"):
        backend.execute("DELETE FROM deed_transactions", "Deed Transactions")
    df = backend.execute("SELECT * FROM deed_transactions", "Deed Transactions")
    assert len(df) == 5000
