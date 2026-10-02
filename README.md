# dcode-harmony

Standalone, plug-and-play distribution layer for running dcode with a local GPT-OSS model served by `llama-server` through the native Harmony/raw-completion protocol.

> **Status: first working slice.** The repository now installs and exposes `dcode`, bootstraps a local Harmony default provider config, registers an `apply_patch` extension tool, and includes test coverage for launcher defaults, provider parsing/HTTP boundaries, and patch safety.

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

Current implementation includes:

- pinned package dependencies for `deepagents-code`, `deepagents`, and `openai-harmony`;
- `dcode` launcher bootstrap that writes an isolated `~/.dcode-harmony/config.toml`;
- default model/provider selection to `local-harmony:gpt-oss-20b`;
- a `BaseChatModel` provider that posts to `/completion`;
- Harmony message conversion/parsing helpers using verified `openai-harmony` classes;
- `apply_patch` as a Python extension tool registered through `dcode.extensions`.

Remaining work is tracked in milestones for stronger native Harmony token rendering/parsing and broader live integration validation.

## Current user experience

After the project is complete:

```bash
git clone https://github.com/di5rupt0r/dcode-harmony.git
cd dcode-harmony
python -m venv .venv
. .venv/bin/activate
python -m pip install .

# llama-server is already running as a systemd service on localhost:8080
dcode
```

Advanced configuration may be supported later, but the default path already avoids manual provider setup for the first launch.

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

The fallback selected must be documented with the pinned versions and its upgrade cost.

## Test-first rule

Tests precede implementation. This is a project rule, not a suggestion:

1. write a failing test for the behavior;
2. run it and record the failure;
3. implement the smallest change;
4. run focused and broader validation;
5. document the result in `HANDOFF.md`.

Internal filesystem, formatting, parsing, and safety logic must use real tests. Mocking is allowed only at external dependency boundaries, such as HTTP transport to a separately running llama-server. No mock may replace the real patch application or Harmony parser behavior.

## Documentation and handoff

- [`HANDOFF.md`](HANDOFF.md): operational state, decisions, validation, and continuation instructions.
- [`MILESTONES.md`](MILESTONES.md): authoritative roadmap and acceptance criteria.

Every agent must update both documents before handing work to another agent.

## License and provenance

The implementation layer is intended to remain separately licensed as documented when code is added. Upstream dcode provenance, source commit, and license details must be recorded before importing any source or copying substantial documentation from `langchain-ai/deepagents`.
