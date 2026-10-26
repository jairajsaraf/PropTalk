"""csv_backend: the pandas blocklist, the empty-builtins exec, and the
subprocess timeout.

The blocklist is a denylist of regexes, not a sandbox. The xfail test below
is a real, unfixed gap kept on purpose as evidence of that.
"""

import time

import pandas as pd
import pytest

import csv_backend


@pytest.mark.parametrize("code", [
    "import os\nresult = df",
    "result = __import__('os')",
    "result = df.__class__",
    "result = open('/etc/passwd').read()",
    "result = pd.read_csv('/etc/passwd')",
    "result = pd.read_pickle('x.pkl')",
    "result = pd.read_json('x.json')",
    "result = pd.read_html('x.html')",
    "df.to_csv('out.csv')\nresult = df",
    "df.to_pickle('out.pkl')\nresult = df",
    "df.to_parquet('out.parquet')\nresult = df",
    "df.to_json('out.json')\nresult = df",
    "result = eval('df')",
    "exec('x = 1')\nresult = df",
    "result = getattr(df, 'head')()",
    "result = globals()",
    "result = os.system('id')",
    "result = subprocess",
    "breakpoint()\nresult = df",
    "result = requests.get('http://example.com')",
])
def test_blocklisted_code_is_rejected_before_execution(deed_df, code: str) -> None:
    with pytest.raises(ValueError, match="Blocked pattern"):
        csv_backend.execute_pandas(deed_df, code, timeout=5)


def test_builtins_are_unavailable(deed_df) -> None:
    with pytest.raises(ValueError, match="name 'len' is not defined"):
        csv_backend.execute_pandas(deed_df, "result = df.head(len(df))", timeout=5)


def test_infinite_loop_times_out(deed_df) -> None:
    start = time.monotonic()
    with pytest.raises(ValueError, match="timed out after 1 seconds"):
        csv_backend.execute_pandas(deed_df, "while True:\n    pass", timeout=1)
    assert time.monotonic() - start < 5


def test_large_result_is_not_mistaken_for_a_timeout(deed_df) -> None:
    """Regression: the parent used to join the worker before reading the
    queue, so any result over the pipe buffer looked like a timeout."""
    out = csv_backend.execute_pandas(deed_df, "result = df", timeout=10)
    assert len(out) == 5000


def test_result_is_capped_at_10000_rows(deed_df) -> None:
    out = csv_backend.execute_pandas(deed_df, "result = pd.concat([df, df, df])", timeout=10)
    assert len(out) == 10000


def test_series_result_becomes_a_frame(deed_df) -> None:
    out = csv_backend.execute_pandas(deed_df, "result = df['city'].value_counts()", timeout=5)
    assert isinstance(out, pd.DataFrame)


@pytest.mark.parametrize("code, message", [
    ("x = 1", "did not assign output to 'result'"),
    ("result = 42", "Expected DataFrame result"),
    ("result = df['no_such_column']", "Execution error"),
])
def test_bad_results_raise(deed_df, code: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        csv_backend.execute_pandas(deed_df, code, timeout=5)


@pytest.mark.xfail(
    reason="Known gap: the blocklist enumerates to_* writers but not to_xml "
           "(nor to_string(path) or read_xml), so pandas itself writes the file. "
           "A denylist is not a sandbox.",
)
def test_known_gap_to_xml_writes_a_file(deed_df, tmp_path) -> None:
    target = tmp_path / "leak.xml"
    code = f"df.head(3).to_xml({str(target)!r}, parser='etree')\nresult = df.head(1)"
    try:
        csv_backend.execute_pandas(deed_df, code, timeout=10)
    except ValueError:
        pass  # being blocked is the outcome we want
    assert not target.exists()
