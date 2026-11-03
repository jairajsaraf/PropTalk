"""End-to-end through the Streamlit app with the LLM stubbed out.

The real path runs (prompt build -> guard -> engine -> render); only
llm.query_llm is replaced, and requests.post is made to fail loudly so
any accidental network call breaks the test.
"""

import json
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


def test_history_click_restores_question_table_and_engine(run_app) -> None:
    """Regression: clicking a history entry crashed the app (widget state was
    set after the widget existed), and entries ignored the engine, so asking
    the same question in the other engine overwrote the first entry."""
    at = run_app({"sql": "SELECT city FROM deed_transactions LIMIT 3",
                  "pandas_code": "result = df.head(3)", "chart_config": None, "explanation": ""},
                 question="first question")
    at.sidebar.radio(key="engine_selector").set_value("pandas").run()
    at.sidebar.radio(key="table_selector").set_value("MLS Listings").run()
    at.run()  # the sidebar renders before a run saves its entry; it shows on the next run
    history = {b.key: b for b in at.button if (b.key or "").startswith("history_")}
    assert sorted(history) == ["history_0", "history_1", "history_2"]  # sql/deed, pandas/deed, pandas/mls

    history["history_0"].click().run()  # the first (SQL, Deed Transactions) entry
    assert not at.exception, at.exception
    assert at.sidebar.radio(key="engine_selector").value == "SQL (SQLite)"
    assert at.sidebar.selectbox(key="table_selector").value == "Deed Transactions"
    assert at.text_input(key="query_input").value == "first question"


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


def test_pandas_engine_accepts_a_scalar_answer(run_app) -> None:
    at = run_app({
        "pandas_code": "result = int((df['cash_purchase'] == 'Y').sum())",
        "chart_config": None,
        "explanation": "cash purchases",
    }, engine="pandas")
    assert not at.error
    assert at.dataframe[0].value.iloc[0, 0] == 1358


# ---------------------------------------------------------------------------
# Saved example answers, per-session cap, plain errors
# ---------------------------------------------------------------------------

EXAMPLE = "Show me the top 10 cities by transaction volume"
EXAMPLE_SQL = (
    "SELECT city, COUNT(*) AS n FROM deed_transactions GROUP BY city ORDER BY n DESC LIMIT 10"
)


@pytest.fixture
def offline_app(monkeypatch, tmp_path):
    """Run the app with no network, a temp demo cache, and query_llm replaced."""
    import demo_cache

    def _no_network(*args, **kwargs):
        raise AssertionError("network call attempted during an offline test")

    monkeypatch.setattr(requests, "post", _no_network)
    monkeypatch.setattr(demo_cache, "CACHE_PATH", str(tmp_path / "demo_cache.json"))
    calls: list[tuple] = []

    def _run(question: str, *, key: str | None, cached: bool, llm_raises: Exception | None = None,
             used: int = 0):
        if key:
            monkeypatch.setenv("LLM_API_KEY", key)
        else:
            monkeypatch.delenv("LLM_API_KEY", raising=False)
        if cached:
            (tmp_path / "demo_cache.json").write_text(json.dumps({
                "model": "m", "generated_at": "2026-11-03T00:00:00+00:00",
                "entries": [{"question": EXAMPLE, "table_id": "Deed Transactions", "mode": "sql",
                             "response": {"sql": EXAMPLE_SQL, "explanation": "top cities",
                                          "chart_config": {"chart_type": "bar", "x": "city",
                                                           "y": "n", "color": None, "title": "t"}}}],
            }))

        def _fake(*args, **kwargs):
            calls.append(args)
            if llm_raises is not None:
                raise llm_raises
            return {"sql": EXAMPLE_SQL, "chart_config": None, "explanation": "", "_debug": {}}

        monkeypatch.setattr(llm, "query_llm", _fake)
        at = AppTest.from_file(APP, default_timeout=60)
        if used:
            at.session_state["live_calls_used"] = used
        at.run()
        at.text_input(key="query_input").set_value(question).run()
        return at, calls

    return _run


def test_example_served_from_cache_without_key(offline_app) -> None:
    messy = "  show ME the top 10 cities by   transaction volume "
    at, calls = offline_app(messy, key=None, cached=True,
                            llm_raises=AssertionError("query_llm must not be called"))

    assert not at.exception, at.exception
    assert len(at.get("plotly_chart")) == 1
    assert calls == []
    assert at.session_state["last_result"]["source"] == "cached"
    assert "live_calls_used" not in at.session_state  # saved answers cost no live budget


def test_429_shows_plain_message(offline_app) -> None:
    response = requests.Response()
    response.status_code = 429
    at, _ = offline_app("some typed question", key="k", cached=False,
                        llm_raises=requests.HTTPError("429", response=response))

    assert not at.exception, at.exception
    shown = [e.value for e in at.error] + [i.value for i in at.info]
    assert any("rate limit is reached" in text and "still work" in text for text in shown), shown
    assert not any("Traceback" in text for text in shown)


def test_typed_question_without_key_says_live_is_off(offline_app) -> None:
    at, calls = offline_app("some typed question", key=None, cached=False)

    assert not at.exception, at.exception
    assert calls == []
    assert any("Live questions are off in this deployment" in i.value for i in at.info)


def test_exhausted_budget_blocks_live_call(offline_app) -> None:
    import session_budget

    at, calls = offline_app("some typed question", key="k", cached=False,
                            used=session_budget.MAX_LIVE_CALLS_PER_SESSION)

    assert not at.exception, at.exception
    assert calls == []
    assert any(str(session_budget.MAX_LIVE_CALLS_PER_SESSION) in i.value for i in at.info)


def test_live_call_consumes_budget_and_is_labeled_live(offline_app) -> None:
    at, calls = offline_app("some typed question", key="k", cached=False)

    assert not at.exception, at.exception
    assert len(calls) == 1
    assert at.session_state["live_calls_used"] == 1
    assert at.session_state["last_result"]["source"] == "live"


def _panel(at):
    panels = [e for e in at.expander if e.label == "How this answer was produced"]
    assert len(panels) == 1, [e.label for e in at.expander]
    return panels[0]


def test_trust_panel_labels_a_saved_answer(offline_app) -> None:
    at, _ = offline_app(EXAMPLE, key=None, cached=True)

    assert not at.exception, at.exception
    text = " ".join(m.value for m in _panel(at).markdown)
    assert "saved, executed live" in text
    assert "Guard" in text and "passed" in text


def test_trust_panel_labels_a_live_answer(offline_app) -> None:
    at, _ = offline_app("some typed question", key="k", cached=False)

    assert not at.exception, at.exception
    assert "generated live" in " ".join(m.value for m in _panel(at).markdown)


def test_trust_panel_shows_a_guard_rejection(run_app) -> None:
    at = run_app({"sql": "DELETE FROM deed_transactions", "chart_config": None, "explanation": ""})

    assert [e.value for e in at.error if "Query rejected" in e.value]
    text = " ".join(m.value for m in _panel(at).markdown)
    assert "rejected" in text
