# Live validation

> Explanation. What was verified against a real server, and what was not.

Validated on 2026-10-02 against `unsloth/gpt-oss-20b-GGUF` on
`http://127.0.0.1:8080/completion` with
`llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk q8_0 -ctv q4_0 -t 4`:

- `/health` returns `{"status":"ok"}` once loaded; `503` while loading.
- `/completion` accepts `prompt` as a token id list and returns `content`
  and `tokens` when `return_tokens=true`.
- SSE events carry `index`, `content`, `tokens`, `stop`, `id_slot`,
  `tokens_predicted`, `tokens_evaluated`; the stream ends with `stop: true`
  and close (no `data: [DONE]`).
- Provider probes: `invoke("Reply with exactly: ok")` → `AIMessage(content="ok")`;
  `stream()` yielded 8 chunks joined as `"1, 2, 3"` with no raw Harmony
  markup; a bound `apply_patch` call produced a valid patch applied to disk.
- Live suite: 6 passed (health, token contract, invoke, stream, tool-call
  execution, SSE fields). Full suite: 97 passed.

Not covered:

- long-running full TUI sessions;
- multiple tool cycles in one session;
- session recovery;
- out-of-memory behavior;
- systemd restart/recovery;
- remote CI.
