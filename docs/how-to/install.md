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
```

To run the test suite you also need the dev extra (contains pytest, ruff,
`ty`):

```bash
python -m pip install -e ".[dev]"
python -m pytest -m "not live" -q
```

The published dependency pins (`deepagents-code`, `deepagents`,
`openai-harmony`) are recorded in [reference/dependencies.md](../reference/dependencies.md).
