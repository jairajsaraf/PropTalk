"""Display formatting for the results table (presentation only; the data is untouched)."""

import pandas as pd
import streamlit as st


def column_config(df: pd.DataFrame) -> dict:
    """Show date-only columns as YYYY-MM-DD instead of 'YYYY-MM-DD 00:00:00'.

    A column with any time of day is left as it is, so no information is hidden.
    """
    config: dict = {}
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_datetime64_any_dtype(series) and (series.dropna().dt.normalize() == series.dropna()).all():
            config[column] = st.column_config.DatetimeColumn(format="YYYY-MM-DD")
    return config
