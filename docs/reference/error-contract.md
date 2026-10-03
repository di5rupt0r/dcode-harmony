# Error contract

> Reference.

The provider propagates `httpx` exceptions directly — there is no wrapper
type:

| Condition | Exception |
|---|---|
| timeout | `httpx.TimeoutException` |
| connection refused | `httpx.ConnectError` |
| HTTP 4xx/5xx | `httpx.HTTPStatusError` (from `raise_for_status()`) |
| invalid JSON payload | `json.JSONDecodeError` (a `ValueError`) |
| missing/mistyped `content`/`tokens` | `ValueError` |
| malformed SSE event | `ValueError` |

Callers needing retry/backoff should catch `httpx.HTTPError` or the specific
subclasses above.
