"""LLM interaction — send questions to chat.tamu.ai, parse responses."""

import json
import os
import re
import time

from openai import OpenAI, APITimeoutError, APIConnectionError

from prompts import get_sql_prompt, get_csv_prompt

DEFAULT_MODEL = "protected.Claude Sonnet 4"
AVAILABLE_MODELS = [
    "protected.Claude Sonnet 4",
    "protected.gemini-2.5-flash",
    "protected.gpt-4.1",
    "protected.Claude 3.7 Sonnet",
]


def get_client() -> OpenAI:
    """Create an OpenAI client configured for chat.tamu.ai."""
    api_key = os.getenv("TAMU_AI_API_KEY")
    if not api_key:
        raise ValueError(
            "TAMU_AI_API_KEY not set. Copy .env.example to .env and add your key."
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://chat-api.tamu.ai/openai",
    )


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

    client = get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    # Retry once on timeout/connection error
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                timeout=60,
            )
            break
        except (APITimeoutError, APIConnectionError):
            if attempt == 0:
                time.sleep(2)
                continue
            raise

    content = response.choices[0].message.content
    return _extract_json(content)
