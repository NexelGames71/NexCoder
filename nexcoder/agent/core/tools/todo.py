"""todo_write: the agent's visible task list."""

from __future__ import annotations

from typing import Any

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec

VALID_STATUSES = {"pending", "in_progress", "completed"}
# Models improvise vocabulary; coerce instead of failing the whole plan.
STATUS_ALIASES = {
    "done": "completed", "complete": "completed", "finished": "completed",
    "doing": "in_progress", "active": "in_progress", "started": "in_progress",
    "wip": "in_progress", "todo": "pending", "open": "pending", "new": "pending",
}
CONTENT_KEYS = ("content", "task", "title", "description", "text")


def todo_write(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    raw = args.get("todos")
    if not isinstance(raw, list) or not raw:
        return {"success": False, "error_code": "invalid_args",
                "error": "todos must be a non-empty array"}
    todos: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, str):  # small models often send bare strings
            item = {"content": item, "status": "pending"}
        item = item or {}
        content = ""
        for key in CONTENT_KEYS:
            if str(item.get(key) or "").strip():
                content = str(item[key]).strip()
                break
        status = str(item.get("status") or "pending").strip().lower()
        status = STATUS_ALIASES.get(status, status)
        if status not in VALID_STATUSES:
            status = "pending"
        if not content:
            return {"success": False, "error_code": "invalid_args",
                    "error": f"todos[{index}] needs a non-empty content field"}
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
