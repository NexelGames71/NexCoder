"""NexCoder agent package."""

from .executor import AgentExecutor
from .tool_call_parser import ParsedToolCall, parse_tool_calls, strip_tool_calls
from .tool_registry import ToolRegistry

__all__ = [
    "AgentExecutor",
    "ParsedToolCall",
    "ToolRegistry",
    "parse_tool_calls",
    "strip_tool_calls",
]
