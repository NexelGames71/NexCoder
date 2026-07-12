"""Message history with token accounting and two-stage compaction.

Stage 1: old tool results collapse to a one-line stub.
Stage 2: if still over budget, everything older than the protected recent
window is replaced by a model-written running summary.
The system prompt and the newest PROTECTED_RECENT messages always survive.
"""

from __future__ import annotations

import json
from typing import Any, Callable

Summarizer = Callable[[list[dict[str, Any]]], str]


def estimate_tokens(text: str) -> int:
    """Conservative chars/3 estimate (matches ModelConnector's heuristic)."""
    return max(1, (len(text or "") + 2) // 3)


def message_tokens(message: dict[str, Any]) -> int:
    content = str(message.get("content") or "")
    extra = json.dumps(message["tool_calls"]) if message.get("tool_calls") else ""
    return estimate_tokens(content) + (estimate_tokens(extra) if extra else 0) + 6


def _collapse_tool_content(content: str) -> str:
    first_line = (content or "").strip().splitlines()[0][:120] if content.strip() else ""
    return f"{first_line}\n[tool output collapsed: {len(content)} chars]"


class Conversation:
    PROTECTED_RECENT = 6

    def __init__(
        self,
        system_prompt: str,
        *,
        context_window: int = 8192,
        reserve_output: int = 3072,
        compact_threshold: float = 0.75,
    ) -> None:
        self.context_window = context_window
        self.reserve_output = reserve_output
        self.compact_threshold = compact_threshold
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}]

    def add(self, message: dict[str, Any]) -> None:
        self._messages.append(dict(message))

    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def payload_messages(self) -> list[dict[str, Any]]:
        """Messages ready for the API: private (underscore) keys stripped."""
        return [
            {key: value for key, value in message.items() if not key.startswith("_")}
            for message in self._messages
        ]

    @property
    def input_budget(self) -> int:
        return max(256, self.context_window - self.reserve_output)

    def total_tokens(self) -> int:
        return sum(message_tokens(message) for message in self._messages)

    def needs_compaction(self) -> bool:
        return self.total_tokens() > self.input_budget * self.compact_threshold

    def compact(self, summarizer: Summarizer | None = None) -> dict[str, int]:
        before = self.total_tokens()
        cutoff = max(1, len(self._messages) - self.PROTECTED_RECENT)

        for index in range(1, cutoff):
            message = self._messages[index]
            if message.get("_compacted"):
                continue
            content = str(message.get("content") or "")
            is_tool_result = (
                message.get("role") == "tool" or "<tool_response>" in content)
            if not is_tool_result:
                continue
            replacement: dict[str, Any] = {
                "role": message.get("role", "user"),
                "content": _collapse_tool_content(content),
                "_compacted": True,
            }
            if "tool_call_id" in message:
                replacement["tool_call_id"] = message["tool_call_id"]
            self._messages[index] = replacement

        if self.needs_compaction() and summarizer is not None and cutoff > 2:
            old = self._messages[1:cutoff]
            summary_text = summarizer(old)
            self._messages = [
                self._messages[0],
                {"role": "user",
                 "content": f"[Conversation summary — earlier turns compacted]\n{summary_text}",
                 "_compacted": True},
                *self._messages[cutoff:],
            ]

        return {"before": before, "after": self.total_tokens()}
