"""End-to-end through the Streamlit app with the LLM stubbed out.

The real path runs (prompt build -> guard -> engine -> render); only
llm.query_llm is replaced, and requests.post is made to fail loudly so
any accidental network call breaks the test.
"""

import os

import pytest
import requests
from streamlit.testing.v1 import AppTest

import llm
import sqlite_backend

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")


@pytest.fixture
def run_app(monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network call attempted during an offline test")

    monkeypatch.setattr(requests, "post", _no_network)
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")

    def _run(response: dict, engine: str = "SQL (SQLite)", question: str = "test question"):
        monkeypatch.setattr(
            llm, "query_llm",
            lambda *args, **kwargs: dict(response, _debug={"llm_elapsed": 0.0}),
        )
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
        if engine != "SQL (SQLite)":
            at.sidebar.radio(key="engine_selector").set_value(engine).run()
        at.text_input(key="query_input").set_value(question).run()
        assert not at.exception, at.exception
        return at

    return _run


def test_sql_engine_answers_a_question(run_app) -> None:
    at = run_app({
        "sql": "SELECT city, COUNT(*) AS n FROM deed_transactions GROUP BY city ORDER BY n DESC LIMIT 3",
        "chart_config": {"chart_type": "bar", "x": "city", "y": "n", "color": None, "title": "t"},
        "explanation": "top cities",
    })
    assert not at.error
    assert len(at.dataframe[0].value) == 3


def test_pandas_engine_answers_a_question(run_app) -> None:
    at = run_app({
        "pandas_code": "result = df.groupby('city').size().reset_index(name='n').head(3)",
        "chart_config": None,
        "explanation": "top cities",
    }, engine="pandas")
    assert not at.error
    assert len(at.dataframe[0].value) == 3


def test_generated_write_is_rejected_and_data_unchanged(run_app) -> None:
    at = run_app({"sql": "DELETE FROM deed_transactions", "chart_config": None, "explanation": ""})
    assert any("Query rejected" in e.value for e in at.error)
    count = sqlite_backend.execute_query("SELECT COUNT(*) AS n FROM deed_transactions")
    assert count["n"].iloc[0] == 5000


def test_blocked_pandas_code_is_reported(run_app) -> None:
    at = run_app({"pandas_code": "import os\nresult = df", "chart_config": None,
                  "explanation": ""}, engine="pandas")
    assert any("Blocked pattern" in e.value for e in at.error)
