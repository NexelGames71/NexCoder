"""load_skill: read a SKILL.md body from the skills registry."""

from __future__ import annotations

from typing import Any

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.skills_registry import get_skill_body

MAX_BODY = 12000


def load_skill(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    skill_id = str(args.get("id") or "").strip()
    if skill_id and skill_id == getattr(ctx, "preloaded_skill", None):
        return {"success": True, "message": "Skill already loaded in context"}
    record = get_skill_body(skill_id, str(ctx.project_root)) if skill_id else None
    if record is None:
        return {"success": False, "error_code": "skill_not_found",
                "error": f"Unknown skill: {skill_id}"}
    return {"success": True, "skill": {**record, "body": (record.get("body") or "")[:MAX_BODY]},
            "message": "Skill loaded"}


def register_skill_tool(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="load_skill", description="Load a skill guide by id.",
        parameters={"type": "object", "properties": {"id": {"type": "string"}},
                    "required": ["id"]},
        handler=load_skill))
