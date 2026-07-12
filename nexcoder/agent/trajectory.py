"""Project-local trajectory recording for agent runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


MAX_TEXT = 4000


class AgentTrajectoryRecorder:
    """Collect compact run events and append them to `.nexcoder/trajectories`.

    The recorder intentionally stores structured metadata, not raw UI markdown.
    Large fields are truncated so local traces remain useful without becoming
    unbounded copies of every file the agent reads.
    """

    def __init__(self, project_root: str | Path, *, task: str, mode: str) -> None:
        self.project_root = Path(project_root)
        self.run_id = f"traj_{uuid.uuid4().hex[:12]}"
        self.task = _truncate(task)
        self.mode = mode
        self.started_at = _utc_now()
        self.events: list[dict[str, Any]] = []

    def record(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.events.append({
            "ts": _utc_now(),
            "type": event_type,
            "payload": _sanitize(payload or {}),
        })

    def finish(self, *, status: str, result: dict[str, Any] | None = None) -> Path | None:
        entry = {
            "run_id": self.run_id,
            "mode": self.mode,
            "task": self.task,
            "status": status,
            "started_at": self.started_at,
            "completed_at": _utc_now(),
            "result": _sanitize(result or {}),
            "events": self.events,
        }
        try:
            folder = self.project_root / ".nexcoder" / "trajectories"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return path
        except Exception:
            return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate(value)
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:100]]
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in {"content", "stdout", "stderr", "diff", "diff_display"}:
                clean[key_text] = _truncate(str(item))
            else:
                clean[key_text] = _sanitize(item)
        return clean
    return value


def _truncate(text: str) -> str:
    if len(text) <= MAX_TEXT:
        return text
    return text[:MAX_TEXT] + "\n...[truncated]"
