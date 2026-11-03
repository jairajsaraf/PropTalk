"""First-start setup: generate the synthetic CSVs when they are not on disk.

sample_data/*.csv is gitignored, so a fresh deployment starts without data.
"""

import os
import subprocess
import sys

import config
import csv_backend

_GENERATOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_sample_data.py")


def ensure_sample_data() -> bool:
    """Generate the sample CSVs if any is missing.

    Returns True if it generated the data, False if every CSV already existed.
    Runs the documented command (`python generate_sample_data.py`), so the
    seeded output is identical to a manual setup.
    """
    paths = [os.path.join(csv_backend.SAMPLE_DIR, t.csv_filename) for t in config.TABLE_REGISTRY]
    if all(os.path.exists(p) for p in paths):
        return False
    subprocess.run([sys.executable, _GENERATOR], check=True)
    return True
