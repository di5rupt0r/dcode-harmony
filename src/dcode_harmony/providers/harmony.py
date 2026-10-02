"""Harmony-compatible BaseChatModel provider for llama.cpp /completion."""

from __future__ import annotations

import json
import uuid
from typing import Any, Sequence

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai_harmony import (
    Conversation,
    DeveloperContent,
    HarmonyEncodingName,
    load_harmony_encoding,
    Message,
    Role,
    ToolDescription,
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
            harmony_messages.append(
                Message.from_role_and_content(Role.ASSISTANT, str(message.content))
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


def parse_harmony_completion(payload: str, tokens: list[int] | None = None) -> AIMessage:
    """Parse Harmony completion response into LangChain AIMessage."""
    if not payload:
        return AIMessage(content="")

    # If tokens are provided and non-empty, parse using Harmony encoding
    if tokens:
        try:
            messages = _ENCODING.parse_messages_from_completion_tokens(tokens, Role.ASSISTANT)
        except Exception as exc:
            raise ValueError(f"Failed to parse completion tokens: {exc}") from exc
    else:
        # Fallback: try JSON parsing, otherwise treat as plain text
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                raise ValueError("Malformed Harmony response: expected JSON list/dict")
            messages = [Message.from_dict(entry) for entry in data if isinstance(entry, dict)]
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
                raise ValueError(f"Malformed tool-call arguments for {tool_name}") from exc
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
        return self.bind(tools=formatted, **kwargs)

    def _payload(self, messages: list[BaseMessage], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        conversation = build_harmony_conversation(messages, tools=tools)
        prompt_tokens = _ENCODING.render_conversation_for_completion(conversation, Role.ASSISTANT)
        return {
            "prompt": prompt_tokens,
            "n_predict": self.max_tokens,
            "temperature": self.temperature,
            "stop": self.stop,
            "return_tokens": True,
        }

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
        payload = self._payload(messages, tools=kwargs.get("tools"))
        if stop:
            payload["stop"] = stop
        content, tokens = self._post_completion(payload)
        ai = parse_harmony_completion(content, tokens=tokens)
        chunk = AIMessageChunk(
            content=ai.content,
            additional_kwargs=ai.additional_kwargs,
            response_metadata=ai.response_metadata,
            tool_calls=ai.tool_calls,
        )
        yield ChatGenerationChunk(message=chunk)
