# 1. Validate generated code at the engine, not only in text

## Context

PropTalk executes code an LLM wrote from user input. The model can be wrong, and the user can be hostile (prompt injection, "ignore your instructions and drop the table"). The original design relied on a text-level guard (`sql_guard.py`): SELECT-only, no `;`, a keyword blocklist, a regex table whitelist. A regex cannot fully parse SQL, and testing found real gaps:

- a `LIMIT` inside a string literal suppressed the row cap;
- double-quoted identifiers escaped the table whitelist;
- `FROM t JOIN x` read `JOIN` as an alias, so `x` was never checked (fixed).

## Decision

Keep the guard as a fast first filter with clear error messages, but make the **engine** enforce the rules that matter, independently of it:

- `sqlite3` `set_authorizer` allowlist: SELECT, reads of whitelisted tables, and functions other than `load_extension`. Everything else is denied, including writes, DDL, ATTACH, PRAGMA, and `sqlite_master`.
- `PRAGMA query_only = ON`, so writes fail even if the authorizer is removed.
- A progress-handler time budget, a per-value size limit, and `fetchmany(MAX_ROWS)`.

## Consequences

- `tests/test_sqlite_backend.py` runs writes, DDL, ATTACH, PRAGMA and schema reads directly against the engine with the guard skipped, and shows each layer blocks writes on its own.
- Guard gaps are documented as tests (`tests/test_sql_guard.py`) with the engine-level backstop that covers them, not hidden.
- The pandas path has no equivalent engine, so its protection is weaker (see [ADR 0004](0004-pandas-subprocess.md)).
