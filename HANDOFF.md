# Handoff

## Current state

- Date: 2026-10-03
- Repository: `di5rupt0r/dcode-harmony`
- Branch / PR: `docs/standardize-rectify` (PR #2)
- Scope of this PR (fixed): documentation rectification, standardization, and aesthetics only (README, MILESTONES, HANDOFF)
- Out of scope: any code/behavior change, reasoning_effort (PR #3), latency investigation (PR #4), M6

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

### 2026-10-02 — Review-fix round results (PR #1 not merge-ready → M1–M4 done)

Commands actually executed (all on this host, 2026-10-02):

- `uv venv` rebuild with uv-managed CPython 3.14.7; `uv pip install -e ".[dev]"`
  → deepagents-code 0.1.80, deepagents 0.7.21, openai-harmony 0.0.8,
  langchain-core 1.6.6, httpx 0.28.1, pytest 8.4.2.
- `pytest -q` after repairing conflict markers: 16 passed, 4 skipped.
- Per-fix failing-test-first commits: `282b65b` (tool history), `6d8e2a1`
  (SSE streaming), parsing matrix `0c089fe`, apply_patch `4795718`,
  extension registry `5b9f92b`, launcher exit-code `b52d44b`.
- Latest full run: `55 passed, 8 skipped` (8 = live, server absent).
- Clean env: `/tmp/opencode/cleanenv` venv, `uv pip install .`,
  `dcode --help` → deepagents-code v0.1.80 banner, `import
  dcode_harmony/deepagents_code/openai_harmony` OK.
- `python -m build` → wheel + sdist built; dist/ and egg-info removed after.
- Real llama-server: NOT running on this host (no llama service, ~6 GB free
  RAM vs ~12 GB needed for Q4_K_M gguf). `pytest -m live` → `8 skipped`.
  No live validation was performed; do not claim otherwise.
- Mocks used only at HTTP transport (httpx.MockTransport) and one subprocess
  boundary for extension/dcode config tests. Everything else real.

Decisions recorded:

- Tokens are authoritative for prompts and parsing; JSON fallback only when
  tokens are absent (plain-text final messages).
- `apply_patch` accepts only the GPT-OSS `*** Begin Patch` grammar; unified
  diff explicitly rejected. Schema keeps single `patch: str` argument.
- Streaming is real SSE (`stream: true`); analysis channel content is never
  emitted as visible chunks; tool calls surface as complete chunks on close.
- Multi-file patches validate before writing and roll back on failure.
- No dnf packages installed; the `uv`-managed interpreter was sufficient.

Remaining risks: live validation pending; no CI (default local pytest is the
gate); lockfile policy (M6) deferred; tool-call partial args not streamed.

Recommendation: do not merge until an operator runs `pytest -m live` against
a running llama-server (M5) and CI or an equivalent local gate is wired.

### 2026-10-02 — Live-validation and hardening round (start)

- llama-server became available: `llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk q8_0 -ctv q4_0 -t 4` on 127.0.0.1:8080 (GPT-OSS 20B GGUF, ~6 GB RSS).
- First `pytest -m live`: 6 failed/1 passed/1 skipped because the model was still loading and old tests used small timeouts and lax assertions.
- Second run (server warm): 3 failed/5 passed/1 skipped, failures are old live tests timing out (httpx.ReadTimeout at 10–30 s budgets) — model is slow on CPU/low RAM.
- Round scope per operator prompt: harden live tests, dedupe streaming
  tool-call counting, close `analysis` leak on no-token SSE events, secure
  `Move to` rollback, TOCTOU decision, strengthen tool binding/tool_choice
  contract, honest docs (M5 only after real validation).
- Server facts: GPT-OSS 20B GGUF (unsloth/gpt-oss-20b-GGUF);
  launch: `llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk
  q8_0 -ctv q4_0 -t 4`; endpoint http://127.0.0.1:8080.
- `/health`: initially `503 {"error":{"message":"Loading model"...}}` during
  model load; after ~5 min, `200`.
- Old live tests `test_live_llama_server_normal_completion` / `_error_handling` / `_completion_smoke` failed with `httpx.ReadTimeout` (10–30 s budgets too small for this CPU-only host).
- Passing: provider integration, harmony parsing, streaming, tool-call shape, normal completion (after generous timeout), health shape.

### 2026-10-02 — Live-validation and hardening round (results)

- Commits: start `3d35398` → live-rewrite `e9492be` → SSE sentinel fix
  `70911bc` → dedupe/leak `1686c92` → tool_choice `b595ad2` → full cycle
  `2a98b10` → Move-rollback hardening `8828692` → TOCTOU doc `7169e9c` →
  HTTP error tests `03ad1ba` → ruff/lint `c848d13` → M5 DONE `009ea4c`.
- Tests written before code each time (recorded failing runs in session):
  streaming dedupe/leak matrix (`2c0786c`), Move/rollback/newlines
  (`e970c6a`), tool_choice rejection, HTTP error contract.
- Real server facts: model `unsloth/gpt-oss-20b-GGUF`, endpoint
  127.0.0.1:8080; `/health` 200 when loaded, 503 while loading; SSE events
  carry `index/content/tokens/stop/id_slot/tokens_predicted/tokens_evaluated`;
  no `[DONE]` sentinel (stream ends with `stop: true`).
- Real probes: invoke returned `content="ok"`; stream gave 8 chunks
  `"1, 2, 3"`; bind_tools produced a genuine
  `functions.apply_patch` call with a valid patch that created hello.txt.
- Suite totals: `pytest -q` → 78 passed; `pytest -m live` → 6 passed;
  `ruff check` + `ruff format --check` pass; `ty check src/` clean.
- Clean env: `uv pip install .` + `DEEPAGENTS_HOME=$(mktemp -d) dcode
  --help` works, config.toml created, no `~/.dcode-harmony` leakage.
- `python -m build` succeeds.
- Recommendation: M5 criteria are now genuinely met; remaining gate before
  merge is operator CI wiring (M6). Code/documentation state is consistent;
  leave merge decision to the maintainer.

### 2026-10-02 — Final consistency round (P0 parsing, docs, SSE, errors, tests)

Commits this round: `e1fad88` (parse fallback fix), `caf5b0f`/`89ecb4b`
(docs sync + live scope), `8a5a374` (SSE test contract), `ba451aa` (error
contract doc), `dcafed3` (stronger assertion), `0a69eed` (format pass).

- P0 fixes landed: `parse_harmony_completion` no longer unpacks JSON-looking
  text (`"42"`, `"{}"`, `'["a","b"]'` are plain content); empty payload+
  tokens → empty `AIMessage`; non-empty tokens always take priority. Failing
  tests added first and recorded; JSON-envelope removal confirmed against all
  call sites (no production caller passed invented JSON — only stale tests,
  which were migrated to real token streams).
- Docs synchronized: README/MILESTONES/HANDOFF all say M1–M5 DONE, live
  validated 2026-10-02 against `unsloth/gpt-oss-20b-GGUF` on
  http://127.0.0.1:8080 (`llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe
  -fa on -ctk q8_0 -ctv q4_0 -t 4`); live result 6 passed; M6 TODO; no CI
  claims; explicit list of what live validation did and did not cover.
- Synthetic SSE tests now model the real contract (events → `stop: true` →
  close; no `[DONE]`); a single compatibility test keeps `[DONE]` accepted.
- Error contract fixed to Option B (propagate httpx; no unified wrapper);
  README section added; MILESTONES claim aligned.
- Live apply_patch test retains strict assertions and applies the patch in
  `tmp_path`.

Final validation (this host, this round):

- `pytest -m "not live" -q` → **77 passed, 6 deselected**
- `pytest -m live -q` → **6 passed** (server up: gpt-oss-20b GGUF)
- `pytest -q` → **83 passed**
- `ruff check .` → pass; `ruff format --check .` → pass; `ty check src/` → pass
- clean venv: `uv pip install .` OK; `DEEPAGENTS_HOME=$(mktemp -d) dcode
  --help` prints deepagents-code v0.1.80
- `python -m build` → wheel + sdist

Recommendation: **approve after condition X** — as the round required, all
gates pass; the only outstanding item is M6 (CI/lockfile/release policy),
which must land as a follow-up PR before calling the project fully
maintainable. No merge was performed.

### 2026-10-02 — Review-fix round 2 (same-path composition, EOF anchor, atomic writes, docs)

Commits: `befdcf3` (failing tests), `2716b1c` (same-path virtual state in
`_plan`, EOF-anchored ambiguity filter, atomic tmp+replace writes, move
rollback test), `4af0924` (M5/README sync), `c1c227c` (launcher env-override
test via real `run_dcode`), `18b6063` (format/validation).

- `_plan` now tracks virtual bytes per path so repeated Add/Update/Delete/
  Move on the same path compose in order (previously second write silently
  overwrote the first).
- `*** End of File` now disambiguates context: EOF-anchored hunk filters
  matches to those ending at file end before the ambiguity check.
- `_write_bytes_secure` writes to a temp file in the same directory,
  fsyncs, then `os.replace`s — a failed write never truncates the target.
- Rollback covers the move window (destination unlinked, source restored),
  and directories created during a reverted patch are removed.
- Rollback of a move verified by a real I/O failure (unwritable
  subdirectory), no internal mocking.
- MILESTONES M5 scope text aligned (no longer says "follow-up PR"); README
  no longer contradicts the live-validation section.
- Launcher test now exercises `run_dcode`'s DEEPAGENTS_HOME selection
  directly.

Final validation (this host, this round):

- `pytest -m "not live" -q` → **82 passed, 6 deselected**
- `pytest -m live -q` → **6 passed** (server live)
- `pytest -q` → **88 passed**
- `ruff check .` → pass; `ruff format --check .` → pass; `ty check src/` → pass
- clean install + `dcode --help` OK; `python -m build` OK

Recommendation: **approve after condition X** — all gates pass and docs are
consistent; M6 (CI/lockfile/release) remains the explicit follow-up. No
merge performed.

### 2026-10-02 — Review-fix round 3 (atomic writes, EOF insertion, modes, long names, README)

Commits: `3ad0a11` (failing tests), `32b3e0a` (mode preservation, EOF-insert
append, short temp basenames, writable-parent check at plan time, staged-temp
cleanup, tests), `a95f22e` (README status/counts sync), `d31ffbd` (format).

- Insertion-only EOF hunks now append at `len(haystack)` (fix applied from
  the review's suggestion, with a filesystem test).
- Updates preserve the original permission bits (staged temp chmodded before
  `os.replace`; rollback restores the original mode too).
- Temp files use a short fixed prefix + random suffix — long names near the
  component limit (240 bytes) work now.
- Planning rejects writes whose target's parent directory is not writable,
  with a clear `PatchError` — writable files in read-only dirs now fail at
  planning time instead of mid-execution.
- A failed `os.replace` unlinks the staged temp; no `.dcode-tmp-*` leftovers.
- README status header and suite counts aligned (M1–M5 DONE, 88 tests,
  live section consistent).

Final validation (this host):

- `pytest -m "not live" -q` → **88 passed, 6 deselected**
- `pytest -m live -q` → **6 passed**
- `pytest -q` → **94 passed**
- `ruff check .` / `ruff format --check .` → pass; `ty check src/` → pass

Recommendation: **approve after condition X** — M6 (CI/lockfile/release) is
the only remaining follow-up. No merge performed.

### 2026-10-02 — Review-fix round 4 (virtual modes, chmod cleanup, README count)

Commits: `30e1985` (virtual mode tracking, chmod failure cleanup,
chmod-failure test), `4007c30` (README count, syscall-boundary docs).

- `_plan` now carries a virtual mode per path (`modes` dict) alongside the
  byte state; a later update resolves its mode from that state instead of
  reading the physical file. Delete→Add→Update on the same path now yields
  the add's default mode, not the deleted file's mode.
- `os.chmod` and `os.replace` in `_write_bytes_secure` share one
  cleanup-protected block: any failure unlinks the staged temp.
- chmod-failure regression test added with an explicit docstring
  justification for syscall-level fault injection (verified: `chattr +i`
  is EPERM on this host, no read-only tmpfs available, so no user-space
  boundary exists for "write ok, chmod denied").
- The rewrite/move tests for read-only dirs and replace failure are the
  plan-time guard (PATCH is rejected before any write) and the same
  documented fault-injection boundary, respectively — AGENTS.md's
  "no internal mocks" rule targets parsers/filesystem logic, not libc
  stubs used for fault injection.
- README suite accounting: 96 total (90 + 6 live).

Final validation: `pytest -q` → **96 passed**; ruff check/format pass;
`ty check src/` pass.

Recommendation: **approve after condition X** — M6 follow-up only. No merge.

### 2026-10-03 — PR #2 docs standardization (start)

Intent: rectify contradictions between README/MILESTONES/HANDOFF, standardize
language and structure, and polish aesthetics. Docs-only PR; the test-first
rule is N/A at the code level — validation is (a) real `pytest` counts cited,
(b) all relative links resolve, (c) no code diffs.

Addendum (same PR, user feedback): the README was too polluted and WIP-looking.
Restructure per user direction:

- Adopt the Diátaxis model (tutorials / how-to guides / reference /
  explanation) under `docs/`.
- README becomes a lean entry point: one-paragraph intro, quickstart, status
  badges-as-list, and links into `docs/`.
- Add `llms.txt` at root: an index of every doc file with a one-line summary,
  so AI agents can navigate without scraping.
- HANDOFF.md / MILESTONES.md / AGENTS.md stay at root (agent-facing protocol
  docs); user/operational docs move under `docs/`.

Decisions:

1. Documentation language is English across all files (AGENTS.md already is;
   README's "Escopo da validação"/"Não validado live" sections were PT).
2. HANDOFF keeps the append-only session/change log; "Current state" stays a
   short summary pointing at the active PR.
3. README gains a TOC and tables where lists mixed concerns (validation
   results, live scope), keeping every existing fact verbatim where true.
4. Suite-count claims must match the last real run (2026-10-03: 91 passed,
   6 live-deselected; full run 97 passed).

### 2026-10-03 — PR #2 docs standardization (result)

- README TOC added; Portuguese sections ("Escopo da validação",
  "Validado live", "Não validado live") translated to English; scope
  wording de-personalized (no stale "this PR" pointers); PT recommendation
  lines translated; typo fixed.
- HANDOFF session log kept append-only; current-state header now points to
  PR #2. MILESTONES header now states PR #1 merged M1–M5, PR #2/#3/#4 roles.
- Validation: docs-only diff vs main (`git diff main --stat` → *.md only);
  `pytest -m "not live" -q` → 91 passed, 6 deselected (unchanged; expected,
  no code touched).

### 2026-10-03 — Rollback coverage narrowed to post-planning failure

Commit `bfcbc1a`. Added `test_rollback_after_post_planning_failure`
(execution-time `os.replace` failure for the second op rolls back the
first update, restores mode, removes created dirs, leaves no staged
temps). M3 milestone wording narrowed accordingly. The unwritable-dir
tests remain as plan-time rejection, not rollback coverage.

`pytest -m "not live" -q` → 91 passed, 6 deselected.
