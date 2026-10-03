# Debug agent runs with execution traces

> How-to guide. Use the execution-trace harness to record every provider
> request/response as JSONL for debugging.

## Quick start

```bash
# Run live tests with tracing enabled
DCODE_TRACE_DIR=traces pytest -m live -q

# Or use the CLI option
pytest -m live -q --trace-dir traces
```

This writes one JSONL file per test into `traces/`. Each file is named
after the test node id (e.g. `tests_test_live_llama_server_test_live_provider_invoke_returns_valid_ai_message.jsonl`).

When `DCODE_TRACE_DIR` is unset and `--trace-dir` is not passed, the suite
runs with zero overhead and writes no files.

## Trace record schema

Each line in a trace file is a JSON object. Fields vary by phase:

| Field | Meaning |
|---|---|
| `ts` | Monotonic offset from transport start (seconds) |
| `test` | Pytest node id |
| `phase` | `request` / `response` / `sse` / `render` / `tool` / `error` |
| `url` | Endpoint URL |
| `prompt_tokens` | Length of the token-array prompt |
| `stream` | Whether streaming was requested |
| `n_predict` | Requested max tokens |
| `max_tokens` | Alias for `n_predict` |
| `ttft_s` | Time to first streamed token (seconds) |
| `total_s` | Request wall time (seconds) |
| `tokens_predicted` | Number of tokens in the response |
| `stop` | Stop reason from the server |
| `content_preview` | First ~120 chars of response content |
| `error` | `ExceptionClass: message` |

## Reading a trace

```bash
# Pretty-print a trace file
python -m json.tool --json-lines traces/<file>.jsonl

# Or use jq
cat traces/<file>.jsonl | jq .
```

A typical non-streaming request produces two records:

1. `phase: "request"` — the outgoing payload (prompt tokens, n_predict, stream flag)
2. `phase: "response"` — the server response (content preview, tokens predicted, stop reason, wall time)

A streaming request produces:

1. `phase: "request"` — the outgoing payload
2. `phase: "sse"` — one record per SSE event, with `ttft_s` on the first event
3. `phase: "response"` — the final response summary

## Failure artifacts

When a test fails with tracing enabled, the terminal output includes the
trace file path:

```
=== FAILURES ===
_________________ test_live_provider_invoke _________________
...
Trace file: traces/tests_test_live_llama_server_test_live_provider_invoke.jsonl
```

This lets you correlate a failure with the exact request/response that
caused it.

## Test-side annotations

Use `trace_event()` to add custom records to the current test's trace file:

```python
from tests._trace import trace_event
from tests._trace import get_trace_dir

def test_something(tmp_path):
    trace_dir = get_trace_dir()
    if trace_dir:
        trace_event(trace_dir / "test_something.jsonl", phase="render", test="test_something", data={"prompt_tokens": 42})
    # ... rest of test
```

This is useful for recording prompt render times, tool execution results,
or parse outcomes without modifying the provider.

## Zero-overhead default

When `DCODE_TRACE_DIR` is unset and `--trace-dir` is not passed:

- No trace files are created
- No transport wrapping occurs
- The test suite runs exactly as before (109 passed, 6 deselected)

This ensures the default `pytest -m "not live" -q` behavior is unchanged.
