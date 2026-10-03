# Architecture

> Reference.

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

Integration preference order:

1. stable public dcode extension/tool-registration API;
2. supported dcode/deepagents agent-construction/configuration hooks;
3. the smallest compatibility shim, only if no public hook exists.

Package layout (`src/dcode_harmony`):

- `cli.py` — `dcode` entry point mapping `cli_main() -> None` to exit 0;
- `launcher.py` — profile bootstrap, `DEEPAGENTS_HOME` selection;
- `extensions.py` — `apply_patch` registration through `dcode.extensions`;
- `providers/harmony.py` — `HarmonyCompletionChatModel` (token prompt,
  token parse, tool binding, SSE streaming);
- `tools/apply_patch.py` — containment-safe patch application.
