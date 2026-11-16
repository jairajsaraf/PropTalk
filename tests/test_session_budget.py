"""session_budget: the per-session cap on live LLM calls."""

import session_budget


def test_remaining_starts_at_max() -> None:
    assert session_budget.remaining({}) == session_budget.MAX_LIVE_CALLS_PER_SESSION


def test_consume_decrements_and_floors_at_zero() -> None:
    state: dict = {}

    session_budget.consume(state)
    assert session_budget.remaining(state) == session_budget.MAX_LIVE_CALLS_PER_SESSION - 1

    for _ in range(session_budget.MAX_LIVE_CALLS_PER_SESSION + 3):
        session_budget.consume(state)
    assert session_budget.remaining(state) == 0
    assert state["live_calls_used"] == session_budget.MAX_LIVE_CALLS_PER_SESSION
