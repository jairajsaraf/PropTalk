"""LLM interaction — send questions to chat.tamu.ai, parse responses."""

import json
import os
import re
import time

import requests

from prompts import get_sql_prompt, get_csv_prompt

DEFAULT_MODEL = "protected.Claude Sonnet 4"
AVAILABLE_MODELS = [
    "protected.Claude Sonnet 4",
    "protected.gemini-2.5-flash",
    "protected.gpt-4.1",
    "protected.Claude 3.7 Sonnet",
]

API_BASE = "https://chat-api.tamu.ai/openai"


def _get_api_key() -> str:
    """Return the TAMU AI API key or raise."""
    api_key = os.getenv("TAMU_AI_API_KEY")
    if not api_key:
        raise ValueError(
            "TAMU_AI_API_KEY not set. Copy .env.example to .env and add your key."
        )
    return api_key


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response:\n{text[:500]}")


def query_llm(
    question: str,
    schema_info: str,
    mode: str,
    table_name: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Send a natural language question to the LLM and get a structured response.

    Args:
        question: The user's plain-English question.
        schema_info: Formatted schema string (from db.get_schema or csv_backend.get_schema).
        mode: "sql" or "csv".
        table_name: Display name or fully qualified table name.
        model: LLM model to use.

    Returns:
        Dict with keys: sql/pandas_code, chart_config, explanation.
    """
    if mode == "sql":
        system_prompt = get_sql_prompt(table_name, schema_info)
    else:
        system_prompt = get_csv_prompt(table_name, schema_info)

    api_key = _get_api_key()
    url = f"{API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        "temperature": 0,
    }

    # Retry once on timeout/connection error
    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            break
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 0:
                time.sleep(2)
                continue
            raise

    # --- Debug logging (prints to terminal) ---
    print(f"[LLM DEBUG] Status: {resp.status_code}")
    print(f"[LLM DEBUG] Content-Type: {resp.headers.get('content-type', 'N/A')}")
    print(f"[LLM DEBUG] Body (first 500 chars): {resp.text[:500]}")

    # Store debug info for Streamlit UI
    query_llm._last_debug = {
        "status_code": resp.status_code,
        "content_type": resp.headers.get("content-type", "N/A"),
        "raw_body": resp.text[:2000],
    }

    resp.raise_for_status()

    # Parse response — try OpenAI-compatible JSON first, fall back to raw text
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        # Response isn't standard OpenAI format — log full body and use raw text
        print(f"[LLM DEBUG] Non-standard response. Full body:\n{resp.text}")
        query_llm._last_debug["parse_error"] = True
        query_llm._last_debug["raw_body"] = resp.text[:5000]
        content = resp.text

    return _extract_json(content)
