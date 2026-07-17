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
        # Estimator calibration: the backend reports the real prompt
        # size after each call; the scale corrects chars/3 drift so the
        # meter and compaction track the actual tokenizer.
        self._scale = 1.0
        # Hysteresis: when compaction cannot get below the threshold,
        # don't thrash — wait until the total grows past this floor.
        self._compact_floor = 0.0

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
        raw = sum(message_tokens(message) for message in self._messages)
        return int(raw * self._scale)

    def calibrate(self, actual_prompt_tokens: int,
                  estimated_at_send: int) -> None:
        """Correct the estimator against the backend's reported usage.

        ``estimated_at_send`` is what ``total_tokens()`` returned for the
        payload that produced ``actual_prompt_tokens``. A 50% EMA keeps
        one odd report from whipsawing the scale.
        """
        if actual_prompt_tokens <= 0 or estimated_at_send <= 0:
            return
        raw_estimate = estimated_at_send / self._scale
        observed = actual_prompt_tokens / max(1.0, raw_estimate)
        blended = 0.5 * self._scale + 0.5 * observed
        self._scale = min(3.0, max(0.4, blended))

    def needs_compaction(self) -> bool:
        threshold = self.input_budget * self.compact_threshold
        return self.total_tokens() > max(threshold, self._compact_floor)

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

        after = self.total_tokens()
        threshold = self.input_budget * self.compact_threshold
        # If compaction cannot get below the threshold (protected window
        # + system prompt form the floor), don't re-run it every turn;
        # wait until the conversation grows meaningfully past this point.
        self._compact_floor = after * 1.08 if after > threshold else 0.0
        return {"before": before, "after": after}

    def force_fit(self) -> None:
        """Last-resort shrink: stub out the oldest non-protected messages
        until the estimated total fits the input budget. Used before send
        and after the backend rejects a request for exceeding the context
        window (the token estimator can undercount dense code)."""
        target = int(self.input_budget * 0.9)

        def stub_at(index: int) -> None:
            message = self._messages[index]
            replacement: dict[str, Any] = {
                "role": message.get("role", "user"),
                "content": "[dropped to fit context]",
                "_compacted": True,
            }
            if "tool_call_id" in message:
                replacement["tool_call_id"] = message["tool_call_id"]
            self._messages[index] = replacement

        # Pass 1: stub oldest non-protected messages.
        index = 1
        while self.total_tokens() > target:
            cutoff = max(1, len(self._messages) - self.PROTECTED_RECENT)
            if index >= cutoff:
                break
            stub_at(index)
            index += 1

        # Pass 2 (last resort): the protected window itself is too big for
        # this budget. Stub everything except system[0] and the final
        # message so the request can never exceed the context window.
        index = 1
        while self.total_tokens() > target and index < len(self._messages) - 1:
            if not self._messages[index].get("_compacted"):
                stub_at(index)
            index += 1
