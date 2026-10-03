# Milestones

Statuses: `DONE`, `IN PROGRESS`, `TODO`, `BLOCKED`.

PR #1 (`copilot/continue-implementation`) covers **M1–M5**: M1–M4 are
packaging/provider/patch/launcher hardening; M5 (live validation against
the real llama-server) completed 2026-10-02. M6 remains a follow-up PR.

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

This PR finishes M1 as part of the packaging/launcher bootstrap.

## M2 — Native Harmony provider — DONE

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
- connection/timeout/HTTP errors propagate as httpx exceptions (ConnectError, TimeoutException, HTTPStatusError); this is the documented contract — no unified wrapper;
- default endpoint is `http://127.0.0.1:8080/completion`;
- stop strings match `stop_tokens_for_assistant_actions()` (`<|return|>`, `<|call|>`).

Only HTTP transport may be mocked in unit tests. Protocol and message conversion tests must exercise the installed `openai-harmony` encoding.

## M3 — Mandatory `apply_patch` tool — DONE

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
- registration is verified through the real `ExtensionRegistry` +
  `ExtensionAPI` (`tests/test_extension_registration.py`);
- repeated operations on the same path compose through a virtual
  per-path byte+mode state in `_plan` (no stale overwrites);
- `*** End of File` hunks disambiguate context (EOF-anchored matches win);
- writes are atomic via temp file + `os.replace`, preserve the original
  permission bits, and leave no staged `.dcode-tmp-*` files on failure;
- insertion-only EOF hunks append at end of file;
- long filenames near the component limit work (short random temp names);
- non-writable parent directories are rejected at planning with a clear
  `PatchError`;
- rollback is verified against a real I/O failure (unwritable subdirectory),
  restoring source bytes, destination state, and modes, and removing
  directories created by the patch.

## M4 — Plug-and-play launcher and model selection — DONE

Acceptance criteria (this PR, unit-level):

- plain `dcode` selects the local Harmony provider via bootstrap `config.toml`;
- no provider/class-path/config editing is required for the default path;
- `DEEPAGENTS_HOME` override is honored; `~/.dcode-harmony` is not written when the override is set;
- existing `config.toml` is not overwritten;
- `cli_main()` returning `None` maps to exit code 0.

## M5 — Live llama-server validation — DONE

Completed on PR #1 (2026-10-02). The earlier "follow-up PR" note referred
to the pre-live state and is obsolete; scope below is what was validated.

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
- 2026-10-02: PR #1 scoped to M1–M4 initially; M5 completed within the
  same PR after live validation. M6 (CI/lockfile/release) remains TODO.

## 2026-10-02 review-round status update

- M1 DONE: clean-environment `uv`/`pip install .` verified; `dcode --help`,
  `import dcode_harmony/deepagents_code/openai_harmony`, `pytest -q`
  (55 passed / 8 live-skipped), and `python -m build` all ran green.
- M2 DONE: prompt is a token array (never `Conversation.to_json()`); tool
  declarations render via `DeveloperContent.with_function_tools`; `bind_tools`
  threads through the real LangChain path; `AIMessage.tool_calls`/`
  ToolMessage` round-trip; parsing matrix covers analysis/commentary/final,
  truncated, malformed, unknown-recipient, fragmented JSON; real SSE
  streaming via `StreamableParser`; `profile={"tool_calling": True}` set.
- M3 DONE: GPT-OSS `*** Begin Patch` grammar (Add/Update/Delete/Move to/
  `*** End of File`); ambiguous context rejected; CRLF/trailing-newline
  preserved; validate-before-write + rollback; `dir_fd`+`O_NOFOLLOW`
  writes; symlink and traversal rejected. Integration test through the real
  extension registry passes.
- M4 DONE: bootstrap config.toml is consumed by the real
  `deepagents_code.config.create_model` (subprocess test); no overwrite of
  existing config; `cli_main() -> None` maps to exit 0; `dcode --help`
  subprocess smoke test passes.
- M5 DONE (2026-10-02): live suite ran against the real
  `unsloth/gpt-oss-20b-GGUF` llama-server — 6 passed (health, token
  contract, invoke, streaming, real apply_patch tool call execution, SSE
  fields). Documented server facts and streaming sentinel absence in
  README/HANDOFF.
- M6 TODO (unchanged): no CI config, no lockfile policy yet.

- 2026-10-02: apply_patch hardening completed across rounds 3–4 (atomic
  writes, mode preservation, virtual mode/byte state, EOF-anchor
  disambiguation, staged-temp cleanup, readonly-dir plan-time rejection);
  M5 validated live on the real server; M6 remains the only follow-up.
