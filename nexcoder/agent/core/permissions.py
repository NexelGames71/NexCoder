"""Permission gates: project allowlist persistence and full-auto policy."""

from __future__ import annotations

import json
from pathlib import Path
import re

from nexcoder.agent.core.tools.base import ALLOW, ALLOW_ALWAYS, DENY, PermissionGate

RISKY_PATTERNS = [
    r"git\s+push", r"git\s+reset\s+--hard", r"rm\s+-r", r"del\s+/s",
    r"rd\s+/s", r"npm\s+publish",
]


class AllowlistGate:
    """Wraps another gate with a persisted per-project command allowlist."""

    def __init__(self, inner: PermissionGate, project_root: str | Path) -> None:
        self.inner = inner
        self._path = Path(project_root) / ".nexcoder" / "permissions.json"

    def _load(self) -> list[str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [str(item) for item in data.get("allowed_commands", [])]
        except (OSError, json.JSONDecodeError, ValueError):
            return []

    def _save(self, commands: list[str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"allowed_commands": sorted(set(commands))}, indent=2),
            encoding="utf-8")

    def request(self, *, tool: str, detail: str) -> str:
        command = detail.strip()
        allowed = self._load()
        if command in allowed:
            return ALLOW
        decision = self.inner.request(tool=tool, detail=detail)
        if decision == ALLOW_ALWAYS:
            self._save(allowed + [command])
            return ALLOW
        return decision


class FullAutoGate:
    """YOLO mode: allow everything except risky commands (those get denied
    so the caller surfaces them; the hard blocklist lives in the tool)."""

    def request(self, *, tool: str, detail: str) -> str:
        lowered = detail.lower()
        for pattern in RISKY_PATTERNS:
            if re.search(pattern, lowered):
                return DENY
        return ALLOW
