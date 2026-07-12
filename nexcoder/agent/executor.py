"""Execute parsed agent tool calls and emit structured timeline records."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Optional

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.permission_policy import PermissionPolicy
from nexcoder.agent.tool_call_parser import ParsedToolCall
from nexcoder.agent.tool_guardrails import ToolGuardrailController
from nexcoder.agent.tool_registry import ToolRegistry


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        on_timeline: Callable[[dict[str, Any]], None] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        guardrails: ToolGuardrailController | None = None,
        permission_policy: PermissionPolicy | None = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> None:
        self.registry = registry
        self.on_timeline = on_timeline or (lambda _item: None)
        self.on_event = on_event or (lambda _event_type, _payload: None)
        self.guardrails = guardrails or ToolGuardrailController()
        self.permission_policy = permission_policy
        self.cancellation_token = cancellation_token
        self._counter = 0

    def execute(self, call: ParsedToolCall) -> tuple[dict[str, Any], str]:
        # Cooperative cancellation: bail before launching the tool so a
        # cancelled run stops at the next safe checkpoint instead of
        # grinding through the rest of the queue.
        if self.cancellation_token is not None:
            self.cancellation_token.raise_if_cancelled()

        self._counter += 1
        target = self.registry.target_for(call.tool, call.args)
        item = {
            "id": f"step_{self._counter:03d}",
            "type": "tool_call",
            "tool": call.tool,
            "label": self.registry.label_for(call.tool),
            "target": target,
            "status": "running",
            "started_at": utc_now(),
            "completed_at": None,
            "result_summary": None,
            "error": None,
        }

        if self.permission_policy is not None:
            permission = self.permission_policy.evaluate(call.tool, target)
            if not permission.allows_execution:
                item.update({
                    "status": "approval_required" if permission.action == "ask" else "blocked",
                    "completed_at": utc_now(),
                    "result_summary": permission.reason,
                    "error": permission.reason,
                    "permission": {
                        "name": permission.permission,
                        "action": permission.action,
                        "pattern": permission.pattern,
                    },
                })
                self.on_timeline(item)
                self.on_event(
                    "tool_approval_required" if permission.action == "ask" else "tool_blocked",
                    {"tool": call.tool, "args": call.args, "permission": item["permission"]},
                )
                result = {
                    "success": False,
                    "error_code": "approval_required" if permission.action == "ask" else "blocked",
                    "error": permission.reason,
                    "permission": item["permission"],
                }
                return item, json.dumps(
                    {"tool": call.tool, "args": call.args, "result": result},
                    ensure_ascii=False,
                )

        decision = self.guardrails.before_call(call.tool, call.args)
        if not decision.allows_execution:
            skipped = decision.code == "duplicate_tool_call"
            item.update({
                "status": "skipped" if skipped else "blocked",
                "completed_at": utc_now(),
                "result_summary": decision.message,
                "error": None if skipped else decision.message,
                "guardrail": {
                    "code": decision.code,
                    "count": decision.count,
                    "signature": decision.signature,
                },
            })
            self.on_timeline(item)
            self.on_event(
                "tool_skipped" if skipped else "tool_blocked",
                {"tool": call.tool, "args": call.args, "decision": item.get("guardrail")},
            )
            result = {
                "success": False,
                "error_code": decision.code,
                "error": decision.message,
                "guardrail": item.get("guardrail"),
            }
            return item, json.dumps({"tool": call.tool, "args": call.args, "result": result}, ensure_ascii=False)

        if decision.action == "warn":
            item["guardrail"] = {
                "code": decision.code,
                "message": decision.message,
                "count": decision.count,
                "signature": decision.signature,
            }
        self.on_timeline(item)
        self.on_event("tool_started", {"tool": call.tool, "args": call.args, "target": target})

        try:
            result = self.registry.execute(call.tool, call.args, cancellation_token=self.cancellation_token)
        except Exception as exc:
            result = {"success": False, "error_code": "tool_exception", "error": str(exc)}

        after_decision = self.guardrails.after_call(call.tool, call.args, result)
        if after_decision.action in {"warn", "block"}:
            result.setdefault("guardrail", {
                "code": after_decision.code,
                "message": after_decision.message,
                "count": after_decision.count,
                "signature": after_decision.signature,
            })
            if after_decision.action == "block" and result.get("success"):
                result = {
                    "success": False,
                    "error_code": after_decision.code,
                    "error": after_decision.message,
                    "guardrail": result.get("guardrail"),
                }

        item = {
            **item,
            "status": "completed" if result.get("success") else self._failure_status(result),
            "completed_at": utc_now(),
            "result_summary": self.registry.summarize_result(result),
            "error": None if result.get("success") else result.get("error", "Tool failed"),
        }
        if result.get("guardrail"):
            item["guardrail"] = result["guardrail"]
        self.on_timeline(item)
        self.on_event("tool_completed", {"tool": call.tool, "args": call.args, "result": result, "timeline_item": item})
        return item, json.dumps({"tool": call.tool, "args": call.args, "result": result}, ensure_ascii=False)

    def _failure_status(self, result: dict[str, Any]) -> str:
        if result.get("error_code") in {
            "blocked",
            "duplicate_tool_call",
            "same_tool_failure_block",
            "idempotent_no_progress_block",
        }:
            return "blocked"
        if result.get("error_code") == "agent_cancelled":
            return "cancelled"
        if result.get("error_code") == "approval_required":
            return "approval_required"
        return "failed"
