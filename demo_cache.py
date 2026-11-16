"""Saved model output for the example questions.

An entry stores only what the model returned (code, chart config, explanation).
The code still goes through the guard and the engine on every request, so a
cached answer is "saved model output, executed live". Regenerate the file with
scripts/build_demo_cache.py.
"""

import json
import os

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:  # pragma: no cover - streamlit is a runtime dependency
    HAS_STREAMLIT = False

CACHE_PATH: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_cache.json")


def normalize(question: str) -> str:
    """Strip, collapse internal whitespace, casefold."""
    return " ".join(question.split()).casefold()


def _read_entries(path: str, mtime_ns: int, size: int) -> list[dict]:
    # mtime_ns and size are cache keys only: a rewritten file is re-read.
    with open(path, encoding="utf-8") as fh:
        return list(json.load(fh)["entries"])


if HAS_STREAMLIT:
    _read_entries = st.cache_data(_read_entries)


def lookup(question: str, table_id: str, mode: str) -> dict | None:
    """Return a copy of the saved response for this question, or None.

    A missing or unreadable cache file is a miss, never an error.
    """
    path = CACHE_PATH
    try:
        stat = os.stat(path)
        entries = _read_entries(path, stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    wanted = normalize(question)
    for entry in entries:
        if (entry.get("table_id") == table_id and entry.get("mode") == mode
                and normalize(str(entry.get("question", ""))) == wanted):
            response = dict(entry["response"])
            response.pop("_debug", None)
            return response
    return None
