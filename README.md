# dcode-harmony

Standalone, plug-and-play distribution layer for running dcode with a local GPT-OSS model served by `llama-server` through the native Harmony/raw-completion protocol.

> **Status: PR #1 (M1–M5 DONE).** Installable `dcode` launcher, native Harmony provider (token prompt, token parse, tool binding, tool history, SSE streaming), a containment-safe `apply_patch` tool, and live validation against the real llama-server (M5, 2026-10-02). Release/lockfile policy (M6) is a follow-up PR.

## Contents

- [Goals](#goals)
- [Current scope](#current-scope)
- [Test validation](#test-validation)
- [apply_patch safety](#apply_patch-safety)
- [Current user experience](#current-user-experience)
- [Dependency policy](#dependency-policy)
- [Architecture](#architecture)
- [Test-first rule](#test-first-rule)
- [Live validation](#live-validation-2026-10-02-real-server)
- [Validation scope](#validation-scope)
- [Documentation and handoff](#documentation-and-handoff)
- [Error contract](#error-contract)
- [Differences from upstream dcode](#differences-from-upstream-dcode)
- [Limitations](#limitations)
- [License and provenance](#license-and-provenance)

## Goals

The finished project will be installable independently from the upstream `deepagents` monorepo. It will use the published `deepagents-code` package as the dcode runtime and keep `deepagents` as an explicitly pinned external dependency. The local integration layer will:

- expose a normal `dcode` executable;
- select the local Harmony GPT-OSS provider by default;
- use `http://127.0.0.1:8080/completion` by default;
- work with a `llama-server` managed by systemd without provider configuration;
- preserve native GPT-OSS Harmony formatting and tool-call semantics;
- provide a mandatory safe `apply_patch` tool;
- remain reproducible through pinned dependencies and a lockfile;
- be developed strictly test-first.

## Current scope

- pinned package dependencies for `deepagents-code`, `deepagents`, and `openai-harmony`;
- `dcode` launcher bootstrap that writes an isolated `~/.dcode-harmony/config.toml` (overridable with `DEEPAGENTS_HOME`);
- default model/provider selection to `local-harmony:gpt-oss-20b`;
- `HarmonyCompletionChatModel` posting Harmony **tokens** to `/completion` with `return_tokens`;
- SSE streaming via llama-server `stream: true` and `openai_harmony.StreamableParser`;
- `apply_patch` registered through `dcode.extensions`;
- verified clean-environment install (`python -m pip install .`, `dcode --help`, `python -m build`).

Validated live on 2026-10-02 against the real server (M5 DONE — see
*Live validation* below). Still open: CI, lockfile/versioning policy
(M6).

## Test validation

```bash
python -m pytest -q          # full suite (live tests skip without a server)
python -m pytest -m "not live"  # unit/integration tests, no server needed
python -m pytest -m live     # requires llama-server on 127.0.0.1:8080
```

Live tests exercise `/health`, `/completion`, token prompt shape, provider
invoke, streaming, SSE fields/terminal stop, and real `apply_patch` tool-call
execution. They were executed against the real server on 2026-10-02
(`6 passed`) — see *Live validation* below.

## apply_patch safety

- Accepts only the GPT-OSS `*** Begin Patch` grammar (Add/Update/Delete,
  optional `*** Move to:`, `@@` hunks, `*** End of File`). Unified diff is
  **not** accepted — that would diverge from what GPT-OSS is trained to emit.
- Tool schema: a single argument `patch: str`. Paths live inside the patch
  text; a separate `path` argument (as in some shells) is not used.
- Absolute paths, `../` traversal, and any symlink in the target path
  (escaping or not) are rejected.
- Every operation is validated and all new contents computed before any
  write; a failure rolls earlier writes back (no partial multi-file state).
- Writes use `dir_fd` + `O_NOFOLLOW`, so a symlink swapped in mid-operation
  cannot redirect the write. Ambiguous hunk context is rejected
  (`ambiguous context`).
- TOCTOU scope: parent directories are opened by path (`os.open(parent)`),
  not walked fd-by-fd. The tool therefore defends against a symlinked final
  path component and a symlinked parent at validation time, but does **not**
  provide full resistance to an attacker concurrently swapping an
  intermediate directory between validation and `open`. Running patches in
  a private workspace is the expected boundary. Do not rely on this tool as
  a security boundary against a hostile local process.


## Current user experience

After the packaging/launcher work:

```bash
git clone https://github.com/di5rupt0r/dcode-harmony.git
cd dcode-harmony
python -m venv .venv
. .venv/bin/activate
python -m pip install .

# llama-server is already running as a systemd service on localhost:8080
dcode
```

Optional: `DEEPAGENTS_HOME=/path/to/profile dcode` uses that profile directory instead of `~/.dcode-harmony`. An existing `config.toml` in the profile is not overwritten.

## Dependency policy

The project will depend on published packages rather than copying the complete upstream SDK or dcode source:

- `deepagents-code`: pinned to an explicitly recorded compatible release;
- `deepagents`: pinned explicitly to the version required by that dcode release;
- `openai-harmony`: pinned to a verified compatible release;
- only small direct dependencies needed by the integration layer.

Pinned versions (verified from published wheel metadata):

- `deepagents-code==0.1.80` (declares `deepagents==0.7.21`);
- `deepagents==0.7.21`;
- `openai-harmony==0.0.8`.

Monorepo-local `uv` path overrides are not used.

## Architecture

```text
user -> dcode executable
          |
          v
  upstream deepagents-code (installed dependency)
          |
          +--> dcode/deepagents agent runtime
          |
          +--> dcode_harmony integration package
                    |
                    +--> openai-harmony formatting/parsing
                    +--> llama-server /completion
                    +--> mandatory apply_patch tool
```

The preferred integration order is:

1. use a stable public dcode extension/tool-registration API;
2. use supported dcode/deepagents agent-construction or configuration hooks;
3. maintain the smallest compatibility shim required if the published package exposes no viable public hook.

## Test-first rule

Tests precede implementation. This is a project rule, not a suggestion:

1. write a failing test for the behavior;
2. run it and record the failure;
3. implement the smallest change;
4. run focused and broader validation;
5. document the result in `HANDOFF.md`.

Internal filesystem, formatting, parsing, and safety logic must use real tests. Mocking is allowed only at external dependency boundaries, such as HTTP transport to a separately running llama-server. No mock may replace the real patch application or Harmony parser behavior.

Live tests are marked `@pytest.mark.live`. Run unit tests with:

```bash
pytest -m "not live"
```

## Live validation (2026-10-02, real server)

Validated against a real local server:

- Model: `unsloth/gpt-oss-20b-GGUF` (gpt-oss-20b, `-hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk q8_0 -ctv q4_0 -t 4`)
- Endpoint: `http://127.0.0.1:8080/completion`
- `/health` returns `{"status":"ok"}` once the model is loaded (returns
  `503 Loading model` during startup).
- `/completion` accepts `prompt` as a token id list and returns both
  `content` and `tokens` when `return_tokens=true`.
- SSE streaming (`stream: true`) events carry `index`, `content`, `tokens`,
  `stop`, `id_slot`, `tokens_predicted`, `tokens_evaluated`. llama-server
  terminates the stream with a `stop: true` event and close — there is **no
  `data: [DONE]` sentinel**.
- Provider-level probes against the real model:
  - `invoke()` on "Reply with exactly: ok" returned `AIMessage(content="ok")`;
  - `stream()` produced 8 chunks, joined `"1, 2, 3"`, no raw Harmony markup;
  - a bound `apply_patch` call produced
    `tool_calls[0] == {"name": "apply_patch", "args": {"patch": "*** Begin
    Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"}}` and the patch was
    applied to disk by the real tool.
- Live suite result: `6 passed` (health, token contract, invoke, stream,
  tool-call execution, SSE fields). Full suite: `97 passed` (91 unit/integration + 6 live).
  `ruff check` and `ruff format --check` pass; `ty check src/` passes.

Repeat with:

```bash
pytest -m live -q       # needs the server on 127.0.0.1:8080
```

## Validation scope

### Validated live (2026-10-02, real server)

- `/health`;
- Harmony prompt as token list;
- `return_tokens=true`;
- provider invoke;
- real streaming;
- real tool call to `apply_patch`;
- real patch application in a temporary workspace;
- SSE fields and termination by `stop: true`.

### Not validated live

- long-running full TUI session;
- multiple tool cycles;
- session recovery;
- behavior under out-of-memory;
- systemd restart/recovery;
- remote CI.

## Documentation and handoff

- [`HANDOFF.md`](HANDOFF.md): operational state, decisions, validation, and continuation instructions.
- [`MILESTONES.md`](MILESTONES.md): authoritative roadmap and acceptance criteria.
- [`AGENTS.md`](AGENTS.md): mandatory document → test → implement → granular push workflow.

Every agent must update both `HANDOFF.md` and `MILESTONES.md` before handing work to another agent.

## Error contract

The provider propagates `httpx` exceptions directly — no wrapper type:

- timeout → `httpx.TimeoutException`;
- connection refused → `httpx.ConnectError`;
- HTTP 4xx/5xx → `httpx.HTTPStatusError` (from `response.raise_for_status()`);
- invalid JSON payload → `json.JSONDecodeError` (a `ValueError`);
- missing/ mistyped `content`/`tokens` → `ValueError`;
- malformed SSE event → `ValueError`.

Callers that need retry/backoff should catch `httpx.HTTPError` (base class)
or the specific subclasses above.

## Differences from upstream dcode

- Ships a `local-harmony:gpt-oss-20b` provider class instead of requiring a
  configured cloud provider on first run.
- Injects a bootstrap `config.toml` when the profile has none (never
  overwrites an existing file).
- Registers an `apply_patch` tool through the public extension API.
- Everything else (TUI, agent runtime, sessions, skills, subagents) is the
  upstream `deepagents-code` runtime.

## Limitations

- Requires a locally running `llama-server` on `http://127.0.0.1:8080`
  serving a GPT-OSS model; no provider is bundled.
- Only the `*** Begin Patch` apply_patch grammar is supported.
- Streaming tool calls are emitted as complete `tool_calls` chunks when the
  call terminates; partial args are not streamed.
- No CI configuration yet; the default `pytest -q` path is the local gate.

## License and provenance

The implementation layer is intended to remain separately licensed as documented when code is added. Upstream dcode provenance, source commit, and license details must be recorded before importing any source or copying substantial documentation from `langchain-ai/deepagents`.
