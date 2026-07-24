"""Atomic project-local persistence for implementation plans."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import threading

from nexcoder.agent.planning.models import ImplementationPlan

_SAFE_ID = re.compile(r"^plan_[A-Za-z0-9_-]{1,64}$")


class PlanStore:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()
        self.base = self.root / ".nexcoder" / "plans"
        self.base.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _directory(self, plan_id: str) -> Path:
        if not _SAFE_ID.match(plan_id):
            raise ValueError(f"Invalid plan id: {plan_id!r}")
        return self.base / plan_id

    @staticmethod
    def _atomic_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def save(self, plan: ImplementationPlan) -> None:
        with self._lock:
            directory = self._directory(plan.id)
            self._atomic_json(directory / "plan.json", plan.to_dict())
            if plan.revision:
                self._atomic_json(
                    directory / "revisions" / f"{plan.revision:04d}.json",
                    plan.to_dict())
            self._write_index()

    def load(self, plan_id: str) -> ImplementationPlan:
        path = self._directory(plan_id) / "plan.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FileNotFoundError(f"Plan not found: {plan_id}") from None
        if not isinstance(data, dict):
            raise ValueError(f"Corrupt plan: {plan_id}")
        return ImplementationPlan.from_dict(data)

    def list(self, *, conversation_id: str = "") -> list[ImplementationPlan]:
        plans: list[ImplementationPlan] = []
        with self._lock:
            for entry in self.base.iterdir():
                if not entry.is_dir() or not _SAFE_ID.match(entry.name):
                    continue
                try:
                    plan = self.load(entry.name)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if not conversation_id or plan.conversation_id == conversation_id:
                    plans.append(plan)
        return sorted(plans, key=lambda item: item.updated_at, reverse=True)

    def _write_index(self) -> None:
        summaries = [{
            "id": plan.id, "conversation_id": plan.conversation_id,
            "title": plan.title, "status": plan.status,
            "revision": plan.revision, "updated_at": plan.updated_at,
        } for plan in self.list()]
        self._atomic_json(self.base / "index.json", summaries)
