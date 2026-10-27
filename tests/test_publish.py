"""evals/publish.py: metrics.json and the README results block.

The expensive part (offline re-score of every report) runs in `make ci`.
These tests check everything else cheaply, including that the committed
metrics and README block are current.
"""

import json
import os

import pytest

from evals import publish, run_eval

REPORTS = publish.discover_reports() if os.path.isdir(publish.RESULTS_DIR) else {}
needs_reports = pytest.mark.skipif(not REPORTS, reason="no eval reports in results/")


def test_text_hash_ignores_line_endings(tmp_path) -> None:
    lf, crlf = tmp_path / "a.json", tmp_path / "b.json"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    assert run_eval.sha256_text_file(str(lf)) == run_eval.sha256_text_file(str(crlf))
    assert run_eval.sha256_file(str(lf)) != run_eval.sha256_file(str(crlf))


def test_discover_reports_labels_and_order(tmp_path) -> None:
    for name in ("eval_report_v10.json", "eval_report.json", "eval_report_v2.json",
                 "metrics.json", "eval_report_backup.json", "notes.txt"):
        (tmp_path / name).write_text("{}")
    found = publish.discover_reports(str(tmp_path))
    assert list(found) == ["v1", "v2", "v10"]
    assert os.path.basename(found["v1"]) == "eval_report.json"


@pytest.mark.parametrize("value, text", [(0.625, "0.63"), (0.5, "0.50"), (0.9333, "0.93"),
                                         (0.0, "0.00"), (1.0, "1.00"), (0.3057, "0.31")])
def test_fmt2_rounds_half_up(value: float, text: str) -> None:
    assert publish.fmt2(value) == text


def test_apply_and_read_block_round_trip() -> None:
    readme = f"intro\n{publish.START_MARKER}\nold\n{publish.END_MARKER}\noutro\n"
    updated = publish.apply_block(readme, "new block\n")
    assert publish.read_block(updated) == "new block\n"
    assert updated.startswith("intro\n") and updated.endswith("outro\n")
    assert publish.apply_block(updated, "new block\n") == updated  # idempotent


@pytest.mark.parametrize("readme", ["no markers", f"{publish.END_MARKER} {publish.START_MARKER}"])
def test_missing_or_misordered_markers_raise(readme: str) -> None:
    with pytest.raises(ValueError, match="markers"):
        publish.apply_block(readme, "x")
    with pytest.raises(ValueError, match="markers"):
        publish.read_block(readme)


def test_count_from_rate_recovers_integers_and_rejects_inconsistent_input() -> None:
    assert publish._count(0.625, 8) == 5 and publish._count(0.92, 25) == 23
    assert publish._count(None, 25) is None
    with pytest.raises(AssertionError):
        publish._count(0.5, 7)


def _fake_metrics(reproduced: bool = True) -> dict:
    summary = {
        "accuracy_rep0": 0.8, "accuracy_rep0_n": 25, "accuracy_rep0_wilson95": [0.6, 0.9],
        "accuracy_all_trials": 0.8, "pass_hat_k": 0.8, "validator_pass_rate": 1.0,
        "exec_success_rate": 1.0, "adversarial_block_rate_rep0": 0.875,
        "adversarial_block_rate_rep0_n": 8, "adversarial_block_rate_rep0_wilson95": [0.5, 0.97],
        "adversarial_harm_trials": 0, "adversarial_trials": 24, "llm_latency_p50_s": 1.0,
        "llm_latency_p95_s": 2.0, "end_to_end_latency_p50_s": 1.5, "end_to_end_latency_p95_s": 2.5,
        "prompt_tokens_total": 1000, "completion_tokens_total": 50,
        "bars": {"accuracy_rep0": True, "validator_pass_rate": True,
                 "adversarial_block_rate_rep0": True, "adversarial_harm_trials": True},
    }
    run = {"model": "m", "model_listed_as": "models/m", "temperature": 0, "k": 3,
           "modes": ["sql"], "python": "3.13.0", "pandas_exec_contract": 2,
           "prereg_file": "evals/PREREGISTRATION.md"}
    return {"schema": 1, "generated_at_commit": "abc", "working_tree_dirty": False,
            "bars": run_eval.BARS,
            "reports": {"v1": {"file": "results/eval_report.json", "run": run,
                               "cases": {"questions": 25, "adversarial": 8},
                               "summary": {"sql": summary},
                               "failure_causes": {"rep0": {"sql": {"correct": 20, "wrong_answer": 5}},
                                                  "all_trials": {"sql": {"correct": 60, "wrong_answer": 15}}},
                               "outcomes": {"adversarial": {"sql": {
                                   "all_trials": {"blocked_validator": 21, "executed": 3},
                                   "rep0": {"blocked_validator": 7, "executed": 1}}}},
                               "reproduced": reproduced, "rescore_mismatches": [] if reproduced else ["x"]}}}


