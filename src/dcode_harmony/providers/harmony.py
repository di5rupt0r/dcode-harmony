"""Harmony-compatible BaseChatModel provider for llama.cpp /completion."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai_harmony import (
    Author,
    Conversation,
    DeveloperContent,
    HarmonyEncodingName,
    Message,
    Role,
    StreamableParser,
    ToolDescription,
    load_harmony_encoding,
)
from pydantic import Field

_ENCODING = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)


def _tool_descriptions(tools: list[dict[str, Any]] | None) -> list[ToolDescription]:
    if not tools:
        return []
    descriptions: list[ToolDescription] = []
    for item in tools:
        function = item.get("function", {}) if isinstance(item, dict) else {}
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        descriptions.append(
            ToolDescription(
                name=name,
                description=str(function.get("description", "")),
                parameters=function.get("parameters"),
            )
        )
    return descriptions


def build_harmony_conversation(
    messages: list[BaseMessage], tools: list[dict[str, Any]] | None = None
) -> Conversation:
    """Map LangChain messages into openai-harmony conversation structures."""
    harmony_messages: list[Message] = []
    tool_descriptions = _tool_descriptions(tools)
    if tool_descriptions:
        developer = DeveloperContent.new().with_function_tools(tool_descriptions)
        harmony_messages.append(
            Message.from_role_and_content(Role.DEVELOPER, developer)
        )
    for message in messages:
        if isinstance(message, SystemMessage):
            harmony_messages.append(
                Message.from_role_and_content(Role.SYSTEM, str(message.content))
            )
        elif isinstance(message, HumanMessage):
            harmony_messages.append(
                Message.from_role_and_content(Role.USER, str(message.content))
            )
        elif isinstance(message, AIMessage):
            content = str(message.content or "")
            if content.strip():
                harmony_messages.append(
                    Message.from_role_and_content(Role.ASSISTANT, content).with_channel(
                        "final"
                    )
                )
            for tool_call in getattr(message, "tool_calls", []) or []:
                name = (
                    tool_call.get("name")
                    if isinstance(tool_call, dict)
                    else tool_call.name
                )
                args = (
                    tool_call.get("args", {})
                    if isinstance(tool_call, dict)
                    else tool_call.args
                )
                harmony_messages.append(
                    Message.from_role_and_content(Role.ASSISTANT, json.dumps(args))
                    .with_channel("commentary")
                    .with_recipient(f"functions.{name}")
                )
        elif isinstance(message, ToolMessage):
            name = message.name or "tool"
            harmony_messages.append(
                Message.from_author_and_content(
                    Author.new(Role.TOOL, name), str(message.content)
                )
            )
        else:
            harmony_messages.append(
                Message.from_role_and_content(Role.USER, str(message.content))
            )
    return Conversation.from_messages(harmony_messages)


def _content_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, dict) and item.get("type") == "text":
                values.append(str(item.get("text", "")))
        return "".join(values)
    return ""


def parse_harmony_completion(
    payload: str, tokens: list[int] | None = None
) -> AIMessage:
    """Parse Harmony completion response into LangChain AIMessage."""
    # Tokens from `return_tokens` are authoritative; they parse even when the
    # text payload is empty (the server may send tokens only).
    if tokens:
        try:
            messages = _ENCODING.parse_messages_from_completion_tokens(
                tokens, Role.ASSISTANT
            )
        except Exception as exc:
            raise ValueError(f"Failed to parse completion tokens: {exc}") from exc
    else:
        if not payload:
            return AIMessage(content="")
        # Fallback: try JSON parsing, otherwise treat as plain text
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                raise ValueError("Malformed Harmony response: expected JSON list/dict")
            messages = [
                Message.from_dict(entry) for entry in data if isinstance(entry, dict)
            ]
        except json.JSONDecodeError:
            # Not JSON, treat as plain text final message
            return AIMessage(content=payload, tool_calls=[])

    final_chunks: list[str] = []
    commentary_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for msg in messages:
        text = _content_text(msg.to_dict().get("content", ""))
        channel = msg.channel or "final"
        recipient = msg.recipient

        if isinstance(recipient, str) and recipient.startswith("functions."):
            tool_name = recipient.split(".", 1)[1]
            try:
                tool_args = json.loads(text) if text else {}
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed tool-call arguments for {tool_name}"
                ) from exc
            if not isinstance(tool_args, dict):
                raise ValueError(f"Malformed tool-call arguments for {tool_name}")
            tool_calls.append(
                {
                    "name": tool_name,
                    "args": tool_args,
                    "id": f"call_{uuid.uuid4().hex}",
                    "type": "tool_call",
                }
            )
            continue

        if channel == "analysis":
            continue
        if channel == "commentary":
            commentary_chunks.append(text)
            continue
        final_chunks.append(text)

    content = "".join(final_chunks).strip() or "".join(commentary_chunks).strip()
    return AIMessage(content=content, tool_calls=tool_calls)


class HarmonyCompletionChatModel(BaseChatModel):
    """LangChain chat model for local Harmony `/completion` endpoint."""

    model: str
    base_url: str = "http://127.0.0.1:8080"
    completion_path: str = "/completion"
    timeout_s: float = 120.0
    max_tokens: int = 2048
    temperature: float = 0.0
    stop: list[str] = Field(default_factory=lambda: ["<|return|>", "<|call|>"])
    transport: httpx.BaseTransport | None = None
    profile: dict[str, Any] | None = Field(
        default_factory=lambda: {"tool_calling": True, "max_input_tokens": 32768}
    )

    @property
    def _llm_type(self) -> str:
        return "harmony_completion"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "completion_path": self.completion_path,
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Bind tools to the model for Harmony function calling."""
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        if tool_choice is not None and tool_choice != "auto":
            raise ValueError(
                f"Unsupported tool_choice {tool_choice!r}: Harmony completion "
                "only supports 'auto' (default) — tool selection is implicit "
                "in the model's channel/recipient output"
            )
        return self.bind(tools=formatted, **kwargs)

    def _payload(
        self,
        messages: list[BaseMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        conversation = build_harmony_conversation(messages, tools=tools)
        prompt_tokens = _ENCODING.render_conversation_for_completion(
            conversation, Role.ASSISTANT
        )
        payload: dict[str, Any] = {
            "prompt": prompt_tokens,
            "n_predict": self.max_tokens,
            "temperature": self.temperature,
            "stop": self.stop,
            "return_tokens": True,
        }
        if stream:
            payload["stream"] = True
        return payload

    def _post_completion(self, payload: dict[str, Any]) -> tuple[str, list[int] | None]:
        endpoint = f"{self.base_url.rstrip('/')}{self.completion_path}"
        with httpx.Client(timeout=self.timeout_s, transport=self.transport) as client:
            response = client.post(endpoint, json=payload)
        response.raise_for_status()
        body = response.json()
        content = body.get("content")
        tokens = body.get("tokens")
        if not isinstance(content, str):
            raise ValueError("Malformed completion response: missing string content")
        if tokens is not None and not isinstance(tokens, list):
            raise ValueError("Malformed completion response: tokens must be a list")
        return content, tokens

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        payload = self._payload(messages, tools=kwargs.get("tools"))
        if stop:
            payload["stop"] = stop
        content, tokens = self._post_completion(payload)
        ai = parse_harmony_completion(content, tokens=tokens)
        return ChatResult(generations=[ChatGeneration(message=ai)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        del run_manager
        payload = self._payload(messages, tools=kwargs.get("tools"), stream=True)
        if stop:
            payload["stop"] = stop
        endpoint = f"{self.base_url.rstrip('/')}{self.completion_path}"
        parser = StreamableParser(_ENCODING, Role.ASSISTANT)
        emitted_tool_messages = 0
        raw_fallback: list[str] = []
        with (
            httpx.Client(timeout=self.timeout_s, transport=self.transport) as client,
            client.stream("POST", endpoint, json=payload) as response,
        ):
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Malformed streaming event: {data!r}") from exc
                if not isinstance(event, dict):
                    raise ValueError("Malformed streaming event: expected object")
                chunk_tokens = event.get("tokens")
                if isinstance(chunk_tokens, list):
                    final_deltas: list[str] = []
                    for token in chunk_tokens:
                        if isinstance(token, int):
                            parser.process(token)
                            delta = parser.last_content_delta
                            if (
                                isinstance(delta, str)
                                and delta
                                and parser.current_channel == "final"
                            ):
                                final_deltas.append(delta)
                    if final_deltas:
                        yield ChatGenerationChunk(
                            message=AIMessageChunk(content="".join(final_deltas))
                        )
                else:
                    # Tokens are authoritative for channel filtering. When
                    # the server omits them we cannot distinguish analysis
                    # from final text, so we buffer and fail loudly if the
                    # buffered text contains Harmony markup instead of
                    # leaking raw channels to the UI.
                    content = event.get("content")
                    if isinstance(content, str) and content:
                        raw_fallback.append(content)
                messages_so_far = parser.messages
                for msg in messages_so_far[emitted_tool_messages:]:
                    recipient = msg.recipient if hasattr(msg, "recipient") else None
                    if isinstance(recipient, str) and recipient.startswith(
                        "functions."
                    ):
                        text = _content_text(msg.to_dict().get("content", ""))
                        tool_name = recipient.split(".", 1)[1]
                        try:
                            tool_args = json.loads(text) if text else {}
                        except json.JSONDecodeError:
                            tool_args = None
                        if isinstance(tool_args, dict):
                            yield ChatGenerationChunk(
                                message=AIMessageChunk(
                                    content="",
                                    tool_calls=[
                                        {
                                            "name": tool_name,
                                            "args": tool_args,
                                            "id": f"call_{uuid.uuid4().hex}",
                                            "type": "tool_call",
                                        }
                                    ],
                                )
                            )
                emitted_tool_messages = len(messages_so_far)
        # Fallback: no token-bearing events at all.
        if not parser.tokens and raw_fallback:
            joined = "".join(raw_fallback)
            if "<|" in joined:
                raise ValueError(
                    "Stream without tokens contains raw Harmony markup; "
                    "cannot safely separate channels"
                )
            if joined:
                yield ChatGenerationChunk(message=AIMessageChunk(content=joined))
