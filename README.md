# dcode-harmony

Standalone, plug-and-play distribution layer that runs `dcode` against a
local GPT-OSS model served by `llama-server`, using the native
Harmony/raw-completion protocol.

## Quickstart

```bash
python -m pip install .

# terminal 1 — stays in the foreground; wait for {"status":"ok"}
llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk q8_0 -ctv q4_0 -t 4

# terminal 2
dcode
```

Full walkthrough: [docs/tutorials/getting-started.md](docs/tutorials/getting-started.md).

## Status

| Milestone | State |
|---|---|
| M0–M5 (bootstrap → native Harmony provider → safe `apply_patch` → launcher → live validation) | DONE (merged in PR #1, 2026-10-02) |
| M6 (CI, lockfile/release policy) | TODO |

Suites: `pytest -q` → 97 passed (91 unit + 6 live, 2026-10-03). See
[docs/how-to/run-tests.md](docs/how-to/run-tests.md).

Open follow-ups:

- PR #2 — documentation overhaul;
- PR #3 — `reasoning_effort` support;
- PR #4 — latency investigation.

## Documentation

All user/operational docs live under [`docs/`](docs/README.md), organized by
Diátaxis (tutorials / how-to / reference / explanation). Machine-readable
index: [`llms.txt`](llms.txt).

Agent-facing protocol docs at the repo root:
[`AGENTS.md`](AGENTS.md) · [`HANDOFF.md`](HANDOFF.md) ·
[`MILESTONES.md`](MILESTONES.md).

## License and provenance

License details and upstream `deepagents` provenance must be recorded before
importing substantial upstream source or documentation; tracked in M6.
