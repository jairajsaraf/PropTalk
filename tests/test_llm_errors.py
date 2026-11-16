"""llm.describe_llm_error: plain-English copy for failed model calls."""

import requests

import llm


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


def test_429_says_examples_still_work() -> None:
    assert llm.describe_llm_error(_http_error(429)) == (
        "The model's rate limit is reached right now. The example questions above still work: "
        "they use saved model output, executed live against the data."
    )


def test_401_and_403_say_key_rejected() -> None:
    expected = "The model API rejected the key. The example questions above still work."
    assert llm.describe_llm_error(_http_error(401)) == expected
    assert llm.describe_llm_error(_http_error(403)) == expected


def test_timeout_copy() -> None:
    assert llm.describe_llm_error(requests.Timeout("slow")) == (
        "The model took too long to answer. Try again, or use an example question."
    )


def test_other_errors_keep_the_message() -> None:
    assert llm.describe_llm_error(RuntimeError("boom")) == "LLM error: boom"
    assert llm.describe_llm_error(_http_error(500)).startswith("LLM error: ")
