"""bootstrap.ensure_sample_data: generate the synthetic CSVs once, on first start."""

import os
import subprocess
import sys

import pytest

import bootstrap
import config
import csv_backend


@pytest.fixture
def spy_run(monkeypatch):
    calls: list[tuple[tuple, dict]] = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", _spy)
    return calls


def test_noop_when_all_csvs_present(monkeypatch, spy_run) -> None:
    monkeypatch.setattr(os.path, "exists", lambda path: True)

    assert bootstrap.ensure_sample_data() is False
    assert spy_run == []


def test_generates_when_any_csv_missing(monkeypatch, spy_run) -> None:
    missing = config.TABLE_REGISTRY[-1].csv_filename
    real_exists = os.path.exists
    monkeypatch.setattr(
        os.path, "exists",
        lambda path: False if str(path).endswith(missing) else real_exists(path),
    )

    assert bootstrap.ensure_sample_data() is True
    assert len(spy_run) == 1
    args, kwargs = spy_run[0]
    command = args[0]
    assert command[0] == sys.executable
    assert command[1].endswith("generate_sample_data.py")
    assert os.path.dirname(command[1]) == os.path.dirname(csv_backend.SAMPLE_DIR)
    assert kwargs.get("check") is True
