"""evals/scoring.py: the answer-matching and statistics rules the eval uses."""

import math

import pandas as pd
import pytest

from evals.scoring import (
    frames_match,
    normalize_value,
    pass_hat_k,
    percentile,
    scalar_matches,
    values_equal,
    wilson_interval,
)


@pytest.mark.parametrize("successes, n, low, high", [
    (0, 10, 0.0, 0.2775),
    (10, 10, 0.7225, 1.0),
    (8, 10, 0.4902, 0.9433),
    (20, 25, 0.6087, 0.9114),
])
def test_wilson_interval_reference_values(successes, n, low, high) -> None:
    got_low, got_high = wilson_interval(successes, n)
    assert math.isclose(got_low, low, abs_tol=5e-4)
    assert math.isclose(got_high, high, abs_tol=5e-4)


@pytest.mark.parametrize("successes, n", [(1, 0), (-1, 5), (6, 5)])
def test_wilson_interval_rejects_bad_input(successes, n) -> None:
    with pytest.raises(ValueError):
        wilson_interval(successes, n)


def test_percentile_nearest_rank() -> None:
    values = list(range(1, 101))
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 95
    assert percentile([3.0], 95) == 3.0
    assert percentile([5, 1, 3], 50) == 3
    with pytest.raises(ValueError):
        percentile([], 50)


def test_pass_hat_k() -> None:
    trials = {"a": [True, True, True], "b": [True, False, True]}
    assert pass_hat_k(trials, 1) == 1.0
    assert pass_hat_k(trials, 3) == 0.5
    with pytest.raises(ValueError, match="fewer than 4"):
        pass_hat_k(trials, 4)


@pytest.mark.parametrize("a, b, equal", [
    (100.0, 100.00001, True),
    (100, 101, False),
    (0.001, 0.009, True),          # inside the 0.01 absolute tolerance
    ("2024-02-15 00:00:00", pd.Timestamp("2024-02-15"), True),  # SQLite text vs pandas
    ("2024-02", pd.Timestamp("2024-02-01"), True),              # strftime month vs timestamp
    (pd.Period("2024-02", "M"), "2024-02", True),
    (None, float("nan"), True),
    (None, 0.0, False),
    (True, 1, True),
    ("HOUSTON", " HOUSTON ", True),
    ("HOUSTON", "houston", False),
    ("2024", 2024, True),           # SQLite strftime('%Y') text vs pandas int
    ("-3.5", -3.5, True),
    ("MLS-100001", "MLS-100001", True),
    ("77001A", 77001, False),
])
def test_values_equal(a, b, equal) -> None:
    assert values_equal(a, b) is equal


def test_normalize_value_keeps_non_midnight_times() -> None:
    assert normalize_value(pd.Timestamp("2024-02-15 13:30")) == "2024-02-15T13:30:00"


def test_scalar_matches() -> None:
    assert scalar_matches(42.0, pd.DataFrame({"avg": [42.000001]}))
    assert scalar_matches(42.0, pd.DataFrame({"city": ["AUSTIN"], "avg": [42.0]}))
    assert scalar_matches(pd.DataFrame({"x": [7]}), pd.DataFrame({"n": [7]}))
    assert not scalar_matches(42.0, pd.DataFrame({"avg": [42.0, 42.0]}))
    assert not scalar_matches(42.0, pd.DataFrame({"avg": [43.0]}))


def _frame(**cols) -> pd.DataFrame:
    return pd.DataFrame(cols)


def test_frames_match_ignores_names_and_extra_columns() -> None:
    expected = _frame(city=["A", "B"], n=[1, 2])
    assert frames_match(expected, _frame(town=["A", "B"], count=[1, 2]))
    assert frames_match(expected, _frame(count=[1, 2], extra=[9, 9], town=["A", "B"]))


def test_frames_match_row_order() -> None:
    expected = _frame(city=["A", "B"], n=[1, 2])
    reversed_rows = _frame(city=["B", "A"], n=[2, 1])
    assert frames_match(expected, reversed_rows)
    assert not frames_match(expected, reversed_rows, ordered=True)


def test_frames_match_requires_row_alignment() -> None:
    """Each column matching as a set is not enough; rows must line up."""
    expected = _frame(city=["A", "B"], n=[1, 2])
    assert not frames_match(expected, _frame(city=["A", "B"], n=[2, 1]))


def test_frames_match_backtracks_over_ambiguous_columns() -> None:
    expected = _frame(a=[1, 2], b=[2, 1])
    assert frames_match(expected, _frame(x=[2, 1], y=[1, 2]), ordered=True)


@pytest.mark.parametrize("actual", [
    _frame(city=["A", "B", "C"], n=[1, 2, 3]),   # extra row
    _frame(city=["A", "B"]),                     # missing column
    _frame(city=["A", "B"], n=[1, 3]),           # wrong value
])
def test_frames_match_failures(actual) -> None:
    assert not frames_match(_frame(city=["A", "B"], n=[1, 2]), actual)


def test_frames_match_across_engines_dates() -> None:
    pandas_out = _frame(month=pd.to_datetime(["2024-01-01", "2024-02-01"]), n=[5, 6])
    sqlite_out = _frame(sale_month=["2024-01", "2024-02"], txn_count=[5, 6])
    assert frames_match(pandas_out, sqlite_out, ordered=True)
