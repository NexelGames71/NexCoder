"""Qt worker + UI permission gate for the v2 agentic engine."""

from __future__ import annotations

import json
import threading
from typing import Callable
import uuid

from PySide6.QtCore import QThread, Signal

from nexcoder.agent.core.backend_config import load_backend_config
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.loop import AGENT_SYSTEM_PROMPT, AgentLoop
from nexcoder.agent.core.permissions import AllowlistGate, FullAutoGate
from nexcoder.agent.core.repo_map import build_repo_map, render_repo_map, save_repo_map
from nexcoder.agent.core.session_store import SessionStore
from nexcoder.agent.core.skills_catalog import render_skills_catalog
from nexcoder.agent.core.tools.base import DENY
from nexcoder.agent.core.transport import get_adapter
from nexcoder.agent.model_connector import AgentModelClient, ModelConnector

PERMISSION_TIMEOUT = 300.0


class UiPermissionGate:
    """Blocks the agent worker thread until the UI answers (or timeout)."""

    def __init__(self, on_request: Callable[[str, str, str], None],
                 timeout: float = PERMISSION_TIMEOUT) -> None:
        self._on_request = on_request
        self._timeout = timeout
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    def request(self, *, tool: str, detail: str) -> str:
        request_id = f"perm_{uuid.uuid4().hex[:8]}"
        entry = {"event": threading.Event(), "decision": DENY}
        with self._lock:
            self._pending[request_id] = entry
        self._on_request(request_id, tool, detail)
        entry["event"].wait(self._timeout)
        with self._lock:
            self._pending.pop(request_id, None)
        return entry["decision"]

    def resolve(self, request_id: str, decision: str) -> None:
        with self._lock:
            entry = self._pending.get(request_id)
        if entry is None:
            return
        entry["decision"] = decision
        entry["event"].set()


class AgentV2Worker(QThread):
    event_json = Signal(str)
    finished_json = Signal(str)

    def __init__(self, project_root: str, prompt: str,
                 gate: UiPermissionGate, full_auto: bool = False,
                 skill_id: str = "") -> None:
        super().__init__()
        self._project_root = project_root
        self._prompt = prompt
        self._gate = gate
        self._full_auto = full_auto
        self._skill_id = skill_id

    def run(self) -> None:
        try:
            config = load_backend_config()
            permission_gate = (FullAutoGate() if self._full_auto
                               else AllowlistGate(self._gate, self._project_root))
            repo_map = build_repo_map(self._project_root)
            save_repo_map(self._project_root, repo_map)
            loop = AgentLoop(
                project_root=self._project_root,
                model=AgentModelClient(ModelConnector()),
                adapter=get_adapter(config.adapter),
                belt=build_default_belt(),
                system_prompt=AGENT_SYSTEM_PROMPT,
                emit=lambda event: self.event_json.emit(json.dumps(
                    event.to_dict(), ensure_ascii=False, default=str)),
                permission_gate=permission_gate,
                max_turns=50,
                context_window=config.context_window,
                extra_system=(render_repo_map(repo_map) + "\n\n"
                              + render_skills_catalog(self._project_root)),
                session_store=SessionStore(self._project_root),
            )
            result = loop.run(self._prompt, preload_skill=self._skill_id or None)
        except Exception as exc:  # worker must never crash the app
            result = {"success": False, "status": "error", "final_text": str(exc),
                      "run_id": "", "checkpoint_id": None, "mutated_files": [],
                      "todos": [], "turns": 0}
        self.finished_json.emit(json.dumps(result, ensure_ascii=False, default=str))
