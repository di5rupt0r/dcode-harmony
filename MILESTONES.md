# Milestones

Statuses: `DONE`, `IN PROGRESS`, `TODO`, `BLOCKED`.

## M0 — Repository bootstrap and handoff documentation — DONE

Acceptance criteria:

- Repository has an initial commit.
- README explains purpose, scope, architecture, install target, and non-goals.
- HANDOFF records observed facts, inferences, decisions, validation, and continuation protocol.
- Milestone plan is authoritative in-repository.

## M1 — Standalone installable package — DONE

Write tests before implementation.

Acceptance criteria:

- `pyproject.toml` builds outside the upstream monorepo.
- Published `deepagents-code` is a pinned dependency.
- `deepagents` is explicitly pinned to a compatible version.
- `openai-harmony` is a pinned, verified dependency.
- No monorepo-local path dependency is required.
- Installing the project exposes a working `dcode` executable.
- The default launcher requires no provider configuration.
- `HANDOFF.md` records exact package versions and provenance.

Suggested boundaries:

1. failing packaging/CLI tests;
2. metadata and package layout;
3. launcher implementation;
4. install/import/CLI validation.

## M2 — Native Harmony provider — IN PROGRESS

Tests first, then implementation.

Acceptance criteria:

- system/user/assistant messages render in the verified GPT-OSS Harmony format;
- tool declarations render in the expected native form;
- analysis, commentary, and final channels are parsed distinctly;
- native tool calls become valid LangChain `AIMessage.tool_calls`;
- malformed output produces useful errors rather than silent corruption;
- default endpoint is `http://127.0.0.1:8080/completion`;
- stop settings match the verified llama.cpp/Harmony behavior;
- existing dcode TUI streaming expectations remain valid.

Progress:
- Streaming support implemented via `_stream` method yielding `ChatGenerationChunk`
- Tool call parsing implemented and tested
- Channel parsing implemented (analysis/commentary/final)
- Message conversion implemented and tested
- HTTP contract tested with mock transport

Only HTTP transport may be mocked in unit tests. Protocol and message conversion tests must exercise real local code and the verified Harmony library.

## M3 — Mandatory `apply_patch` tool — IN PROGRESS

This milestone cannot be deferred.

Integration fallback order:

1. **Preferred:** stable public extension/tool-registration API from the pinned dcode package.
2. **Fallback:** supported dcode/deepagents construction or configuration hook.
3. **Last resort:** smallest compatibility shim needed to inject the tool, with explicit version/upgrade constraints.

Acceptance criteria:

- tool name is exactly `apply_patch`;
- schema accepts the GPT-OSS expected arguments;
- real patches apply in temporary workspaces;
- malformed patches fail clearly;
- absolute paths and parent traversal are rejected;
- symlink/containment escapes are rejected;
- tool results are useful to the model;
- registration is verified through the actual dcode integration path.

Progress:
- All acceptance criteria implemented via extension API (preferred path)
- All safety guardrails implemented and tested
- Tool registered as `apply_patch` via `dcode.extensions` entry point

## M4 — Plug-and-play launcher and model selection — IN PROGRESS

Acceptance criteria:

- plain `dcode` selects the local Harmony provider;
- no provider/class-path/config editing is required for the default path;
- optional environment overrides are documented;
- existing upstream provider behavior is not modified unnecessarily;
- launcher and model selection have real integration tests.

Progress:
- Launcher bootstrap config auto-generates Harmony provider defaults
- `DEEPAGENTS_HOME` environment override tested
- Endpoint parameters (base_url, completion_path, timeout_s, stop) tested
- Unit tests passing, integration tests pending

## M5 — Live llama-server validation — IN PROGRESS

Acceptance criteria:

- documented systemd service assumptions;
- live test command against the user's local server;
- validated normal completion;
- validated reasoning/final output handling;
- validated native tool call and `apply_patch` execution;
- validated error handling when the service is down.

Progress:
- Live test suite added with `@pytest.mark.live` marker
- Normal completion test added (with stop tokens)
- Error handling test added (invalid requests)
- End-to-end Harmony provider integration test added
- Tests skip gracefully when server unavailable
- Actual live run pending user's local server availability

Tests that require a live server may be explicitly marked/skipped when unavailable, but must never be replaced by mocks.

## M6 — Release and maintenance — TODO

Acceptance criteria:

- reproducible install/lockfile;
- release/version policy;
- upstream compatibility/update procedure;
- security review of patch and command boundaries;
- final README and handoff documentation;
- PR/release notes describing live validation.

## Change log

- 2026-10-02: Bootstrap recovery completed; created initial documented base after handoff attempts targeted an empty repository.
- 2026-10-02: Added pinned dependency metadata, isolated launcher bootstrap, initial Harmony `/completion` provider slice, safe `apply_patch` extension tool, and test-first coverage for launcher/provider/patch safety.
- 2026-10-02: Added streaming support to Harmony provider (`_stream` method), launcher environment override tests, and comprehensive live server validation test suite with skip-on-unavailable logic.
