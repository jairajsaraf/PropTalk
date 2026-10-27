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


def test_allowlisted_builtins_work(deed_df) -> None:
    code = ("result = pd.DataFrame({'n': [len(df)], 'c': [int(df['sale_amount'].max())],"
            " 's': [str(sorted(set(df['county']))[0])], 'r': [round(float(df['sale_amount'].mean()), 1)]})")
    out = csv_backend.execute_pandas(deed_df, code, timeout=10)
    assert out["n"].iloc[0] == 5000 and out["s"].iloc[0] == "BEXAR"


def test_builtin_allowlist_is_exactly_what_the_contract_says() -> None:
    assert set(csv_backend._builtins_for(2)) == set(csv_backend.SAFE_BUILTIN_NAMES)
    assert csv_backend._builtins_for(1) == {}
    for dangerous in ("type", "object", "getattr", "setattr", "delattr", "hasattr", "vars",
                      "dir", "globals", "locals", "open", "input", "print", "eval", "exec",
                      "compile", "__import__", "breakpoint", "memoryview", "bytearray",
                      "bytes", "map", "filter", "iter", "next", "callable", "isinstance",
                      "issubclass", "super", "property", "classmethod", "staticmethod"):
        assert dangerous not in csv_backend.SAFE_BUILTIN_NAMES, dangerous


@pytest.mark.parametrize("name", ["type", "object", "vars", "dir", "isinstance", "map",
                                  "print", "bytes", "iter", "next", "super"])
def test_other_builtins_remain_unavailable(deed_df, name: str) -> None:
    """Names the blocklist does not catch by itself must still be undefined
    in the worker; the allowlist, not the regex, is what keeps them out."""
    with pytest.raises(ValueError, match=f"name '{name}' is not defined"):
        csv_backend.execute_pandas(deed_df, f"result = pd.DataFrame({{'x': [{name}]}})", timeout=5)


def test_builtin_allowlist_does_not_open_dunder_access(deed_df) -> None:
    for code in ("result = pd.DataFrame({'x': [str.__mro__]})",
                 "result = pd.DataFrame({'x': [().__class__]})",
                 "result = pd.DataFrame({'x': [int.__subclasses__()]})"):
        with pytest.raises(ValueError, match="Blocked pattern"):
            csv_backend.execute_pandas(deed_df, code, timeout=5)


@pytest.mark.parametrize("expr", [
    "len(df)", "df['sale_amount'].mean()", "df['sale_amount'].max()", "df.shape[0]",
    "(df['cash_purchase'] == 'Y').sum()", "df['city'].iloc[0]", "True",
    "df['sale_date'].min()", "1 + 1.5",
])
def test_scalar_results_become_a_one_cell_frame(deed_df, expr: str) -> None:
    out = csv_backend.execute_pandas(deed_df, f"result = {expr}", timeout=10)
    assert isinstance(out, pd.DataFrame) and out.shape == (1, 1)
    assert list(out.columns) == ["result"]


@pytest.mark.parametrize("expr, kind", [
    ("[1, 2, 3]", "list"), ("{'a': 1}", "dict"), ("(1, 2)", "tuple"), ("df.shape", "tuple"),
    ("df.columns", "Index"),
])
def test_non_scalar_non_frame_results_are_still_rejected(deed_df, expr: str, kind: str) -> None:
    with pytest.raises(ValueError, match=f"Expected DataFrame result, got {kind}"):
        csv_backend.execute_pandas(deed_df, f"result = {expr}", timeout=10)


def test_contract_1_reproduces_the_original_behaviour(deed_df) -> None:
    """The v1 eval report was made under contract 1; its re-score depends on
    this exact behaviour, so it is pinned here."""
    with pytest.raises(ValueError, match="name 'len' is not defined"):
        csv_backend.execute_pandas(deed_df, "result = df.head(len(df))", timeout=5, contract=1)
    with pytest.raises(ValueError, match="Expected DataFrame result, got int"):
        csv_backend.execute_pandas(deed_df, "result = df.shape[0]", timeout=5, contract=1)
    out = csv_backend.execute_pandas(deed_df, "result = df.head(3)", timeout=5, contract=1)
    assert len(out) == 3


def test_current_contract_is_2() -> None:
    assert csv_backend.EXEC_CONTRACT == 2


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
    ("result = [42]", "Expected DataFrame result"),
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
