"""Typed event stream shared by the agent loop, CLI renderer, and UI bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Literal

EventType = Literal[
    "run_started",
    "turn_started",
    "text_delta",
    "tool_started",
    "tool_streaming",
    "tool_result",
    "command_output",
    "todo_updated",
    "edit_applied",
    "permission_request",
    "permission_resolved",
    "checkpoint_created",
    "compaction",
    "context_usage",
    "run_completed",
    "run_error",
]


@dataclass(frozen=True)
class AgentEvent:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload, "ts": self.ts}


EventCallback = Callable[[AgentEvent], None]
