"""scripts/build_demo_cache.py: build and verify the saved example answers (offline, stubbed model)."""

import importlib.util
import os

import config

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "build_demo_cache.py")
_spec = importlib.util.spec_from_file_location("build_demo_cache", SCRIPT)
build_demo_cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_demo_cache)


def _fake_model(question, schema_info, mode, table_name, model=None) -> dict:
    code_key = "sql" if mode == "sql" else "pandas_code"
    return {code_key: "x", "chart_config": None, "explanation": "e", "_debug": {"raw_body": "secret"}}


def test_build_calls_every_table_mode_question_once_and_drops_debug() -> None:
    calls: list[tuple] = []
    sleeps: list[float] = []

    def model(*args, **kwargs):
        calls.append(args)
        return _fake_model(*args, **kwargs)

    entries = build_demo_cache.build_entries(model, sleeps.append, interval=5.0)

    expected = sum(len(t.example_questions) for t in config.TABLE_REGISTRY) * 2
    assert len(entries) == len(calls) == expected == 16
    assert all("_debug" not in e["response"] for e in entries)
    assert {e["mode"] for e in entries} == {"sql", "pandas"}
    assert len(sleeps) == expected - 1 and set(sleeps) == {5.0}  # spaced, none after the last


def test_verify_keeps_good_entries_and_reports_bad_ones() -> None:
    good_sql = {"question": "q1", "table_id": "Deed Transactions", "mode": "sql",
                "response": {"sql": "SELECT city, COUNT(*) AS n FROM deed_transactions GROUP BY city LIMIT 5"}}
    rejected = {"question": "q2", "table_id": "Deed Transactions", "mode": "sql",
                "response": {"sql": "DELETE FROM deed_transactions"}}
    empty = {"question": "q3", "table_id": "Deed Transactions", "mode": "sql",
             "response": {"sql": "SELECT city FROM deed_transactions WHERE 1 = 0"}}
    good_pandas = {"question": "q4", "table_id": "MLS Listings", "mode": "pandas",
                   "response": {"pandas_code": "result = df.head(3)"}}
    broken_pandas = {"question": "q5", "table_id": "MLS Listings", "mode": "pandas",
                     "response": {"pandas_code": "result = df.nope"}}

    kept, dropped = build_demo_cache.verify_entries(
        [good_sql, rejected, empty, good_pandas, broken_pandas])

    assert [e["question"] for e in kept] == ["q1", "q4"]
    assert sorted(e["question"] for e, _ in dropped) == ["q2", "q3", "q5"]
    assert all(reason for _, reason in dropped)
