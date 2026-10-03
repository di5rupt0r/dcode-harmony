# Getting started

> Tutorial. You will go from a fresh clone to running `dcode` against a local
> GPT-OSS model in about ten minutes.

## 1. Prerequisites

- Linux or macOS with Python 3.12+ (developed on CPython 3.14 via `uv`).
- A `llama-server` binary from llama.cpp.
- ~12 GB of free RAM to serve the GPT-OSS 20B GGUF (Q4_K_M class).

## 2. Install

```bash
git clone https://github.com/di5rupt0r/dcode-harmony.git
cd dcode-harmony
python -m venv .venv
. .venv/bin/activate
python -m pip install .
```

## 3. Start the model server

```bash
llama-server -hfr unsloth/gpt-oss-20b-GGUF -cmoe -fa on -ctk q8_0 -ctv q4_0 -t 4
```

Wait until `curl localhost:8080/health` returns `{"status":"ok"}` (model load
takes a few minutes; a `503` during startup is normal).

## 4. Run dcode

```bash
dcode
```

On first run, dcode-harmony writes a bootstrap `config.toml` into
`~/.dcode-harmony` (override with `DEEPAGENTS_HOME`) and selects the local
Harmony provider. No further configuration is needed.

## 5. Verify

Ask dcode a question; the provider talks to
`http://127.0.0.1:8080/completion` using native Harmony tokens. To validate
the whole stack with the real model:

```bash
pytest -m live -q
```

## Next steps

- [Run llama-server as a systemd service](../how-to/run-llama-server.md)
- [Configure the dcode profile](../how-to/configure-profile.md)
- [Architecture reference](../reference/architecture.md)
