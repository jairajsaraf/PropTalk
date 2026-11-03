"""Build demo_cache.json: the model's answer to every example question.

    python scripts/build_demo_cache.py            # LIVE: one LLM call per table x engine x example
    python scripts/build_demo_cache.py --verify   # offline: re-check the existing demo_cache.json

The live run calls a rate-limited API, so it waits `--interval` seconds between
calls (the eval's min_interval_s). Only the model's output is stored; the
guard and the engine run again on every request. After building, every entry is
executed offline and any that fails or returns no rows is dropped and listed.
"""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

import config  # noqa: E402
import csv_backend  # noqa: E402
import demo_cache  # noqa: E402
import llm  # noqa: E402
import sqlite_backend  # noqa: E402
from sql_guard import validate_query  # noqa: E402

MODES = ("sql", "pandas")
CODE_KEY = {"sql": "sql", "pandas": "pandas_code"}


def _backends() -> dict:
    return {
        "sql": sqlite_backend.SqliteBackend(config.get_sqlite_tables()),
        "pandas": csv_backend.CsvBackend(config.get_csv_tables()),
    }


def build_entries(query_fn: Callable[..., dict], sleep_fn: Callable[[float], None] = time.sleep,
                  interval: float = 5.0, model: str | None = None) -> list[dict]:
    """Ask the model every example question in both engines, `interval` seconds apart."""
    backends = _backends()
    entries: list[dict] = []
    for table in config.TABLE_REGISTRY:
        for mode in MODES:
            backend = backends[mode]
            schema = backend.get_schema(table.display_name)
            table_name = (backend.get_sql_table_name(table.display_name) if mode == "sql"
                          else table.display_name)
            for question in table.example_questions:
                if entries:
                    sleep_fn(interval)
                response = dict(query_fn(question, schema, mode, table_name, model))
                response.pop("_debug", None)
                entries.append({"question": question, "table_id": table.display_name,
                                "mode": mode, "response": response})
    return entries


def verify_entries(entries: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Run each entry through the real guard and engine. Returns (kept, [(dropped, reason)])."""
    backends = _backends()
    kept: list[dict] = []
    dropped: list[tuple[dict, str]] = []
    for entry in entries:
        mode, table_id = entry["mode"], entry["table_id"]
        code = entry["response"].get(CODE_KEY[mode], "")
        try:
            if mode == "sql":
                ok, sanitized, reason = validate_query(code, backends["sql"].get_allowed_table_names())
                if not ok:
                    raise ValueError(f"guard rejected: {reason}")
                df = sqlite_backend.execute_query(sanitized)
            else:
                df = csv_backend.execute_pandas(backends["pandas"].load_data(table_id), code)
            if df is None or df.empty:
                raise ValueError("returned no rows")
        except Exception as exc:  # any failure drops the entry; the reason is reported
            dropped.append((entry, f"{type(exc).__name__}: {exc}"))
        else:
            kept.append(entry)
    return kept, dropped


def _write(entries: list[dict], model: str, path: str) -> None:
    payload = {"model": model, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "entries": entries}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true", help="re-check the existing file offline; no LLM calls")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between live calls")
    args = parser.parse_args(argv)

    if args.verify:
        with open(demo_cache.CACHE_PATH, encoding="utf-8") as fh:
            saved = json.load(fh)
        entries, model = saved["entries"], saved["model"]
    else:
        from dotenv import load_dotenv
        load_dotenv()
        model = llm.get_model()
        entries = build_entries(llm.query_llm, interval=args.interval, model=model)

    kept, dropped = verify_entries(entries)
    print(f"{len(kept)} of {len(entries)} entries verified (guard + engine, non-empty result).")
    for entry, reason in dropped:
        print(f"  DROPPED [{entry['mode']}] {entry['table_id']}: {entry['question']!r} -> {reason}")
    _write(kept, model, demo_cache.CACHE_PATH)
    print(f"wrote {demo_cache.CACHE_PATH}")
    return 0 if not dropped else 1


if __name__ == "__main__":
    raise SystemExit(main())
