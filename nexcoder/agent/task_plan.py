"""Persistent structured plans driven by real agent execution events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable
import uuid


INSPECTION_TOOLS = {"list_directory", "read_file", "search_grep", "load_skill"}
CHANGE_TOOLS = {"write_file", "create_directory", "move_path"}
VERIFY_TOOLS = {"run_command"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskPlanItem:
    id: str
    title: str
    phase: str
    status: str = "pending"
    detail: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskPlanTracker:
    """Maintain and persist an ordered plan for one agent task."""

    def __init__(
        self,
        project_root: str | Path,
        *,
        prompt: str,
        task_type: str,
        session_id: str | None = None,
        on_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        self.prompt = prompt.strip()
        self.task_type = task_type
        self.session_id = _safe_id(session_id) if session_id else None
        self.on_update = on_update or (lambda _plan: None)
        self.created_at = _now()
        self.updated_at = self.created_at
        self.items = self._initial_items(task_type)
        self._emit()

    @staticmethod
    def _initial_items(task_type: str) -> list[TaskPlanItem]:
        if task_type in {"question", "review"}:
            return [
                TaskPlanItem("inspect", "Inspect relevant project context", "inspect", "in_progress", started_at=_now()),
                TaskPlanItem("respond", "Prepare a grounded answer", "respond"),
            ]
        return [
            TaskPlanItem("inspect", "Inspect relevant files and project state", "inspect", "in_progress", started_at=_now()),
            TaskPlanItem("change", "Implement the requested changes", "change"),
            TaskPlanItem("verify", "Run available validation", "verify"),
            TaskPlanItem("review", "Prepare the change set for review", "review"),
        ]

    def tool_event(self, event_type: str, payload: dict[str, Any]) -> None:
        tool = str(payload.get("tool") or "")
        phase = (
            "inspect" if tool in INSPECTION_TOOLS
            else "change" if tool in CHANGE_TOOLS
            else "verify" if tool in VERIFY_TOOLS
            else None
        )
        if not phase:
            return
        if event_type == "tool_started":
            self._activate(phase)
            return
        if event_type != "tool_completed":
            return
        item = self._item(phase)
        if not item:
            return
        result = dict(payload.get("result") or {})
        if result.get("success"):
            item.detail = str(result.get("message") or "Completed successfully")
            item.error = None
        else:
            item.detail = "A tool failed; the agent may retry or choose another approach"
            item.error = str(result.get("error") or "Tool failed")
        self._emit()

    def finish(self, result: dict[str, Any]) -> dict[str, Any]:
        success = bool(result.get("success", True))
        has_patches = bool(result.get("patches"))
        for item in self.items:
            if item.phase == "inspect" and item.status == "in_progress" and success:
                self._complete(item)
            if item.phase == "change" and has_patches and success:
                self._complete(item)
            if item.phase == "verify" and item.status == "in_progress" and success:
                self._complete(item)
            if item.phase == "verify" and item.status == "pending" and has_patches:
                item.status = "skipped"
                item.detail = "Validation runs after reviewed changes are applied"
                item.completed_at = _now()
            if item.phase == "review" and has_patches:
                item.status = "approval_required"
                item.detail = "Review and approve the prepared change set"
                item.started_at = item.started_at or _now()
            if item.phase == "respond" and success:
                self._complete(item)
        if not success:
            active = next((item for item in self.items if item.status == "in_progress"), None)
            if active:
                active.status = "failed"
                active.error = str(result.get("error") or result.get("response") or "Task did not complete")[:500]
                active.completed_at = _now()
        elif not has_patches:
            for item in self.items:
                if item.status == "pending":
                    item.status = "skipped"
                    item.completed_at = _now()
        self._emit()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.plan_id,
            "session_id": self.session_id,
            "task_type": self.task_type,
            "title": _title(self.prompt),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "items": [item.to_dict() for item in self.items],
        }

    def _activate(self, phase: str) -> None:
        target = self._item(phase)
        if not target or target.status in {"completed", "skipped"}:
            return
        target_index = self.items.index(target)
        if any(
            index > target_index and item.status != "pending"
            for index, item in enumerate(self.items)
        ):
            return
        for item in self.items:
            if item is not target and item.status == "in_progress":
                self._complete(item)
        target.status = "in_progress"
        target.started_at = target.started_at or _now()
        target.error = None
        self._emit()

    def _item(self, phase: str) -> TaskPlanItem | None:
        return next((item for item in self.items if item.phase == phase), None)

    @staticmethod
    def _complete(item: TaskPlanItem) -> None:
        item.status = "completed"
        item.started_at = item.started_at or _now()
        item.completed_at = _now()
        item.error = None

    def _emit(self) -> None:
        self.updated_at = _now()
        snapshot = self.snapshot()
        self._persist(snapshot)
        self.on_update(snapshot)

    def _persist(self, snapshot: dict[str, Any]) -> None:
        if not self.session_id:
            return
        folder = self.project_root / ".nexcoder" / "sessions" / self.session_id
        try:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / "plan.json"
            fd, temp_path = tempfile.mkstemp(prefix="plan-", suffix=".json", dir=folder)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(snapshot, handle, indent=2, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, target)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        except OSError:
            return


def _safe_id(value: str) -> str | None:
    return value if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value or "") else None


def _title(prompt: str) -> str:
    text = re.sub(r"\s+", " ", prompt).strip()
    return text[:117] + "..." if len(text) > 120 else text
