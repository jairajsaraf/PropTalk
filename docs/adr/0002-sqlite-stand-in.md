# 2. In-memory SQLite as the SQL engine for the demo

## Context

The original app ran T-SQL against a SQL Server reached through `pyodbc`, falling back to pandas over CSVs when no server was configured. A public demo cannot ship that server or its data, so the SQL path was untestable for anyone cloning the repo, and the security claims about it could not be shown.

## Decision

Remove SQL Server and `pyodbc`. Load the same synthetic CSVs into an in-memory `sqlite3` database (stdlib, no new dependency) and lock it down as described in [ADR 0001](0001-validated-generation.md). The sidebar lets the user choose SQL (SQLite) or pandas over the same data. The SQL prompt targets the SQLite dialect (`LIMIT`, `strftime`).

## Consequences

- Clone, generate data, set a key, run. There's no server to provision, and CI tests the real SQL path.
- SQLite is a stand-in. Its authorizer and `query_only` controls have counterparts in production databases (read-only roles, statement timeouts, row limits), but the exact mechanisms differ. Moving to a server means re-implementing the engine layer, not just the connection.
- Dates are stored as ISO text, so SQL results return dates as strings. The eval's scoring normalizes this, and the chart builder's automatic date detection does not see them.
