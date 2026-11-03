"""'How this answer was produced': what happened to the model's code on its way
to the result, using only values the pipeline already has.

Every limit shown is read from the code's own constants, so the panel cannot
drift from what the engine enforces. The one quality number comes from
results/metrics.json (written by evals.publish), never from a literal here.
"""

import json
import os
from dataclasses import dataclass

import csv_backend
import sql_guard
import sqlite_backend

METRICS_PATH = "results/metrics.json"
EVAL_URL = "https://github.com/jairajsaraf/PropTalk#evaluation-results"


@dataclass(frozen=True)
class TrustCheck:
    label: str
    detail: str


def _model_output(source: str) -> TrustCheck:
    detail = "saved, executed live" if source == "cached" else "generated live"
    return TrustCheck("Model output", detail)


def build_checks(mode: str, source: str, validation_result: dict | None,
                 row_count: int, query_elapsed: float) -> list[TrustCheck]:
    """One check per control that applied to this answer."""
    rows = TrustCheck("Rows returned", f"{row_count:,} in {query_elapsed:.2f}s")
    if mode == "sql":
        if validation_result is None:
            guard = "not reached"
        elif validation_result.get("is_valid"):
            guard = "SELECT-only, table whitelist: passed"
        else:
            guard = f"rejected: {validation_result.get('rejection_reason', 'unknown reason')}"
        return [
            _model_output(source),
            TrustCheck("Guard", guard),
            TrustCheck("Row cap", f"{sql_guard.MAX_ROWS:,} rows"),
            TrustCheck("Engine", "read-only: authorizer allowlist + PRAGMA query_only"),
            TrustCheck("Time budget", f"{sqlite_backend.QUERY_TIME_BUDGET_SECONDS} s"),
            rows,
        ]
    return [
        _model_output(source),
        TrustCheck("Blocklist", "generated code is screened before it runs"),
        TrustCheck("Isolation", "separate process, copy of the data"),
        TrustCheck("Timeout", f"{csv_backend._EXEC_TIMEOUT} s"),
        rows,
    ]


def _resolve(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(os.path.dirname(os.path.abspath(__file__)), path)


def eval_line(mode: str, metrics_path: str = METRICS_PATH) -> str | None:
    """One sentence on how this engine scored in the preregistered eval, or None
    if the metrics file or any key is missing."""
    try:
        with open(_resolve(metrics_path), encoding="utf-8") as fh:
            reports = json.load(fh)["reports"]
        if mode == "sql":
            summary = reports["v1"]["summary"]["sql"]
            contract = None
        else:
            summary = reports["v2"]["summary"]["pandas"]
            contract = reports["v2"]["run"]["pandas_exec_contract"]
        n = int(summary["accuracy_rep0_n"])
        correct = round(float(summary["accuracy_rep0"]) * n)
        lo, hi = summary["accuracy_rep0_wilson95"]
        line = (f"In the preregistered eval this engine answered {correct}/{n} questions "
                f"correctly (95% CI {lo:.2f}–{hi:.2f}).")
        if contract is not None and contract != csv_backend.EXEC_CONTRACT:
            line += (f" Measured under executor contract {contract}; "
                     f"this app runs contract {csv_backend.EXEC_CONTRACT}.")
        return line
    except (OSError, ValueError, KeyError, TypeError):
        return None


def render(mode: str, source: str, validation_result: dict | None,
           row_count: int, query_elapsed: float) -> None:
    """Draw the panel. Imported lazily so the helpers above stay Streamlit-free."""
    import streamlit as st

    with st.expander("How this answer was produced", expanded=True):
        for check in build_checks(mode, source, validation_result, row_count, query_elapsed):
            label_col, detail_col = st.columns([1, 4])
            label_col.markdown(f"**{check.label}**")
            detail_col.markdown(check.detail)
        line = eval_line(mode)
        if line:
            st.caption(f"{line} [Method and results]({EVAL_URL})")
