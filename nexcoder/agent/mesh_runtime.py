"""Qt worker for Agent Mesh runs (mirrors agent_runtime_v2.py)."""

from __future__ import annotations

import json

from PySide6.QtCore import QThread, Signal

from nexcoder.agent.agent_runtime_v2 import UiPermissionGate
from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.core.backend_config import load_backend_config
from nexcoder.agent.core.command_policy import AUTONOMY_LEVELS, AutonomyGate
from nexcoder.agent.core.permissions import AllowlistGate
from nexcoder.agent.core.project_commands import (
    detect_project_commands, render_project_commands,
)
from nexcoder.agent.core.repo_map import (
    build_repo_map, render_repo_map, save_repo_map,
)
from nexcoder.agent.core.rules import load_project_rules
from nexcoder.agent.core.transport import get_adapter
from nexcoder.agent.mesh.orchestrator import MeshOrchestrator
from nexcoder.agent.model_connector import AgentModelClient, ModelConnector


class MeshWorker(QThread):
    event_json = Signal(str)
    finished_json = Signal(str)

    def __init__(self, project_root: str, goal: str,
                 gate: UiPermissionGate, autonomy: str = "ask") -> None:
        super().__init__()
        self._project_root = project_root
        self._goal = goal
        self._gate = gate
        self._autonomy = autonomy if autonomy in AUTONOMY_LEVELS else "ask"
        self.cancel_token = CancellationToken()

    def cancel(self) -> None:
        self.cancel_token.cancel()

    def run(self) -> None:
        try:
            config = load_backend_config()
            permission_gate = AllowlistGate(
                AutonomyGate(self._gate, self._autonomy),
                self._project_root)
            repo_map = build_repo_map(self._project_root)
            save_repo_map(self._project_root, repo_map)
            extra_sections = [render_repo_map(repo_map)]
            rules = load_project_rules(self._project_root)
            if rules:
                extra_sections.append(rules)
            commands = render_project_commands(
                detect_project_commands(self._project_root))
            if commands:
                extra_sections.append(commands)

            orchestrator = MeshOrchestrator(
                project_root=self._project_root,
                model=AgentModelClient(ModelConnector()),
                adapter=get_adapter(config.adapter),
                permission_gate=permission_gate,
                emit=lambda event_type, payload: self.event_json.emit(
                    json.dumps({"type": event_type, "payload": payload},
                               ensure_ascii=False, default=str)),
                cancel_token=self.cancel_token,
                context_window=config.context_window,
                extra_system="\n\n".join(extra_sections),
            )
            summary = orchestrator.run(self._goal)
        except Exception as exc:  # worker must never crash the app
            summary = {"mesh_id": "", "status": "error",
                       "goal": self._goal, "report": str(exc),
                       "units": [], "agents": [], "conflicts": [],
                       "mutated_files": []}
            self.event_json.emit(json.dumps(
                {"type": "mesh_error", "payload": {"error": str(exc)}},
                ensure_ascii=False, default=str))
        self.finished_json.emit(json.dumps(summary, ensure_ascii=False,
                                           default=str))
