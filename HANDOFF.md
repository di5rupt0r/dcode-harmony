# Handoff

## Current state

- Date: 2026-10-02
- Repository: `di5rupt0r/dcode-harmony`
- Branch / PR: `copilot/continue-implementation` (PR #1)
- Scope of this PR (fixed): M1 packaging/launcher bootstrap, M2 native Harmony provider, M3 safe `apply_patch`, M4 launcher/model selection (unit-level)
- Out of scope: M5 live llama-server validation, M6 release/lockfile/versioning (follow-up PRs)

## Decisions recorded

1. Do not clone the full `libs/code` tree by default.
2. Install published `deepagents-code` and explicitly pin compatible `deepagents` instead.
3. Add `openai-harmony` as a direct dependency after verifying the real package metadata/API.
4. Make the resulting package expose `dcode` and default to local llama-server behavior.
5. Treat `apply_patch` as mandatory in the first runtime implementation milestone.
6. Try integration mechanisms in this order: public extension API, supported construction/configuration hook, smallest compatibility shim.
7. Enforce document → failing tests → implementation for each feature.
8. Do not mock internal behavior or real filesystem patching; mock only external boundaries such as HTTP transport.
9. Prompt the model with Harmony **tokens** from `render_conversation_for_completion`, not `Conversation.to_json()`.
10. Parse completions with `parse_messages_from_completion_tokens` (and `StreamableParser` for SSE), not `json.loads` of generated text.
11. `deepagents_code.cli_main` is typed `() -> None` (exit via `SystemExit`); map `None` to process exit 0.
12. `ExtensionAPI.cwd` is a `pathlib.Path`; still wrap with `Path(...)` before `apply_patch_text`.

## Verified APIs (installed / fetched)

- `openai-harmony==0.0.8`: `HarmonyEncodingName.HARMONY_GPT_OSS`, `render_conversation_for_completion`, `parse_messages_from_completion_tokens`, `encode(..., allowed_special="all")`, `stop_tokens_for_assistant_actions()` → `<|return|>` and `<|call|>`, `StreamableParser.process`, `Author.new(Role.TOOL, name)`, `DeveloperContent.with_function_tools`, `Message.with_content_type`.
- llama.cpp server README: `/completion` `prompt` may be a token array; `return_tokens` exists (default false); streaming SSE returns `content`, `tokens`, and `stop`.
- GPT-OSS `apply_patch` grammar: Add/Delete/Update, optional `*** Move to:`, hunks `@@ [header]`, optional `*** End of File`.
- `deepagents_code==0.1.80`: `cli_main() -> None`; `ExtensionAPI.cwd: Path`.

## Required protocol for future agents

Before changing code: read this file, `README.md`, and `MILESTONES.md`; write failing tests first.

After changing code: run `pytest -m "not live"`; update milestone status with real counts; do not claim live llama-server validation unless a live server was used.

## Session/change log

### 2026-10-02 — PR #1 (M1–M4)

This session closes PR #1 as a finished M1–M4 unit. Implementation follows this handoff: native Harmony render/parse/bind/history/SSE streaming, dir_fd `apply_patch`, launcher `None`→0 and home override tests. M5/M6 remain TODO.

### 2026-10-02 — PR review fix round (operator prompt)

- `src/dcode_harmony/providers/harmony.py` contained unresolved merge-conflict
  markers (SyntaxError) breaking every import; repaired (commit ed71ae2);
  suite now collects and passes 16/4-skipped.
- `.venv` rebuilt with uv-managed CPython 3.14.7 (system python3.14 lacked
  `Python.h`; `bsdiff4` could not build). Installed pins:
  `deepagents-code==0.1.80`, `deepagents==0.7.21`, `openai-harmony==0.0.8`,
  `httpx==0.28.1`, pytest 8.4.2. No dnf installs needed.
- `git push` restored after transient network failure; local agent-policy
  commit was redundant with remote e3c15e0 and was dropped.

Defects found during inspection (fix order per PR review):

1. `build_harmony_conversation` drops `AIMessage.tool_calls` and maps
   `ToolMessage` to `Role.USER` instead of a tool response → broken tool loop.
2. `_stream` does not stream; it replays one non-streaming response as a
   single chunk. llama-server SSE (`stream: true`) + `StreamableParser` needed.
3. Model exposes no `profile` capability dict for dcode's negotiation.
4. `apply_patch`: no `*** Move to:`, CRLF/trailing-newline not preserved,
   ambiguous context not detected, no validate-before-write/rollback, no
   `O_NOFOLLOW`/`dir_fd` hardening.
5. Tool contract decided: `apply_patch(patch: str)` (paths live inside the
   patch text per GPT-OSS grammar); document instead of splitting path+patch.

Protocol for this round: failing test first (recorded), smallest fix, rerun,
commit+push each coherent unit, update HANDOFF/MILESTONES/README.
