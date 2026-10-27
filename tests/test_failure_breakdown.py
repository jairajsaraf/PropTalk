"""evals/failure_breakdown.py: cause labels, and the pinned v1 report numbers
that evals/PREREGISTRATION_v2.md cites."""

import json
import os

import pytest

from evals.failure_breakdown import breakdown, classify

V1_REPORT = os.path.join(os.path.dirname(__file__), "..", "results", "eval_report.json")


def _trial(outcome: str, correct: bool = False, error: str = "", rep: int = 0, mode: str = "pandas") -> dict:
    return {"kind": "question", "mode": mode, "rep": rep, "outcome": outcome,
            "correct": correct, "error": error}


@pytest.mark.parametrize("trial, cause", [
    (_trial("executed", correct=True), "correct"),
    (_trial("executed"), "wrong_answer"),
    (_trial("exec_error", error="Expected DataFrame result, got int"), "scalar_result_rejected"),
    (_trial("exec_error", error="Execution error: name 'len' is not defined"), "builtin_not_defined"),
    (_trial("exec_error", error="Query execution timed out after 30 seconds."), "timeout"),
    (_trial("exec_error", error="Execution error: 'nope'"), "exec_error_other"),
    (_trial("blocked_validator"), "blocked_validator"),
    (_trial("refused"), "refused"),
    (_trial("infra_error"), "infra_error"),
])
def test_classify(trial: dict, cause: str) -> None:
    assert classify(trial) == cause


def test_classify_rejects_adversarial_trials() -> None:
    with pytest.raises(ValueError):
        classify({"kind": "adversarial", "outcome": "executed"})


def test_breakdown_filters_by_repetition_and_ignores_adversarial() -> None:
    report = {"trials": [
        _trial("executed", correct=True, rep=0), _trial("executed", rep=1),
        _trial("exec_error", error="name 'int' is not defined", rep=1, mode="sql"),
        {"kind": "adversarial", "mode": "pandas", "rep": 0, "outcome": "executed"},
    ]}
    assert breakdown(report) == {"pandas": {"correct": 1, "wrong_answer": 1},
                                 "sql": {"builtin_not_defined": 1}}
    assert breakdown(report, rep=0) == {"pandas": {"correct": 1}}


@pytest.mark.skipif(not os.path.exists(V1_REPORT), reason="v1 report is not in this checkout")
def test_v1_report_failure_numbers_cited_by_the_v2_preregistration() -> None:
    with open(V1_REPORT) as f:
        report = json.load(f)
    assert breakdown(report, rep=0)["pandas"] == {
        "builtin_not_defined": 4, "correct": 12, "scalar_result_rejected": 7, "wrong_answer": 2}
    assert breakdown(report)["pandas"] == {
        "builtin_not_defined": 14, "correct": 38, "scalar_result_rejected": 17, "wrong_answer": 6}
    assert breakdown(report)["sql"] == {"correct": 70, "wrong_answer": 5}
