"""Qt worker + UI permission gate for the v2 agentic engine."""

from __future__ import annotations

import json
import threading
from typing import Callable
import uuid

from PySide6.QtCore import QThread, Signal

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.core.backend_config import load_backend_config
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.permissions import AllowlistGate, FullAutoGate
from nexcoder.agent.core.profiles import build_belt_for, get_v2_profile
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
            # The UI answers with the id from the loop's permission_request
            # event, which differs from this gate's internal id. The loop is
            # single-threaded, so with exactly one pending request the answer
            # unambiguously belongs to it.
            if entry is None and len(self._pending) == 1:
                entry = next(iter(self._pending.values()))
        if entry is None:
            return
        entry["decision"] = decision
        entry["event"].set()


class AgentV2Worker(QThread):
    event_json = Signal(str)
    finished_json = Signal(str)

    def __init__(self, project_root: str, prompt: str,
                 gate: UiPermissionGate, full_auto: bool = False,
                 skill_id: str = "", mode: str = "agent") -> None:
        super().__init__()
        self._project_root = project_root
        self._prompt = prompt
        self._gate = gate
        self._full_auto = full_auto
        self._skill_id = skill_id
        self._mode = mode if mode in ("agent", "ask", "edit", "debug",
                                      "review", "scan") else "agent"
        self.cancel_token = CancellationToken()

    def cancel(self) -> None:
        """Request cooperative cancellation of the running loop."""
        self.cancel_token.cancel()

    def run(self) -> None:
        try:
            config = load_backend_config()
            permission_gate = (FullAutoGate() if self._full_auto
                               else AllowlistGate(self._gate, self._project_root))
            repo_map = build_repo_map(self._project_root)
            save_repo_map(self._project_root, repo_map)
            profile = get_v2_profile(self._mode)
            loop = AgentLoop(
                project_root=self._project_root,
                model=AgentModelClient(ModelConnector()),
                adapter=get_adapter(config.adapter),
                belt=build_belt_for(profile),
                system_prompt=profile.system_prompt,
                trajectory_mode=profile.name,
                emit=lambda event: self.event_json.emit(json.dumps(
                    event.to_dict(), ensure_ascii=False, default=str)),
                permission_gate=permission_gate,
                max_turns=profile.max_turns,
                context_window=config.context_window,
                extra_system=(render_repo_map(repo_map) + "\n\n"
                              + render_skills_catalog(self._project_root)),
                session_store=SessionStore(self._project_root),
                cancel_token=self.cancel_token,
            )
            result = loop.run(self._prompt, preload_skill=self._skill_id or None)
        except Exception as exc:  # worker must never crash the app
            result = {"success": False, "status": "error", "final_text": str(exc),
                      "run_id": "", "checkpoint_id": None, "mutated_files": [],
                      "todos": [], "turns": 0}
        self.finished_json.emit(json.dumps(result, ensure_ascii=False, default=str))
