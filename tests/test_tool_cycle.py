"""Full-cycle tool test: provider -> tool -> ToolMessage (§P1.4)."""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import json
from pathlib import Path

import httpx
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from dcode_harmony.providers.harmony import (
    HarmonyCompletionChatModel,
    build_harmony_conversation,
)
from openai_harmony import HarmonyEncodingName, Role, load_harmony_encoding

_ENCODING = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)


def _realistic_stream_response() -> bytes:
    tokens = _ENCODING.encode(
        'to=functions.apply_patch<|channel|>commentary json'
        '<|message|>{"patch": "*** Begin Patch\\n*** Add File: hi.txt\\n+hi\\n*** End Patch"}<|call|>',
        allowed_special="all",
    )
    return (
        b"data: "
        + json.dumps({"content": "", "tokens": tokens, "stop": True}).encode()
        + b"\n\n"
    )


def test_full_tool_cycle_with_real_encoding_and_registry(tmp_path: Path) -> None:
    # 1. Load apply_patch through the real extension entry point.
    entry = next(
        ep
        for ep in importlib.metadata.entry_points(group="dcode.extensions")
        if ep.name == "dcode_harmony"
    )
    module_name = entry.value.partition(":")[0]
    spec = importlib.util.find_spec(module_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from deepagents_code.extensions.api import ExtensionAPI, ExtensionMode
    from deepagents_code.extensions.registry import ExtensionRegistry, SourceInfo

    registry = ExtensionRegistry()
    api = ExtensionAPI(
        registry,
        SourceInfo(Path(spec.origin), is_package=True),
        cwd=tmp_path,
        mode=ExtensionMode.HEADLESS,
    )
    asyncio.run(module.extension(api))
    tool = registry.tools[0].unit
    assert tool.name == "apply_patch"

    # 2. bind_tools threads the real tool schema into the provider.
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        rendered = _ENCODING.decode(body["prompt"])
        assert "functions.apply_patch" in rendered or "apply_patch" in rendered
        tokens = _ENCODING.encode(
            'to=functions.apply_patch<|channel|>commentary json'
            '<|message|>{"patch": "*** Begin Patch\\n*** Add File: hi.txt\\n+hi\\n*** End Patch"}<|call|>',
            allowed_special="all",
        )
        return httpx.Response(
            200,
            json={"content": "", "tokens": tokens, "stop": True},
        )

    model = HarmonyCompletionChatModel(
        model="gpt-oss-20b",
        transport=httpx.MockTransport(handler),
    )
    result = model.bind_tools([tool]).invoke([HumanMessage("create hi.txt")])

    # 3. The provider surfaces a real AIMessage.tool_calls.
    assert result.tool_calls
    call = result.tool_calls[0]
    assert call["name"] == "apply_patch"
    assert isinstance(call["args"], dict) and isinstance(call["args"]["patch"], str)

    # 4. Execute the tool for real, then render the ToolMessage back into Harmony.
    outcome = tool.invoke({"patch": call["args"]["patch"]})
    assert "Added hi.txt" in outcome
    assert (tmp_path / "hi.txt").read_text(encoding="utf-8") == "hi\n"

    followup = build_harmony_conversation(
        [
            SystemMessage("rules"),
            HumanMessage("create hi.txt"),
            result,
            ToolMessage(content=outcome, tool_call_id=call["id"], name="apply_patch"),
        ]
    )
    rendered = _ENCODING.decode(_ENCODING.render_conversation(followup))
    assert "to=functions.apply_patch" in rendered
    assert "<|start|>apply_patch<|message|>" in rendered
