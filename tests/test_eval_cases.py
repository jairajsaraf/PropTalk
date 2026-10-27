"""The eval's cases are well-formed and every reference answer is real.

Each question carries a pandas reference (which defines the expected
answer) and an SQL reference. Both run through the production paths, and
the SQL answer must match the pandas one under the eval's own scoring.
"""

import json
import os

import pytest

import config
import csv_backend
import sqlite_backend
from evals.scoring import frames_match, scalar_matches
from sql_guard import validate_query

EVALS = os.path.join(os.path.dirname(__file__), "..", "evals")
TABLES = {t.display_name: t for t in config.TABLE_REGISTRY}
ALLOWED = [t.sqlite_table for t in config.TABLE_REGISTRY]


def _load(name: str) -> list[dict]:
    with open(os.path.join(EVALS, name)) as f:
        return [json.loads(line) for line in f if line.strip()]


QUESTIONS = _load("questions.jsonl")
ADVERSARIAL = _load("adversarial.jsonl")


def test_case_files_are_well_formed() -> None:
    ids = [c["id"] for c in QUESTIONS + ADVERSARIAL]
    assert len(ids) == len(set(ids)), "duplicate case ids"
    assert len(QUESTIONS) == 25 and len(ADVERSARIAL) == 8
    for c in QUESTIONS:
        assert c["table"] in TABLES
        assert c["kind"] in ("scalar", "frame")
        assert isinstance(c["ordered"], bool)
    for c in ADVERSARIAL:
        assert c["table"] in TABLES


@pytest.mark.parametrize("case", QUESTIONS, ids=[c["id"] for c in QUESTIONS])
def test_reference_answers_run_and_agree(case: dict) -> None:
    table = TABLES[case["table"]]
    df = csv_backend.CsvBackend(config.get_csv_tables()).load_data(case["table"])
    expected = csv_backend.execute_pandas(df, case["reference_pandas"], timeout=30)
    assert not expected.empty
    if case["kind"] == "scalar":
        assert expected.shape == (1, 1)

    ok, sanitized, reason = validate_query(case["reference_sql"], ALLOWED)
    assert ok, reason
    assert table.sqlite_table in sanitized
    via_sql = sqlite_backend.execute_query(sanitized)

    if case["kind"] == "scalar":
        assert scalar_matches(expected, via_sql)
    else:
        assert frames_match(expected, via_sql, ordered=case["ordered"])
