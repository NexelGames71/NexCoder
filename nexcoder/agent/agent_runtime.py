"""Standalone structured agent runtime loop.

This module is intentionally small: the desktop app uses
``nexcoder.agent.runtime.AgentRuntime`` for Qt signal orchestration, while this
class provides the pure model/tool loop requested by the agent architecture.
"""

from __future__ import annotations

from typing import Any, Callable

from nexcoder.agent.executor import AgentExecutor
from nexcoder.agent.tool_call_parser import ToolCallParseError, parse_tool_calls, strip_tool_calls
from nexcoder.agent.tool_registry import ToolRegistry


class StructuredAgentRuntime:
    def __init__(
        self,
        model_client: Any,
        project_root: str,
        *,
        max_steps: int = 16,
        on_timeline: Callable[[dict[str, Any]], None] | None = None,
        on_diff: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.model = model_client
        self.project_root = project_root
        self.max_steps = max_steps
        self.timeline: list[dict[str, Any]] = []
        registry = ToolRegistry(project_root, on_diff=on_diff)
        self.executor = AgentExecutor(registry, on_timeline=self._record_timeline(on_timeline))

    def run(self, initial_messages: list[dict[str, str]]) -> dict[str, Any]:
        messages = list(initial_messages)

        for _step in range(self.max_steps):
            response_text = self.model.generate(messages)
            try:
                tool_calls = parse_tool_calls(response_text)
            except ToolCallParseError as exc:
                messages.append({
                    "role": "system",
                    "content": f"Tool call parse error: {exc}. Re-emit valid tool-call JSON.",
                })
                continue

            if not tool_calls:
                final = strip_tool_calls(response_text).strip()
                return {"type": "final", "final": final, "timeline": self.timeline}

            visible_text = strip_tool_calls(response_text).strip()
            if visible_text:
                messages.append({"role": "assistant", "content": visible_text})

            observations: list[str] = []
            for tool_call in tool_calls:
                _item, observation = self.executor.execute(tool_call)
                observations.append(observation)

            messages.append({
                "role": "system",
                "content": "Tool observations:\n" + "\n".join(observations),
            })

        return {
            "type": "blocked",
            "final": "Reached maximum tool iterations.",
            "timeline": self.timeline,
        }

    def _record_timeline(
        self,
        callback: Callable[[dict[str, Any]], None] | None,
    ) -> Callable[[dict[str, Any]], None]:
        def record(item: dict[str, Any]) -> None:
            existing = next((idx for idx, step in enumerate(self.timeline) if step["id"] == item["id"]), None)
            if existing is None:
                self.timeline.append(item)
            else:
                self.timeline[existing] = item
            if callback:
                callback(item)

        return record


AgentRuntime = StructuredAgentRuntime
