"""Parse model tool-call markup into structured agent actions."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


TOOL_CALL_PATTERN = re.compile(r'<tool_call\s+name="([^"]+)">([\s\S]*?)</tool_call>')


@dataclass(frozen=True)
class ParsedToolCall:
    type: str
    tool: str
    args: dict[str, Any]
    raw: str

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "tool": self.tool,
            "args": self.args,
        }


class ToolCallParseError(ValueError):
    """Raised when a model emits malformed tool-call markup."""


def parse_tool_calls(text: str) -> list[ParsedToolCall]:
    calls: list[ParsedToolCall] = []
    for match in TOOL_CALL_PATTERN.finditer(text or ""):
        tool = match.group(1).strip()
        args_text = match.group(2).strip()
        if not tool:
            raise ToolCallParseError("tool_call is missing a tool name")

        if not args_text:
            args: dict[str, Any] = {}
        else:
            try:
                parsed = json.loads(args_text)
            except json.JSONDecodeError as exc:
                raise ToolCallParseError(
                    f"tool_call {tool!r} has invalid JSON args: {exc.msg}"
                ) from exc
            if not isinstance(parsed, dict):
                raise ToolCallParseError(
                    f"tool_call {tool!r} args must be a JSON object"
                )
            args = parsed

        calls.append(ParsedToolCall(type="tool_call", tool=tool, args=args, raw=match.group(0)))
    return calls


def strip_tool_calls(text: str) -> str:
    """Remove complete tool-call XML blocks from model-visible prose."""
    return TOOL_CALL_PATTERN.sub("", text or "")
