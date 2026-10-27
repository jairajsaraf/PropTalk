"""Why question trials failed, by cause, from a saved eval report.

    python -m evals.failure_breakdown results/eval_report.json [--rep 0]

A failed trial is not always a wrong answer: the executor can reject valid
code. This separates the two, so a headline accuracy is not read as "how
often the model reasons wrongly".
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys

_UNDEFINED_RE = re.compile(r"name '\w+' is not defined")


def classify(trial: dict) -> str:
    """Cause label for one question trial."""
    if trial["kind"] != "question":
        raise ValueError("only question trials are classified")
    outcome = trial["outcome"]
    if outcome == "infra_error":
        return "infra_error"
    if trial.get("correct"):
        return "correct"
    if outcome == "executed":
        return "wrong_answer"
    if outcome == "exec_error":
        error = trial.get("error", "")
        if "Expected DataFrame result" in error:
            return "scalar_result_rejected"
        if _UNDEFINED_RE.search(error):
            return "builtin_not_defined"
        if "timed out" in error:
            return "timeout"
        return "exec_error_other"
    return outcome  # blocked_validator, refused, unparseable, llm_error


def breakdown(report: dict, rep: int | None = None) -> dict[str, dict[str, int]]:
    """Counts of each cause per mode, optionally for one repetition only."""
    counts: dict[str, collections.Counter] = {}
    for trial in report["trials"]:
        if trial["kind"] != "question" or (rep is not None and trial["rep"] != rep):
            continue
        counts.setdefault(trial["mode"], collections.Counter())[classify(trial)] += 1
    return {mode: dict(sorted(c.items())) for mode, c in sorted(counts.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report")
    parser.add_argument("--rep", type=int, default=None, help="only this repetition")
    args = parser.parse_args(argv)
    with open(args.report) as f:
        report = json.load(f)
    print(json.dumps(breakdown(report, args.rep), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
