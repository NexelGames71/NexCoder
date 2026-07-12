"""Reusable guardrails for NexCoder tool loops.

Inspired by Hermes' tool-loop controller, but scoped to NexCoder's smaller
XML-tool runtime. The controller is side-effect free: callers decide whether a
decision becomes a timeline item, an observation, or a hard stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping


IDEMPOTENT_TOOLS = frozenset({
    "list_directory",
    "list_project_tree",
    "read_file",
    "search_grep",
    "search_code",
    "load_skill",
})

MUTATING_TOOLS = frozenset({
    "write_file",
    "run_command",
    "run_terminal_command",
    "run_tests",
})


@dataclass(frozen=True)
class ToolGuardrailConfig:
    repeated_exact_block_after: int = 1
    same_tool_failure_warn_after: int = 2
    same_tool_failure_block_after: int = 4
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 3
    idempotent_tools: frozenset[str] = field(default_factory=lambda: IDEMPOTENT_TOOLS)
    mutating_tools: frozenset[str] = field(default_factory=lambda: MUTATING_TOOLS)
    # Tools whose exact repeats are legitimate because the world changes
    # between calls (e.g. re-running tests after a fix). They skip the
    # repeated-exact-call block but keep failure tracking.
    exempt_repeat_tools: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolGuardrailDecision:
    action: str = "allow"  # allow | warn | block
    code: str = "allow"
    message: str = ""
    tool: str = ""
    count: int = 0
    signature: str = ""

    @property
    def allows_execution(self) -> bool:
        return self.action in {"allow", "warn"}


class ToolGuardrailController:
    """Track repeated tool calls and repeated failures within one agent run."""

    def __init__(self, config: ToolGuardrailConfig | None = None) -> None:
        self.config = config or ToolGuardrailConfig()
        self._seen_calls: dict[str, int] = {}
        self._failure_counts: dict[str, int] = {}
        self._same_tool_failures: dict[str, int] = {}
        self._idempotent_results: dict[str, tuple[str, int]] = {}

    def before_call(self, tool: str, args: Mapping[str, Any] | None) -> ToolGuardrailDecision:
        signature = tool_signature(tool, args or {})
        seen = self._seen_calls.get(signature, 0)
        if tool in self.config.exempt_repeat_tools:
            # Re-running a previously *successful* command is the legitimate
            # verify -> fix -> re-verify loop. Re-running one that already
            # failed, unchanged, is never productive.
            if self._failure_counts.get(signature, 0) > 0:
                return ToolGuardrailDecision(
                    action="block",
                    code="repeat_failed_command",
                    message=(
                        "This exact command already failed. Change the command "
                        "(fix quoting, paths, or arguments) instead of retrying it."),
                    tool=tool,
                    count=self._failure_counts[signature],
                    signature=signature,
                )
            self._seen_calls[signature] = seen + 1
            return ToolGuardrailDecision(tool=tool, count=seen + 1, signature=signature)
        if seen >= self.config.repeated_exact_block_after:
            return ToolGuardrailDecision(
                action="block",
                code="duplicate_tool_call",
                message=(
                    "This exact tool call was already executed. Use the previous "
                    "result, change the arguments, or explain the blocker."
                ),
                tool=tool,
                count=seen,
                signature=signature,
            )
        self._seen_calls[signature] = seen + 1
        return ToolGuardrailDecision(tool=tool, signature=signature)

    def after_call(
        self,
        tool: str,
        args: Mapping[str, Any] | None,
        result: Mapping[str, Any] | None,
    ) -> ToolGuardrailDecision:
        signature = tool_signature(tool, args or {})
        failed = not bool((result or {}).get("success"))

        if failed:
            exact_failures = self._failure_counts.get(signature, 0) + 1
            self._failure_counts[signature] = exact_failures
            same_tool_failures = self._same_tool_failures.get(tool, 0) + 1
            self._same_tool_failures[tool] = same_tool_failures

            if same_tool_failures >= self.config.same_tool_failure_block_after:
                return ToolGuardrailDecision(
                    action="block",
                    code="same_tool_failure_block",
                    message=(
                        f"{tool} failed {same_tool_failures} times. Stop retrying "
                        "the same failing path and choose a different strategy."
                    ),
                    tool=tool,
                    count=same_tool_failures,
                    signature=signature,
                )
            if same_tool_failures >= self.config.same_tool_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=(
                        f"{tool} has failed {same_tool_failures} times. Inspect "
                        "the latest error before retrying."
                    ),
                    tool=tool,
                    count=same_tool_failures,
                    signature=signature,
                )
            return ToolGuardrailDecision(tool=tool, count=exact_failures, signature=signature)

        self._failure_counts.pop(signature, None)
        self._same_tool_failures.pop(tool, None)

        if tool not in self.config.idempotent_tools or tool in self.config.mutating_tools:
            self._idempotent_results.pop(signature, None)
            return ToolGuardrailDecision(tool=tool, signature=signature)

        result_hash = _hash_json(result or {})
        previous = self._idempotent_results.get(signature)
        repeat_count = 1
        if previous and previous[0] == result_hash:
            repeat_count = previous[1] + 1
        self._idempotent_results[signature] = (result_hash, repeat_count)

        if repeat_count >= self.config.no_progress_block_after:
            return ToolGuardrailDecision(
                action="block",
                code="idempotent_no_progress_block",
                message=(
                    f"{tool} returned the same result {repeat_count} times. Use "
                    "the result already provided or call a different tool."
                ),
                tool=tool,
                count=repeat_count,
                signature=signature,
            )
        if repeat_count >= self.config.no_progress_warn_after:
            return ToolGuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=(
                    f"{tool} returned the same result {repeat_count} times. Avoid "
                    "looping on identical read-only calls."
                ),
                tool=tool,
                count=repeat_count,
                signature=signature,
            )
        return ToolGuardrailDecision(tool=tool, count=repeat_count, signature=signature)


def tool_signature(tool: str, args: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {"tool": tool, "args": args},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _hash_json(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
