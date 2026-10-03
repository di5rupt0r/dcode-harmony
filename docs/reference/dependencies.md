# Dependencies

> Reference.

The project depends on published packages — not on copying the upstream
monorepo.

| Package | Pinned version | Role |
|---|---|---|
| `deepagents-code` | `==0.1.80` | dcode runtime (declares `deepagents==0.7.21`) |
| `deepagents` | `==0.7.21` | agent runtime, pinned explicitly |
| `openai-harmony` | `==0.0.8` | Harmony render/parse/stream |

Monorepo-local `uv` path overrides are not used. Versions were verified from
published wheel metadata.
