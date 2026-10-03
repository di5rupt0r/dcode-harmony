# Install from source

> How-to guide.

```bash
git clone https://github.com/di5rupt0r/dcode-harmony.git
cd dcode-harmony
python -m venv .venv && . .venv/bin/activate
python -m pip install .
```

Development install (editable + dev extras):

```bash
python -m pip install -e ".[dev]"
```

Verify:

```bash
dcode --help
python -m pytest -m "not live" -q
```

The `.[dev]` extra provides `pytest` only. To run lint/type checks, install
them separately:

```bash
python -m pip install ruff ty
ruff check . && ruff format --check . && ty check src/
```

The published dependency pins (`deepagents-code`, `deepagents`,
`openai-harmony`) are recorded in [reference/dependencies.md](../reference/dependencies.md).