def test_render_results_contains_the_numbers_it_was_given() -> None:
    text = publish.render_results(_fake_metrics())
    for expected in ("0.80 (20/25), 95% CI 0.60–0.90", "0.88 (7/8)", "1,000 / 50", "0 of 24",
                     "`wrong_answer` | 5 / 15", "`blocked_validator` | 21 (7)", "reproduces exactly"):
        assert expected in text, expected
    assert "does not reproduce" in publish.render_results(_fake_metrics(reproduced=False))


def test_check_flags_stale_files_and_ignores_volatile_fields(tmp_path) -> None:
    metrics = _fake_metrics()
    metrics_path, readme_path = tmp_path / "metrics.json", tmp_path / "README.md"
    metrics_path.write_text(json.dumps(metrics))
    readme_path.write_text(publish.apply_block(
        f"{publish.START_MARKER}\n{publish.END_MARKER}\n", publish.render_results(metrics)))
    assert publish.check(metrics, str(metrics_path), str(readme_path)) == []

    moved = dict(metrics, generated_at_commit="def", working_tree_dirty=True)
    assert publish.check(moved, str(metrics_path), str(readme_path)) == []  # commit SHA is informational

    changed = _fake_metrics()
    changed["reports"]["v1"]["summary"]["sql"]["accuracy_rep0"] = 0.4
    problems = publish.check(changed, str(metrics_path), str(readme_path))
    assert any("metrics.json is stale" in p for p in problems)
    assert any("README results block is stale" in p for p in problems)

    problems = publish.check(_fake_metrics(reproduced=False), str(metrics_path), str(readme_path))
    assert any("does not reproduce" in p for p in problems)
    assert publish.check(metrics, str(tmp_path / "nope.json"), str(readme_path))[0].endswith("is missing")


@needs_reports
def test_committed_metrics_match_the_reports_without_re_executing_anything() -> None:
    """Cheap staleness check: everything derived from the report files by
    reading only. `make ci` additionally re-executes the stored code."""
    with open(publish.METRICS_PATH) as f:
        committed = json.load(f)
    fresh = publish.build_metrics(rescore=False)
    assert list(committed["reports"]) == list(fresh["reports"])
    for label, rep in committed["reports"].items():
        expected = dict(fresh["reports"][label], reproduced=rep["reproduced"],
                        rescore_mismatches=rep["rescore_mismatches"])
        assert rep == expected, label
        assert rep["reproduced"] is True and rep["rescore_mismatches"] == []
    assert committed["bars"] == run_eval.BARS


@needs_reports
def test_committed_readme_block_is_rendered_from_the_committed_metrics() -> None:
    with open(publish.METRICS_PATH) as f:
        committed = json.load(f)
    with open(publish.README_PATH) as f:
        readme = f.read()
    assert publish.read_block(readme) == publish.render_results(committed)
    assert "\n## Limitations\n" in readme  # the generated block links to it


@needs_reports
def test_report_files_use_lf_line_endings_in_git_not_necessarily_on_disk() -> None:
    """Hashes are computed after folding CRLF, so a Windows checkout agrees."""
    for rep in publish.build_metrics(rescore=False)["reports"].values():
        assert len(rep["sha256_lf"]) == 64


def test_live_report_writer_uses_lf(tmp_path) -> None:
    path = tmp_path / "r.json"
    run_eval._write_report({"a": [1, 2], "b": {"c": 3}}, str(path))
    assert b"\r" not in path.read_bytes()
