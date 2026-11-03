"""trust_panel: the 'how this answer was produced' checks and the eval line."""

import json

import csv_backend
import sql_guard
import sqlite_backend
import trust_panel

PASSED = {"is_valid": True, "sanitized_query": "SELECT 1", "rejection_reason": ""}


def _details(checks: list[trust_panel.TrustCheck]) -> dict[str, str]:
    return {c.label: c.detail for c in checks}


def test_sql_checks_use_code_constants(monkeypatch) -> None:
    monkeypatch.setattr(sql_guard, "MAX_ROWS", 123)
    monkeypatch.setattr(sqlite_backend, "QUERY_TIME_BUDGET_SECONDS", 7)

    details = _details(trust_panel.build_checks("sql", "live", PASSED, 5, 0.01))

    assert "123" in details["Row cap"]
    assert "7" in details["Time budget"]
    assert "5" in details["Rows returned"]
    assert list(details) == ["Model output", "Guard", "Row cap", "Engine", "Time budget", "Rows returned"]


def test_pandas_checks_use_code_constants(monkeypatch) -> None:
    monkeypatch.setattr(csv_backend, "_EXEC_TIMEOUT", 17)

    details = _details(trust_panel.build_checks("pandas", "live", None, 3, 0.2))

    assert "17" in details["Timeout"]
    assert list(details) == ["Model output", "Blocklist", "Isolation", "Timeout", "Rows returned"]
    assert details["Isolation"] == "separate process, copy of the data"


def test_cached_source_is_labeled() -> None:
    cached = _details(trust_panel.build_checks("sql", "cached", PASSED, 1, 0.0))
    live = _details(trust_panel.build_checks("sql", "live", PASSED, 1, 0.0))

    assert cached["Model output"] == "saved, executed live"
    assert live["Model output"] == "generated live"


def test_guard_rejection_is_shown() -> None:
    rejected = {"is_valid": False, "sanitized_query": "", "rejection_reason": "Only SELECT is allowed"}

    details = _details(trust_panel.build_checks("sql", "live", rejected, 0, 0.0))

    assert "Only SELECT is allowed" in details["Guard"]
    assert "passed" not in details["Guard"].lower()


def _write_metrics(path, contract: int = 2) -> str:
    path.write_text(json.dumps({"reports": {
        "v1": {"summary": {"sql": {"accuracy_rep0": 0.92, "accuracy_rep0_n": 25,
                                   "accuracy_rep0_wilson95": [0.7503, 0.9778]}}},
        "v2": {"summary": {"pandas": {"accuracy_rep0": 0.88, "accuracy_rep0_n": 25,
                                      "accuracy_rep0_wilson95": [0.7, 0.96]}},
               "run": {"pandas_exec_contract": contract}},
    }}))
    return str(path)


def test_eval_line_sql_reads_metrics(tmp_path) -> None:
    line = trust_panel.eval_line("sql", _write_metrics(tmp_path / "m.json"))

    assert line is not None
    assert "23/25" in line
    assert "0.75" in line and "0.98" in line


def test_eval_line_pandas_without_mismatch(tmp_path) -> None:
    line = trust_panel.eval_line("pandas", _write_metrics(tmp_path / "m.json", csv_backend.EXEC_CONTRACT))

    assert line is not None
    assert "22/25" in line
    assert "executor contract" not in line


def test_eval_line_flags_contract_mismatch(tmp_path) -> None:
    line = trust_panel.eval_line("pandas", _write_metrics(tmp_path / "m.json", contract=csv_backend.EXEC_CONTRACT - 1))

    assert line is not None
    assert f"Measured under executor contract {csv_backend.EXEC_CONTRACT - 1}" in line
    assert f"this app runs contract {csv_backend.EXEC_CONTRACT}" in line


def test_eval_line_missing_file_returns_none(tmp_path) -> None:
    assert trust_panel.eval_line("sql", str(tmp_path / "nope.json")) is None


def test_eval_line_missing_key_or_bad_json_returns_none(tmp_path) -> None:
    broken = tmp_path / "m.json"
    broken.write_text(json.dumps({"reports": {"v1": {"summary": {}}}}))
    assert trust_panel.eval_line("sql", str(broken)) is None
    broken.write_text("{not json")
    assert trust_panel.eval_line("sql", str(broken)) is None


def test_eval_line_reads_the_real_committed_metrics() -> None:
    """The committed metrics file has the keys the panel reads."""
    assert trust_panel.eval_line("sql") is not None
    assert trust_panel.eval_line("pandas") is not None


# --- the glanceable strip shown with every answer -------------------------------------------

def test_strip_for_a_saved_sql_answer() -> None:
    strip = trust_panel.strip("sql", "cached", PASSED, 4, 0.0123)

    assert ":green-badge[" in strip and "Guard passed" in strip
    assert "Saved model output" in strip and "executed live" in strip
    assert "Read-only engine" in strip
    assert "4 rows" in strip


def test_strip_for_a_live_answer_does_not_claim_saved() -> None:
    strip = trust_panel.strip("sql", "live", PASSED, 4, 0.01)

    assert "Live model output" in strip
    assert "Saved" not in strip


def test_strip_shows_a_rejection_in_red() -> None:
    rejected = {"is_valid": False, "sanitized_query": "", "rejection_reason": "Only SELECT is allowed"}

    strip = trust_panel.strip("sql", "live", rejected, 0, 0.0)

    assert ":red-badge[" in strip and "Guard rejected" in strip
    assert "Guard passed" not in strip


def test_strip_for_pandas_names_isolation_not_a_guard() -> None:
    strip = trust_panel.strip("pandas", "live", None, 1, 0.2)

    assert "Isolated process" in strip
    assert "Guard" not in strip
    assert "1 row" in strip and "1 rows" not in strip


def test_strip_is_short_and_leaves_limits_to_the_details(monkeypatch) -> None:
    monkeypatch.setattr(sql_guard, "MAX_ROWS", 123)

    strip = trust_panel.strip("sql", "live", PASSED, 5, 0.01)

    assert "123" not in strip  # limits live in the expandable details, not the strip
