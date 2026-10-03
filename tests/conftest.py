"""pytest configuration for the execution-trace harness.

When DCODE_TRACE_DIR is set (or --trace-dir is passed), every test gets a
per-test JSONL trace file. When unset, zero overhead and no files written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests._trace import TracingTransport, get_trace_dir

_active_transports: list[TracingTransport] = []


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--trace-dir",
        action="store",
        default=None,
        help="Directory for JSONL trace files (overrides DCODE_TRACE_DIR)",
    )


def pytest_configure(config: pytest.Config) -> None:
    # get_trace_dir() reads DCODE_TRACE_DIR; --trace-dir is handled by
    # setting the env var in pytest_configure if the option is provided.
    trace_dir_opt = config.getoption("--trace-dir")
    if trace_dir_opt:
        import os
        os.environ["DCODE_TRACE_DIR"] = trace_dir_opt


@pytest.fixture
def tracing_transport() -> Any:
    """Provide a TracingTransport for tests that want tracing.

    Yields None when tracing is disabled (DCODE_TRACE_DIR unset).
    """
    trace_dir = get_trace_dir()
    if trace_dir is None:
        yield None
        return

    import httpx

    inner = httpx.HTTPTransport()
    transport = TracingTransport(inner)
    _active_transports.append(transport)
    yield transport
    _active_transports.remove(transport)


def _write_trace_file(item: pytest.Item, transport: TracingTransport) -> Path | None:
    """Write all records from a transport to a per-test JSONL file."""
    trace_dir = get_trace_dir()
    if trace_dir is None or not transport.records:
        return None

    safe_name = item.nodeid.replace("/", "_").replace("::", "_")
    trace_file = trace_dir / f"{safe_name}.jsonl"
    trace_file.parent.mkdir(parents=True, exist_ok=True)

    with trace_file.open("w", encoding="utf-8") as f:
        for record in transport.records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return trace_file


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Any:
    """Write trace files and print path on failure."""
    outcome = yield
    report = outcome.get_result()

    if report.when != "call":
        return

    # Write trace files for all active transports
    written_files: list[Path] = []
    for transport in _active_transports:
        path = _write_trace_file(item, transport)
        if path:
            written_files.append(path)

    # Print trace path on failure
    if report.failed and written_files:
        for path in written_files:
            print(f"\nTrace file: {path}")
