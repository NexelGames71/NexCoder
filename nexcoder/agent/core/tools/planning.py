"""Structured tools used by the planning lifecycle."""

from __future__ import annotations

from typing import Any

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec


def _require_plan(ctx: ToolContext):
    if ctx.plan_manager is None or not ctx.plan_id:
        raise ValueError("No active implementation plan")
    return ctx.plan_manager


def request_plan_clarification(args: dict[str, Any],
                               ctx: ToolContext) -> dict[str, Any]:
    plan = _require_plan(ctx).set_questions(
        ctx.plan_id, list(args.get("questions") or []))
    ctx.plan_revision = plan.revision
    ctx.emit(AgentEvent("plan_questions", {"plan": plan.to_dict()}))
    return {"success": True, "message": "Clarification questions submitted",
            "plan": plan.to_dict(), "stop": True}


def submit_implementation_plan(args: dict[str, Any],
                               ctx: ToolContext) -> dict[str, Any]:
    plan = _require_plan(ctx).submit_draft(
        ctx.plan_id, dict(args.get("plan") or {}),
        str(args.get("revision_summary") or "Generated plan"))
    ctx.plan_revision = plan.revision
    ctx.emit(AgentEvent("plan_updated", {"plan": plan.to_dict()}))
    return {"success": True, "message": "Plan is ready for approval",
            "plan": plan.to_dict(), "stop": True}


def report_plan_deviation(args: dict[str, Any],
                          ctx: ToolContext) -> dict[str, Any]:
    plan = _require_plan(ctx).record_deviation(
        ctx.plan_id, str(args.get("classification") or "minor"),
        str(args.get("description") or ""),
        str(args.get("proposed_amendment") or ""))
    ctx.emit(AgentEvent("plan_deviation", {"plan": plan.to_dict()}))
    return {"success": True,
            "message": f"Recorded {args.get('classification')} deviation",
            "plan": plan.to_dict(), "stop": plan.status == "paused"}


QUESTION_SCHEMA = {
    "type": "object", "properties": {
        "questions": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "title": {"type": "string"},
            "kind": {"type": "string", "enum": [
                "single", "multiple", "boolean", "text", "number", "file", "confirm"]},
            "explanation": {"type": "string"}, "required": {"type": "boolean"},
            "options": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "label": {"type": "string"},
                "description": {"type": "string"}}, "required": ["id", "label"]}},
        }, "required": ["id", "title", "kind"]}},
    }, "required": ["questions"]}


PLAN_SCHEMA = {
    "type": "object", "properties": {
        "revision_summary": {"type": "string"},
        "plan": {"type": "object", "properties": {
            "title": {"type": "string"}, "objective": {"type": "string"},
            "current_state_findings": {"type": "array", "items": {"type": "string"}},
            "proposed_architecture": {"type": "array", "items": {"type": "string"}},
            "confirmed_requirements": {"type": "array", "items": {"type": "string"}},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "inspected_files": {"type": "array", "items": {"type": "string"}},
            "phases": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "title": {"type": "string"},
                "description": {"type": "string"},
                "tasks": {"type": "array", "items": {"type": "object", "properties": {
                    "id": {"type": "string"}, "title": {"type": "string"},
                    "description": {"type": "string"}}, "required": ["title"]}},
            }, "required": ["title", "tasks"]}},
            "files": {"type": "array", "items": {"type": "object", "properties": {
                "path": {"type": "string"}, "operation": {"type": "string"},
                "description": {"type": "string"}, "confirmed": {"type": "boolean"}},
                "required": ["path", "description"]}},
            "risks": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "mitigation": {"type": "string"},
                "severity": {"type": "string"}}, "required": ["title", "mitigation"]}},
            "validation_steps": {"type": "array", "items": {"type": "object", "properties": {
                "description": {"type": "string"}, "command": {"type": "string"}},
                "required": ["description"]}},
            "definition_of_done": {"type": "array", "items": {"type": "string"}},
        }, "required": ["title", "objective", "phases", "files", "validation_steps"]},
    }, "required": ["plan"]}


def register_planning_tools(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="request_plan_clarification",
        description=("Pause Plan Mode and present structured questions. Use only when "
                     "inspection cannot determine a material requirement. Include an "
                     "Other option when listed choices are not exhaustive."),
        parameters=QUESTION_SCHEMA, handler=request_plan_clarification))
    belt.register(ToolSpec(
        name="submit_implementation_plan",
        description=("Submit the complete repository-grounded implementation plan for "
                     "review. Never print the plan as loose prose."),
        parameters=PLAN_SCHEMA, handler=submit_implementation_plan))
    belt.register(ToolSpec(
        name="report_plan_deviation",
        description=("Record a minor execution deviation or pause for approval of a "
                     "material amendment."),
        parameters={"type": "object", "properties": {
            "classification": {"type": "string", "enum": ["minor", "material"]},
            "description": {"type": "string"},
            "proposed_amendment": {"type": "string"}},
            "required": ["classification", "description"]},
        handler=report_plan_deviation))
