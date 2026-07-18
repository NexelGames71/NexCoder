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


_WRITE_PATH_RE = re.compile(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"')
_WRITE_CONTENT_RE = re.compile(r'"content"\s*:\s*"')
_WRITE_APPEND_RE = re.compile(r'"append"\s*:\s*true')


def salvage_truncated_write(raw: str) -> ToolCall | None:
    """Recover a write_file call cut off by the output token cap.

    Small models retry the same oversized call forever; salvaging the
    partial content turns every truncation into forward progress — the
    loop writes what arrived and asks for the rest via append=true.
    Returns None unless a path and a meaningful amount of content can
    be recovered.
    """
    start = raw.rfind("<tool_call>")
    body = raw[start:] if start != -1 else raw
    if '"write_file"' not in body:
        return None
    path_match = _WRITE_PATH_RE.search(body)
    content_match = _WRITE_CONTENT_RE.search(body)
    if not path_match or not content_match:
        return None
    try:
        path = json.loads(f'"{path_match.group(1)}"')
    except json.JSONDecodeError:
        return None
    fragment = body[content_match.end():]
    # The JSON string was cut mid-way: it has no closing quote (or the
    # tail after it failed to parse — handled by normal parsing). Trim
    # back to the last cleanly-decodable point.
    for _ in range(8):
        if not fragment:
            return None
        # A trailing odd-length backslash run is an incomplete escape.
        stripped = fragment.rstrip("\\")
        if (len(fragment) - len(stripped)) % 2 == 1:
            fragment = fragment[:-1]
        try:
            content = json.loads(f'"{fragment}"')
            break
        except json.JSONDecodeError:
            fragment = fragment[:-1]
    else:
        return None
    if len(content) < 200:
        return None  # not worth salvaging; a retry is cheaper
    args: dict[str, Any] = {"path": path, "content": content}
    if _WRITE_APPEND_RE.search(body[:content_match.start()]):
        args["append"] = True
    return ToolCall(id=_new_call_id(), name="write_file", args=args)


def dedupe_salvaged_write(existing: str,
                          content: str) -> tuple[str, bool] | None:
    """Reconcile a salvaged full-file rewrite with what is already on disk.

    Small models retry the whole file instead of appending, so the second
    salvage usually re-contains the first. Returning only the new tail
    (as an append) makes every truncated attempt monotonic progress.
    Returns ``(content_to_write, append)`` or ``None`` when the attempt
    adds nothing new.
    """
    if not existing:
        return content, False
    if content.startswith(existing):
        remainder = content[len(existing):]
        return (remainder, True) if remainder else None
    if existing.startswith(content):
        return None  # shorter prefix of what we already have — no progress
    return content, False  # diverged: take the fresh attempt wholesale


# Hermes/Qwen-native form: the tool name lives inside the JSON body.
# Qwen2.5 models are trained on this exact shape, so the XML adapter
# teaches it in the prompt and accepts it (plus the legacy attribute form).
QWEN_TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>")

# Lenient salvage for small models: a fenced JSON object that has exactly
# the tool-call shape ({"name": str, "arguments": dict}) is treated as a
# tool call. Anything else in a fence is left untouched.
FENCED_JSON_PATTERN = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```")


def _tool_call_shape(payload: Any) -> tuple[str, dict[str, Any]] | None:
    """Return (name, args) when payload is exactly tool-call shaped."""
    if not isinstance(payload, dict) or not set(payload) <= {"name", "arguments"}:
        return None
    name = payload.get("name")
    arguments = payload.get("arguments")
    if not isinstance(name, str) or not name:
        return None
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return None
    return name, arguments


def _fenced_tool_call(body: str) -> tuple[str, dict[str, Any]] | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return _tool_call_shape(payload)


def _extract_bare_json_calls(text: str, calls: list[ToolCall]) -> str:
    """Consume unmarked top-level JSON objects that are tool-call shaped."""
    decoder = json.JSONDecoder()
    out: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "{":
            try:
                payload, end = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                out.append(text[index])
                index += 1
                continue
            shaped = _tool_call_shape(payload)
            if shaped is not None:
                calls.append(ToolCall(id=_new_call_id(), name=shaped[0], args=shaped[1]))
            else:
                out.append(text[index:end])
            index = end
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


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

        # Unclosed opener: models sometimes drop the </tool_call> tag (or
        # the stream ended right after the JSON). If everything after the
        # opener parses as a complete tool-call JSON, accept it; genuinely
        # truncated JSON still fails and takes the retry path.
        open_index = stripped.find("<tool_call>")
        if open_index != -1:
            body = stripped[open_index + len("<tool_call>"):].strip()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = None
            shape = _tool_call_shape(payload) if payload is not None else None
            if shape is not None:
                calls.append(ToolCall(id=_new_call_id(),
                                      name=shape[0], args=shape[1]))
                stripped = stripped[:open_index]

        def consume_fenced(match: re.Match) -> str:
            parsed = _fenced_tool_call(match.group(1))
            if parsed is None:
                return match.group(0)  # not a tool call — keep the fence
            name, arguments = parsed
            calls.append(ToolCall(id=_new_call_id(), name=name, args=arguments))
            return ""

        stripped = FENCED_JSON_PATTERN.sub(consume_fenced, stripped)
        stripped = _extract_bare_json_calls(stripped, calls)

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
