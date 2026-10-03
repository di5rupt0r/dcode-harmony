# Configure the dcode profile

> How-to guide.

- Default profile directory: `~/.dcode-harmony`
- Override: `DEEPAGENTS_HOME=/path/to/profile dcode`
- On first run the launcher writes a bootstrap `config.toml` that selects the
  local Harmony provider (`local-harmony:gpt-oss-20b`). An existing
  `config.toml` is never overwritten.
- When `DEEPAGENTS_HOME` is set, nothing is written to `~/.dcode-harmony`.

Reference: [reference/configuration.md](../reference/configuration.md).
