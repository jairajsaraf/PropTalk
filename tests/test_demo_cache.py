"""demo_cache: saved model output for the example questions."""

import json
import os

import pytest

import demo_cache

QUESTION = "Show me the top 10 cities by transaction volume"


def _write_cache(path, response: dict) -> None:
    path.write_text(json.dumps({
        "model": "test-model",
        "generated_at": "2026-11-03T00:00:00+00:00",
        "entries": [{
            "question": QUESTION,
            "table_id": "Deed Transactions",
            "mode": "sql",
            "response": response,
        }],
    }))


@pytest.fixture
def cache_file(tmp_path, monkeypatch):
    path = tmp_path / "demo_cache.json"
    monkeypatch.setattr(demo_cache, "CACHE_PATH", str(path))
    return path


def test_lookup_hit_ignores_case_and_spaces(cache_file) -> None:
    _write_cache(cache_file, {"sql": "SELECT 1", "chart_config": None, "explanation": "x"})

    hit = demo_cache.lookup("  show ME the top 10 cities by   transaction volume ",
                            "Deed Transactions", "sql")

    assert isinstance(hit, dict)
    assert hit["sql"] == "SELECT 1"


def test_lookup_miss_returns_none(cache_file) -> None:
    _write_cache(cache_file, {"sql": "SELECT 1", "chart_config": None, "explanation": ""})

    assert demo_cache.lookup("a different question", "Deed Transactions", "sql") is None
    assert demo_cache.lookup(QUESTION, "MLS Listings", "sql") is None
    assert demo_cache.lookup(QUESTION, "Deed Transactions", "pandas") is None


def test_lookup_missing_file_returns_none(cache_file) -> None:
    assert demo_cache.lookup(QUESTION, "Deed Transactions", "sql") is None


def test_lookup_strips_debug(cache_file) -> None:
    _write_cache(cache_file, {"sql": "SELECT 1", "chart_config": None, "explanation": "",
                              "_debug": {"raw_body": "secret"}})

    hit = demo_cache.lookup(QUESTION, "Deed Transactions", "sql")

    assert hit is not None
    assert "_debug" not in hit


def test_lookup_returns_a_copy(cache_file) -> None:
    _write_cache(cache_file, {"sql": "SELECT 1", "chart_config": None, "explanation": ""})

    first = demo_cache.lookup(QUESTION, "Deed Transactions", "sql")
    first["sql"] = "DROP TABLE x"

    assert demo_cache.lookup(QUESTION, "Deed Transactions", "sql")["sql"] == "SELECT 1"


def test_lookup_sees_a_rewritten_file(cache_file) -> None:
    _write_cache(cache_file, {"sql": "SELECT 1", "chart_config": None, "explanation": ""})
    assert demo_cache.lookup(QUESTION, "Deed Transactions", "sql")["sql"] == "SELECT 1"

    _write_cache(cache_file, {"sql": "SELECT 2", "chart_config": None, "explanation": ""})
    stat = os.stat(cache_file)  # filesystem timestamps can be coarser than two quick writes
    os.utime(cache_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    assert demo_cache.lookup(QUESTION, "Deed Transactions", "sql")["sql"] == "SELECT 2"
