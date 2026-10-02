# dcode-harmony

Standalone, plug-and-play distribution layer for running dcode with a local GPT-OSS model served by `llama-server` through the native Harmony/raw-completion protocol.

> **Status: bootstrap only.** This repository currently contains project documentation and packaging direction. The provider, launcher integration, and `apply_patch` implementation are not complete yet.

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

This initial commit establishes the standalone project contract and handoff documentation. It deliberately does **not** claim that the following are implemented:

- Harmony prompt rendering or response parsing;
- raw llama.cpp `/completion` requests;
- automatic dcode launcher/provider integration;
- `apply_patch` execution;
- live llama-server validation.

Those features are separate milestones and must begin with meaningful tests before implementation code.

## Planned user experience

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

Advanced configuration may be supported later, but the default path must not require users to select a provider or edit dcode configuration.

## Dependency policy

The project will depend on published packages rather than copying the complete upstream SDK or dcode source:

- `deepagents-code`: pinned to an explicitly recorded compatible release;
- `deepagents`: pinned explicitly to the version required by that dcode release;
- `openai-harmony`: pinned to a verified compatible release;
- only small direct dependencies needed by the integration layer.

The exact versions must be verified against package metadata before they are committed. Monorepo-local `uv` path overrides must not be copied into this project.

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
