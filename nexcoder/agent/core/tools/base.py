"""ToolSpec / ToolBelt / ToolContext — the contract every core tool follows."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable, Protocol

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.core.events import AgentEvent, EventCallback
from nexcoder.agent.safety import SafetyChecker
from nexcoder.services.checkpoint import CheckpointManager

ALLOW = "allow"
ALLOW_ALWAYS = "allow_always"
DENY = "deny"


class PermissionGate(Protocol):
    def request(self, *, tool: str, detail: str) -> str: ...


class AllowAllGate:
    def request(self, *, tool: str, detail: str) -> str:
        return ALLOW


class ToolContext:
    """Everything a tool handler needs beyond its own args."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        emit: EventCallback,
        checkpoints: CheckpointManager | None = None,
        safety: SafetyChecker | None = None,
        permission_gate: PermissionGate | None = None,
        run_id: str = "",
        cancel_token: CancellationToken | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.emit = emit
        self.checkpoints = checkpoints or CheckpointManager(str(self.project_root))
        self.safety = safety or SafetyChecker()
        self.permission_gate = permission_gate or AllowAllGate()
        self.run_id = run_id
        self.cancel_token = cancel_token
        self.checkpoint_id: str | None = None
        self.mutated_files: set[str] = set()
        self.todos: list[dict[str, Any]] = []
        self.preloaded_skill: str | None = None

    def resolve(self, target: str) -> Path | None:
        """Resolve a project-relative path; None when it escapes the root."""
        try:
            path = (self.project_root / (target or ".")).resolve()
            common = os.path.commonpath([str(self.project_root), str(path)])
        except (OSError, ValueError):
            return None
        return path if common == str(self.project_root) else None

    def snapshot_before_mutation(self, relative_path: str) -> None:
        """Capture the pre-edit state of a file into the run checkpoint."""
        if relative_path in self.mutated_files:
            return
        absolute = str(self.project_root / relative_path)
        if self.checkpoint_id is None:
            self.checkpoint_id = self.checkpoints.create(
                [absolute], label=f"agent-run {self.run_id}")
            self.emit(AgentEvent("checkpoint_created", {
                "checkpoint_id": self.checkpoint_id, "run_id": self.run_id}))
        else:
            self.checkpoints.add_file(self.checkpoint_id, absolute)
        self.mutated_files.add(relative_path)


ToolHandler = Callable[[dict[str, Any], ToolContext], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    handler: ToolHandler
    mutating: bool = False

    def openai_schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters}}


class ToolBelt:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Duplicate tool: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def schemas(self) -> list[dict[str, Any]]:
        return [spec.openai_schema() for spec in self._specs.values()]

    def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        spec = self._specs.get(name)
        if spec is None:
            return {"success": False, "error_code": "unknown_tool",
                    "error": f"Unknown tool: {name}"}
        try:
            return spec.handler(args, ctx)
        except Exception as exc:  # tool bugs become observations, never crashes
            return {"success": False, "error_code": "tool_exception",
                    "error": f"{type(exc).__name__}: {exc}"}
