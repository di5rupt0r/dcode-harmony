# Run the tests

> How-to guide.

```bash
pytest -q                  # full suite; live tests skip without a server
pytest -m "not live" -q    # unit/integration only (no server needed)
pytest -m live -q          # requires llama-server on 127.0.0.1:8080
```

Current baseline (2026-10-03): `pytest -m "not live"` → 91 passed,
6 deselected; full suite → 97 passed (91 + 6 live).

Live tests exercise `/health`, `/completion` token contract, provider
`invoke`, streaming, SSE field/terminal shape, and a real `apply_patch`
tool call applied to a temporary workspace.

Lint/types gate (requires `ruff` and `ty`, not in `.[dev]`):

```bash
python -m pip install ruff ty
ruff check . && ruff format --check . && ty check src/
```
