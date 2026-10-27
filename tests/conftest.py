"""Shared fixtures. Tests run offline against the seeded synthetic data."""

import os

import pandas as pd
import pytest

import config
import generate_sample_data


@pytest.fixture(scope="session", autouse=True)
def sample_data() -> None:
    """Generate the synthetic CSVs once if they are missing (CI starts clean)."""
    paths = [os.path.join(generate_sample_data.OUTPUT_DIR, t.csv_filename)
             for t in config.TABLE_REGISTRY]
    if not all(os.path.exists(p) for p in paths):
        generate_sample_data.main()


@pytest.fixture
def deed_df() -> pd.DataFrame:
    path = os.path.join(generate_sample_data.OUTPUT_DIR, "deed_transactions_sample.csv")
    return pd.read_csv(path, parse_dates=["sale_date"])
