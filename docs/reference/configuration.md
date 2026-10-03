# Configuration

> Reference.

| Setting | Default | Override |
|---|---|---|
| Profile directory | `~/.dcode-harmony` | `DEEPAGENTS_HOME` env var |
| Provider | `local-harmony:gpt-oss-20b` | `config.toml` in profile |
| Endpoint | `http://127.0.0.1:8080/completion` | provider config |
| `config.toml` | written on first run | never overwritten once present |

The bootstrap `config.toml` is consumed by the real
`deepagents_code.config.create_model`; plain `dcode` needs no manual
provider/class-path configuration.
