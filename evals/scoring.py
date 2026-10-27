"""Scoring for the PropTalk eval: answer matching, confidence intervals,
latency percentiles, and pass^k.

Pure functions with no network or file I/O, shared by the live eval run and
the offline re-score so both apply exactly the same rules.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Sequence

import pandas as pd

REL_TOL = 1e-4
ABS_TOL = 0.01

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]00:00:00(?:\.0+)?)?$")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (default 95%)."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100); no interpolation."""
    if not values:
        raise ValueError("values must be non-empty")
    ordered = sorted(values)
    rank = math.ceil(q / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


def pass_hat_k(trials: dict[str, list[bool]], k: int) -> float:
    """Fraction of cases whose first k trials all passed (pass^k)."""
    if not trials:
        raise ValueError("trials must be non-empty")
    short = [case for case, runs in trials.items() if len(runs) < k]
    if short:
        raise ValueError(f"fewer than {k} trials for: {', '.join(sorted(short))}")
    return sum(all(runs[:k]) for runs in trials.values()) / len(trials)


def normalize_value(value: object) -> object:
    """Map engine-specific representations onto one comparable form.

    Numbers and booleans become float; missing values become None; dates
    become 'YYYY-MM-DD' whether they arrive as Timestamps (pandas) or ISO
    text (SQLite), and a bare 'YYYY-MM' month is read as its first day.
    Digit-only strings become numbers, since SQLite's strftime('%Y', ...)
    returns '2024' where pandas returns 2024.
    """
    if value is None:
        return None
    if isinstance(value, pd.Period):
        value = value.start_time
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        if pd.isna(value):
            return None
        ts = pd.Timestamp(value)
        return ts.strftime("%Y-%m-%d") if ts == ts.normalize() else ts.isoformat()
    if isinstance(value, str):
        text = value.strip()
        if _MONTH_RE.match(text):
            return f"{text}-01"
        if _DATE_RE.match(text):
            return text[:10]
        if _NUMBER_RE.match(text):
            return float(text)
        return text
    if isinstance(value, bool):
        return float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)) or hasattr(value, "__float__"):
        return float(value)
    return value


def values_equal(a: object, b: object, rel_tol: float = REL_TOL, abs_tol: float = ABS_TOL) -> bool:
    """Compare two values after normalization, with numeric tolerance."""
    a, b = normalize_value(a), normalize_value(b)
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)
    return a == b


def scalar_matches(expected: object, actual: pd.DataFrame) -> bool:
    """A scalar answer matches when the result has exactly one row and at
    least one of its cells equals the expected value."""
    if isinstance(expected, pd.DataFrame):
        if expected.shape != (1, 1):
            raise ValueError("expected scalar must be a value or a 1x1 frame")
        expected = expected.iat[0, 0]
    if len(actual) != 1:
        return False
    return any(values_equal(expected, cell) for cell in actual.iloc[0].tolist())


def _sort_key(value: object) -> tuple:
    if value is None:
        return (0, 0)
    if isinstance(value, float):
        return (1, value)
    return (2, str(value))


def _columns_equal(a: list, b: list) -> bool:
    return len(a) == len(b) and all(values_equal(x, y) for x, y in zip(a, b))


def frames_match(expected: pd.DataFrame, actual: pd.DataFrame, ordered: bool = False) -> bool:
    """A frame answer matches when row counts are equal and every expected
    column can be paired with a distinct actual column (names ignored) so
    that the rows line up value by value. Extra actual columns are allowed.
    Row order matters only when `ordered` is True.
    """
    if len(expected) != len(actual):
        return False
    exp_cols = [[normalize_value(v) for v in expected[c].tolist()] for c in expected.columns]
    act_cols = [[normalize_value(v) for v in actual.iloc[:, i].tolist()] for i in range(actual.shape[1])]
    if len(exp_cols) > len(act_cols):
        return False

    # Candidate pairings: same multiset of values (cheap filter before rows).
    candidates = [
        [j for j, act in enumerate(act_cols)
         if _columns_equal(sorted(exp, key=_sort_key), sorted(act, key=_sort_key))]
        for exp in exp_cols
    ]

    def rows_match(mapping: list[int]) -> bool:
        exp_rows = list(zip(*exp_cols))
        act_rows = list(zip(*(act_cols[j] for j in mapping)))
        if not ordered:
            exp_rows.sort(key=lambda r: tuple(map(_sort_key, r)))
            act_rows.sort(key=lambda r: tuple(map(_sort_key, r)))
        return all(_columns_equal(list(e), list(a)) for e, a in zip(exp_rows, act_rows))

    def search(i: int, used: list[int]) -> bool:
        if i == len(exp_cols):
            return rows_match(used)
        return any(search(i + 1, used + [j]) for j in candidates[i] if j not in used)

    return search(0, [])
