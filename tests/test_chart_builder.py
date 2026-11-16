"""chart_builder: a bar config over raw rows must not stack them into a sum."""

import pandas as pd

from chart_builder import build_chart

BAR = {"chart_type": "bar", "x": "PropertyType", "y": "ListPrice", "color": None, "title": "t"}


def test_bar_over_raw_rows_draws_a_box_plot() -> None:
    df = pd.DataFrame({"PropertyType": ["Condo", "Condo", "House"], "ListPrice": [200_000, 300_000, 500_000]})
    assert build_chart(df, BAR).data[0].type == "box"


def test_bar_over_one_row_per_category_stays_a_bar() -> None:
    df = pd.DataFrame({"PropertyType": ["Condo", "House"], "ListPrice": [250_000, 500_000]})
    assert build_chart(df, BAR).data[0].type == "bar"


def test_grouped_bar_with_unique_category_pairs_stays_a_bar() -> None:
    df = pd.DataFrame({"city": ["A", "A", "B"], "year": ["2023", "2024", "2024"], "n": [1, 2, 3]})
    config = {"chart_type": "bar", "x": "city", "y": "n", "color": "year", "title": "t"}
    assert {trace.type for trace in build_chart(df, config).data} == {"bar"}
