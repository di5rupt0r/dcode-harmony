"""Integration test: real extension API registration of apply_patch (§7)."""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
from pathlib import Path

import pytest

from deepagents_code.extensions.api import ExtensionAPI, ExtensionMode
from deepagents_code.extensions.registry import ExtensionRegistry, SourceInfo


def _load_entry_module():
    entry = next(
        ep
        for ep in importlib.metadata.entry_points(group="dcode.extensions")
        if ep.name == "dcode_harmony"
    )
    module_name = entry.value.partition(":")[0]
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, spec.origin


def test_extension_registers_apply_patch_via_real_api(tmp_path: Path) -> None:
    module, origin = _load_entry_module()
    registry = ExtensionRegistry()
    source = SourceInfo(Path(origin), is_package=True, source_id="dcode_harmony@entry-point")
    api = ExtensionAPI(registry, source, cwd=tmp_path, mode=ExtensionMode.HEADLESS)

    asyncio.run(module.extension(api))

    tools = registry.tools
    assert len(tools) == 1
    tool = tools[0].unit
    assert tool.name == "apply_patch"
    schema = tool.args_schema.model_json_schema()
    assert "patch" in schema["properties"]
    # And the registered tool actually patches files in the real workspace.
    (tmp_path / "a.txt").write_text("one\nold\n", encoding="utf-8")
    result = tool.invoke(
        {
            "patch": "*** Begin Patch\n*** Update File: a.txt\n@@\n one\n-old\n+new\n*** End Patch\n"
        }
    )
    assert "Updated a.txt" in result
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one\nnew\n"
