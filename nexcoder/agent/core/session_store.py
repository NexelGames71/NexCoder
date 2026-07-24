"""Persist agent run transcripts so crashed runs can be inspected/resumed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, project_root: str | Path) -> None:
        self._folder = Path(project_root) / ".nexcoder" / "sessions"

    def save(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._folder.mkdir(parents=True, exist_ok=True)
        path = self._folder / f"{run_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                   default=str), encoding="utf-8")
        return path

    def load(self, run_id: str) -> dict[str, Any] | None:
        path = self._folder / f"{run_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list_runs(self) -> list[str]:
        if not self._folder.is_dir():
            return []
        entries = sorted(self._folder.glob("run_*.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        return [entry.stem for entry in entries]
