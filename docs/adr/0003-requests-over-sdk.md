# 3. Plain `requests` instead of a vendor SDK

## Context

PropTalk needs one call: POST a system prompt and a question to `/chat/completions`, get JSON back. Endpoints that call themselves OpenAI-compatible differ in details: some stream server-sent events by default, and some return content wrapped in code fences or with extra fields.

## Decision

Call the endpoint with `requests.post`, with `"stream": false` and temperature 0. Parse the standard JSON response, fall back to parsing an SSE stream, and extract the JSON object from the model's text. The base URL, key and model come from `LLM_API_BASE`, `LLM_API_KEY` and `LLM_MODEL`, and default to Gemini's OpenAI-compatible endpoint.

## Consequences

- One dependency that is already needed, and the parsing of every response shape is in one function the tests can reach.
- Any OpenAI-compatible provider works by changing environment variables. The model the eval ran on is the default.
- No SDK conveniences (typed responses, built-in retries). The single retry on timeout or connection error is implemented here, and the eval runner adds its own retry and backoff for rate limits.
