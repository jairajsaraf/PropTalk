"""Per-session cap on live LLM calls.

The count lives in the Streamlit session state, so it resets on a page reload.
It is a courtesy cap that keeps one visitor from draining the shared quota by
accident, not abuse protection.
"""

from collections.abc import MutableMapping
from typing import Any

MAX_LIVE_CALLS_PER_SESSION: int = 8
_KEY = "live_calls_used"


def remaining(state: MutableMapping[str, Any]) -> int:
    """Live calls this session may still make."""
    return max(0, MAX_LIVE_CALLS_PER_SESSION - int(state.get(_KEY, 0)))


def consume(state: MutableMapping[str, Any]) -> None:
    """Record one live call, never going past the cap."""
    state[_KEY] = min(MAX_LIVE_CALLS_PER_SESSION, int(state.get(_KEY, 0)) + 1)
