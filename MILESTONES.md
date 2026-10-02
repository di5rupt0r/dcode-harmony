# Milestones

Statuses: `DONE`, `IN PROGRESS`, `TODO`, `BLOCKED`.

PR #1 (`copilot/continue-implementation`) is a self-contained unit for **M1–M4 only**.

## M0 — Repository bootstrap and handoff documentation — DONE

Acceptance criteria:

- Repository has an initial commit.
- README explains purpose, scope, architecture, install target, and non-goals.
- HANDOFF records observed facts, inferences, decisions, validation, and continuation protocol.
- Milestone plan is authoritative in-repository.

## M1 — Standalone installable package — IN PROGRESS

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

This PR finishes M1 as part of the packaging/launcher bootstrap.

## M2 — Native Harmony provider — IN PROGRESS

Tests first, then implementation.

Acceptance criteria (this PR):

- system/user/assistant messages render with `openai_harmony` (`render_conversation_for_completion`, not JSON);
- `/completion` prompt is a token array; `return_tokens` is true; timeout is only on the HTTP client;
- tool declarations render in the Harmony developer message via `DeveloperContent.with_function_tools`;
- `bind_tools` uses `convert_to_openai_tool` and threads tools through `_generate` / `_stream` / `_payload`;
- `AIMessage.tool_calls` and `ToolMessage` round-trip as assistant commentary + `Role.TOOL` history;
- analysis / commentary / final channels parse from completion tokens (`parse_messages_from_completion_tokens`);
- native tool calls become LangChain `AIMessage.tool_calls` with unique ids; malformed tool args raise `ValueError`;
- `_stream` reads llama-server SSE (`stream: true`) and yields multiple `AIMessageChunk`s via `StreamableParser`;
- `_generate` stays non-streaming;
- connection/timeout/HTTP errors wrap into one exception that names the `/completion` endpoint;
- default endpoint is `http://127.0.0.1:8080/completion`;
- stop strings match `stop_tokens_for_assistant_actions()` (`<|return|>`, `<|call|>`).

Only HTTP transport may be mocked in unit tests. Protocol and message conversion tests must exercise the installed `openai-harmony` encoding.

## M3 — Mandatory `apply_patch` tool — IN PROGRESS

This milestone cannot be deferred.

Acceptance criteria (this PR):

- tool name is exactly `apply_patch`;
- schema/docstring describe the GPT-OSS patch grammar (`Begin/End Patch`, Add/Delete/Update, optional `Move to`, `@@` anchors, `End of File`);
- real patches apply in temporary workspaces;
- malformed patches fail clearly;
- absolute paths and parent traversal are rejected via `Path.is_relative_to`;
- dangling symlinks, symlinked parents, and final-target symlinks are rejected;
- file operations use directory fds + `O_NOFOLLOW` (no silent fallback if `os.open` lacks `dir_fd`);
- all operations are validated before any write (failed later op leaves earlier files unchanged);
- `@@` headers are anchors; ambiguous context without an anchor raises `PatchError("ambiguous context")`;
- trailing newline and CRLF are preserved;
- registration is verified through a fake `ExtensionAPI` (`api.cwd` wrapped in `Path`).

## M4 — Plug-and-play launcher and model selection — IN PROGRESS

Acceptance criteria (this PR, unit-level):

- plain `dcode` selects the local Harmony provider via bootstrap `config.toml`;
- no provider/class-path/config editing is required for the default path;
- `DEEPAGENTS_HOME` override is honored; `~/.dcode-harmony` is not written when the override is set;
- existing `config.toml` is not overwritten;
- `cli_main()` returning `None` maps to exit code 0.

## M5 — Live llama-server validation — TODO

Tracked in a follow-up PR (do not implement on PR #1).

Acceptance criteria:

- documented systemd service assumptions;
- live test command against the user's local server;
- validated normal completion;
- validated reasoning/final output handling;
- validated native tool call and `apply_patch` execution;
- validated error handling when the service is down.

## M6 — Release and maintenance — TODO

Tracked in a follow-up PR (do not implement on PR #1).

Acceptance criteria:

- reproducible install/lockfile;
- release/version policy;
- upstream compatibility/update procedure;
- security review of patch and command boundaries;
- final README and handoff documentation;
- PR/release notes describing live validation.

## Change log

- 2026-10-02: Bootstrap recovery completed; created initial documented base after handoff attempts targeted an empty repository.
- 2026-10-02: PR #1 scope locked to M1–M4. M5 and M6 deferred to follow-up PRs.
