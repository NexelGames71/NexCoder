"""Tool-call transport adapters.

The loop never knows how tool calls travel. XmlAdapter keeps the local
Qwen-7B path (calls embedded in text); NativeAdapter speaks the OpenAI
tools / tool_calls protocol for the future GPU-hosted model. Switching
backend = switching adapter, zero loop changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Protocol
import uuid

from nexcoder.agent.tool_call_parser import (
    ToolCallParseError, parse_tool_calls, strip_tool_calls,
)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    parse_error: str | None = None


class ToolCallAdapter(Protocol):
    def request_extras(self, schemas: list[dict[str, Any]]) -> dict[str, Any]: ...
    def system_prompt_suffix(self, schemas: list[dict[str, Any]]) -> str: ...
    def parse_assistant_message(self, message: dict[str, Any]) -> ModelTurn: ...
    def tool_result_messages(
        self, calls: list[ToolCall], results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


def _new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:8]}"


# Hermes/Qwen-native form: the tool name lives inside the JSON body.
# Qwen2.5 models are trained on this exact shape, so the XML adapter
# teaches it in the prompt and accepts it (plus the legacy attribute form).
QWEN_TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>")


class XmlAdapter:
    """Tool calls embedded in assistant text as <tool_call> blocks."""

    def request_extras(self, schemas: list[dict[str, Any]]) -> dict[str, Any]:
        return {}

    def system_prompt_suffix(self, schemas: list[dict[str, Any]]) -> str:
        lines = [
            "",
            "# Tools",
            "You act by calling tools. Emit each call as a block exactly like:",
            "<tool_call>",
            '{"name": "tool_name", "arguments": {"arg": "value"}}',
            "</tool_call>",
            "The body must be one valid JSON object with \"name\" and \"arguments\".",
            "Never print file contents in markdown code fences — create files "
            "with the write_file tool.",
            "",
            "Available tools:",
        ]
        for schema in schemas:
            fn = schema["function"]
            props = fn["parameters"].get("properties", {})
            required = set(fn["parameters"].get("required", []))
            args_desc = ", ".join(
                f"{name}{'' if name in required else '?'}: {spec.get('type', 'any')}"
                for name, spec in props.items())
            lines.append(f"- {fn['name']}({args_desc}) — {fn['description']}")
        lines += [
            "",
            "Only emit a tool_call block when you want the tool executed. "
            "When the task is complete, reply with plain text and no tool_call blocks.",
        ]
        return "\n".join(lines)

    def parse_assistant_message(self, message: dict[str, Any]) -> ModelTurn:
        text = str(message.get("content") or "")
        calls: list[ToolCall] = []
        parse_error: str | None = None

        # Legacy attribute form: <tool_call name="x">{...}</tool_call>
        try:
            for item in parse_tool_calls(text):
                calls.append(ToolCall(id=_new_call_id(), name=item.tool, args=item.args))
        except ToolCallParseError as exc:
            parse_error = str(exc)
        stripped = strip_tool_calls(text)

        # Qwen/Hermes form: <tool_call>{"name": ..., "arguments": {...}}</tool_call>
        def consume(match: re.Match) -> str:
            nonlocal parse_error
            body = match.group(1)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                parse_error = parse_error or f"tool_call has invalid JSON: {exc.msg}"
                return ""
            name = str((payload or {}).get("name") or "")
            arguments = (payload or {}).get("arguments")
            if not name:
                parse_error = parse_error or "tool_call JSON is missing a name"
                return ""
            if arguments is None:
                arguments = {}
            if not isinstance(arguments, dict):
                parse_error = parse_error or f"arguments for {name} must be a JSON object"
                return ""
            calls.append(ToolCall(id=_new_call_id(), name=name, args=arguments))
            return ""

        stripped = QWEN_TOOL_CALL_PATTERN.sub(consume, stripped)

        if parse_error:
            return ModelTurn(text=stripped.strip(), parse_error=parse_error)
        return ModelTurn(text=stripped.strip(), tool_calls=tuple(calls))

    def tool_result_messages(
        self, calls: list[ToolCall], results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        blocks = []
        for call, result in zip(calls, results):
            payload = json.dumps({"tool": call.name, "result": result},
                                 ensure_ascii=False, default=str)
            blocks.append(f"<tool_response>{payload}</tool_response>")
        return [{"role": "user", "content": "\n".join(blocks)}]


class NativeAdapter:
    """OpenAI tools / tool_calls protocol (vLLM, TGI, cloud APIs)."""

    def request_extras(self, schemas: list[dict[str, Any]]) -> dict[str, Any]:
        return {"tools": schemas} if schemas else {}

    def system_prompt_suffix(self, schemas: list[dict[str, Any]]) -> str:
        return ""

    def parse_assistant_message(self, message: dict[str, Any]) -> ModelTurn:
        calls: list[ToolCall] = []
        parse_error: str | None = None
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            name = str(fn.get("name") or "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                parse_error = f"Invalid JSON arguments for {name}: {exc.msg}"
                continue
            if not isinstance(args, dict):
                parse_error = f"Arguments for {name} must be a JSON object"
                continue
            calls.append(ToolCall(id=str(raw.get("id") or _new_call_id()),
                                  name=name, args=args))
        return ModelTurn(text=str(message.get("content") or "").strip(),
                         tool_calls=tuple(calls), parse_error=parse_error)

    def tool_result_messages(
        self, calls: list[ToolCall], results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {"role": "tool", "tool_call_id": call.id,
             "content": json.dumps(result, ensure_ascii=False, default=str)}
            for call, result in zip(calls, results)
        ]


def get_adapter(name: str) -> ToolCallAdapter:
    if name == "xml":
        return XmlAdapter()
    if name == "native":
        return NativeAdapter()
    raise ValueError(f"Unknown adapter: {name!r}")
