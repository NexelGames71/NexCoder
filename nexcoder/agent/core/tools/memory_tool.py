"""remember: persist a durable project fact for future runs."""

from __future__ import annotations

from typing import Any

from nexcoder.agent.core.memory import remember_note
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec


def remember(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    note = str(args.get("note") or "").strip()
    if not note:
        return {"success": False, "error_code": "invalid_args",
                "error": "note must be a non-empty string"}
    if len(note) > 500:
        return {"success": False, "error_code": "invalid_args",
                "error": "Keep notes under 500 characters — one durable fact."}
    remember_note(ctx.project_root, note)
    return {"success": True, "message": "Noted for future runs"}


def register_memory_tool(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="remember",
        description=("Save one durable project fact for future sessions "
                     "(build/test commands, conventions, gotchas). Use "
                     "sparingly; not a scratchpad."),
        parameters={"type": "object", "properties": {
            "note": {"type": "string"}}, "required": ["note"]},
        handler=remember))
