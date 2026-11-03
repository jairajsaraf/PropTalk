"""table_view.column_config: readable date columns in the results table."""

import pandas as pd

import table_view


def _fmt(cfg: dict, column: str) -> str | None:
    return cfg[column]["type_config"].get("format")


def test_midnight_datetimes_show_as_dates() -> None:
    df = pd.DataFrame({"sale_date": pd.to_datetime(["2024-05-09", "2024-06-13"]), "n": [1, 2]})

    cfg = table_view.column_config(df)

    assert _fmt(cfg, "sale_date") == "YYYY-MM-DD"
    assert "n" not in cfg


def test_datetimes_with_a_time_of_day_are_left_alone() -> None:
    df = pd.DataFrame({"ts": pd.to_datetime(["2024-05-09 13:45:00", "2024-06-13 00:00:00"])})

    assert table_view.column_config(df) == {}


def test_no_datetime_columns_gives_empty_config() -> None:
    assert table_view.column_config(pd.DataFrame({"city": ["A"], "n": [1]})) == {}
