"""todo_write: the agent's visible task list."""

from __future__ import annotations

from typing import Any

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec

VALID_STATUSES = {"pending", "in_progress", "completed"}


def todo_write(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    raw = args.get("todos")
    if not isinstance(raw, list) or not raw:
        return {"success": False, "error_code": "invalid_args",
                "error": "todos must be a non-empty array"}
    todos: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        content = str((item or {}).get("content") or "").strip()
        status = str((item or {}).get("status") or "pending")
        if not content or status not in VALID_STATUSES:
            return {"success": False, "error_code": "invalid_args",
                    "error": f"todos[{index}] needs content and status in "
                             f"{sorted(VALID_STATUSES)}"}
        todos.append({"id": index + 1, "content": content, "status": status})
    ctx.todos = todos
    ctx.emit(AgentEvent("todo_updated", {"todos": todos}))
    done = sum(1 for t in todos if t["status"] == "completed")
    return {"success": True, "message": f"Todo list updated ({done}/{len(todos)} done)"}


def register_todo_tool(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="todo_write",
        description=("Replace your task list. Call early on multi-step tasks and "
                     "keep statuses current as you work."),
        parameters={"type": "object", "properties": {
            "todos": {"type": "array", "items": {"type": "object", "properties": {
                "content": {"type": "string"},
                "status": {"type": "string",
                           "enum": ["pending", "in_progress", "completed"]}},
                "required": ["content", "status"]}}},
            "required": ["todos"]},
        handler=todo_write))
