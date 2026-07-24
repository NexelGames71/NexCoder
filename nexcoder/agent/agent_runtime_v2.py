"""Qt worker + UI permission gate for the v2 agentic engine."""

from __future__ import annotations

import json
from queue import Empty, SimpleQueue
import threading
from typing import Callable
import uuid

from PySide6.QtCore import QThread, Signal

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.core.backend_config import load_backend_config
from nexcoder.agent.core.command_policy import AUTONOMY_LEVELS, AutonomyGate
from nexcoder.agent.core.editor_context import (
    render_chat_history, render_editor_context,
)
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.permissions import AllowlistGate
from nexcoder.agent.core.profiles import (
    READ_TOOLS, V2Profile, build_belt_for, get_v2_profile,
)
from nexcoder.agent.core.project_commands import (
    detect_project_commands, render_project_commands,
)
from nexcoder.agent.core.rules import load_project_rules
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
                 skill_id: str = "", mode: str = "agent",
                 editor_context: dict | None = None,
                 history: list[dict] | None = None,
                 resume_messages: list[dict] | None = None,
                 attachments: list[dict] | None = None,
                 autonomy: str = "ask",
                 plan_context: dict | None = None) -> None:
        super().__init__()
        self._project_root = project_root
        self._prompt = prompt
        self._gate = gate
        self._skill_id = skill_id
        self._mode = mode if mode in ("agent", "plan", "ask", "edit",
                                      "debug", "review", "scan",
                                      "terminal") else "agent"
        self._editor_context = editor_context
        self._history = history
        self._resume_messages = resume_messages
        self._attachments = list(attachments or [])
        self._plan_context = dict(plan_context or {})
        # full_auto is the legacy flag; the autonomy level supersedes it.
        if full_auto and autonomy == "ask":
            autonomy = "full_auto"
        self._autonomy = autonomy if autonomy in AUTONOMY_LEVELS else "ask"
        self.cancel_token = CancellationToken()
        self._steering: SimpleQueue[dict] = SimpleQueue()
        self._connector: ModelConnector | None = None

    def cancel(self) -> None:
        """Cancel the loop and actively close any blocked model stream."""
        self.cancel_token.cancel()
        connector = self._connector
        if connector is not None:
            connector.cancel_current_request()

    def steer(self, prompt: str, attachments: list[dict] | None = None) -> None:
        """Queue a user follow-up for the next safe model turn boundary."""
        value = str(prompt or "").strip()
        images = list(attachments or [])
        if value or images:
            self._steering.put({"text": value, "attachments": images})

    def _drain_steering(self) -> list[dict]:
        updates: list[dict] = []
        while True:
            try:
                updates.append(self._steering.get_nowait())
            except Empty:
                return updates

    def run(self) -> None:
        try:
            config = load_backend_config()
            connector = ModelConnector()
            self._connector = connector
            # Allowlist first (exact matches skip everything), then the
            # autonomy level, then the UI prompt as the final arbiter.
            permission_gate = AllowlistGate(
                AutonomyGate(self._gate, self._autonomy),
                self._project_root)
            repo_map = build_repo_map(self._project_root)
            save_repo_map(self._project_root, repo_map)
            profile = get_v2_profile(self._mode)
            # Read-only autonomy strips mutating tools no matter the mode
            # — safety is structural, not prompt-hoped.
            if self._autonomy == "read_only" and profile.tools is None:
                profile = V2Profile(name=profile.name,
                                    system_prompt=profile.system_prompt,
                                    tools=READ_TOOLS,
                                    max_turns=profile.max_turns)
            extra_sections = [render_repo_map(repo_map),
                              render_skills_catalog(self._project_root)]
            rules = load_project_rules(self._project_root)
            if rules:
                extra_sections.append(rules)
            commands = render_project_commands(
                detect_project_commands(self._project_root))
            if commands:
                extra_sections.append(commands)
            plan_id = str(self._plan_context.get("plan_id") or "")
            plan_revision = int(self._plan_context.get("revision") or 0)
            plan_manager = None
            if plan_id:
                from nexcoder.agent.planning.manager import PlanManager
                plan_manager = PlanManager(self._project_root)
            loop = AgentLoop(
                project_root=self._project_root,
                model=AgentModelClient(connector),
                adapter=get_adapter(config.adapter),
                belt=build_belt_for(profile, include_planning=bool(plan_id)),
                system_prompt=profile.system_prompt,
                trajectory_mode=profile.name,
                emit=lambda event: self.event_json.emit(json.dumps(
                    event.to_dict(), ensure_ascii=False, default=str)),
                permission_gate=permission_gate,
                max_turns=(config.max_turns_override or profile.max_turns),
                context_window=config.context_window,
                reserve_output=config.reserve_output,
                extra_system="\n\n".join(extra_sections),
                session_store=SessionStore(self._project_root),
                cancel_token=self.cancel_token,
                steering_source=self._drain_steering,
                plan_manager=plan_manager,
                plan_id=plan_id,
                plan_revision=plan_revision,
            )
            task = (("" if self._resume_messages else
                     render_chat_history(self._history))
                    + self._prompt
                    + render_editor_context(self._editor_context,
                                            self._project_root))
            result = loop.run(
                task,
                preload_skill=self._skill_id or None,
                resume_messages=self._resume_messages,
                input_attachments=self._attachments,
            )
        except Exception as exc:  # worker must never crash the app
            result = {"success": False, "status": "error", "final_text": str(exc),
                      "run_id": "", "checkpoint_id": None, "mutated_files": [],
                      "todos": [], "turns": 0}
        finally:
            self._connector = None
        self.finished_json.emit(json.dumps(result, ensure_ascii=False, default=str))
