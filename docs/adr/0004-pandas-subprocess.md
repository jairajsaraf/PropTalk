# 4. Run pandas code in a worker process with a timeout

## Context

In pandas mode the LLM writes Python. There is no engine to enforce rules as in [ADR 0001](0001-validated-generation.md), and running `exec` in the app's own process would let a runaway loop hang the app, or a mutation change the shared data.

## Decision

- A regex blocklist rejects imports, dunder access, `eval`/`exec`, file readers and writers, and similar before anything runs.
- The code runs in a separate `multiprocessing` process on a pickled copy of the DataFrame, with a 30-second timeout after which the process is terminated.
- `exec` gets an explicit allowlist of harmless builtins. It started with none, and the v1 eval showed that rejected ordinary code (`len`, `int`). Execution contract 2 added the allowlist and accepted scalar results.

## Consequences

- A hung or destructive query cannot affect the app or the data: in both eval runs, attack code that "deleted" or zeroed data ran against the copy and caused no harm.
- **This is not a sandbox.** The blocklist is an enumeration, and enumerations have gaps. `df.to_xml(path)` writes a file and is kept, unfixed, as a strict expected-failure test (`tests/test_pandas_guard.py`). The blocklist also matches inside string literals.
- On Windows each query starts a fresh interpreter (`spawn`), about 1.4 s per query when measured once by hand on the machine the eval ran on. On Linux the default `fork` is fast but forks a multi-threaded process, which Python warns can deadlock; switching start method is an open item.
- The executor's behavior is versioned (`EXEC_CONTRACT`) and recorded in every eval report, so old reports re-score under the rules they ran with.
