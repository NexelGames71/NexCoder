"""MeshOrchestrator — plans, delegates, supervises, and synthesizes.

One goal in, one verified report out. Work units execute sequentially
in dependency order (the local model server is single-slot, so
inference is serialized by design); each unit runs as a bounded
AgentLoop with a role profile and receives structured handoffs from
the units before it. Safety stays centralized: every unit shares the
same permission gate and cancellation token.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.tools.base import ToolBelt
from nexcoder.agent.errors import AgentCancelledError
from nexcoder.agent.mesh.roles import get_role
from nexcoder.agent.mesh.types import (
    MeshAgentResult, WorkUnit, detect_conflicts, new_mesh_id, parse_plan,
)

logger = logging.getLogger(__name__)

MESH_TOTAL_TURN_BUDGET = 70
HANDOFF_CHAR_CAP = 900

PLAN_PROMPT = """You are the orchestrator of a small engineering team.
Decompose the user's goal into AT MOST 4 bounded work units for these
specialist roles: explorer (read-only scouting), implementation (writes
code), test (writes and runs tests), review (read-only final review).

Rules:
- Only include units that genuinely help THIS goal. Small goals need
  fewer units. Always include exactly one review unit last.
- Reply with ONLY a JSON array, no prose, in this exact shape:
[{"id": "work_1", "title": "...", "role": "explorer",
  "description": "...", "dependencies": [],
  "completion_criteria": ["..."]}]
"""


def _belt_for_role(role_tools: tuple[str, ...] | None) -> ToolBelt:
    full = build_default_belt()
    if role_tools is None:
        return full
    belt = ToolBelt()
    for name in role_tools:
        spec = full.get(name)
        if spec is not None:
            belt.register(spec)
    return belt


class MeshOrchestrator:
    def __init__(
        self,
        *,
        project_root: str | Path,
        model: Any,
        adapter: Any,
        permission_gate: Any,
        emit: Callable[[str, dict[str, Any]], None],
        cancel_token: CancellationToken | None = None,
        context_window: int = 32768,
        extra_system: str = "",
        total_turn_budget: int = MESH_TOTAL_TURN_BUDGET,
    ) -> None:
        self.project_root = Path(project_root)
        self.model = model
        self.adapter = adapter
        self.permission_gate = permission_gate
        self._emit = emit
        self.cancel_token = cancel_token or CancellationToken()
        self.context_window = context_window
        self.extra_system = extra_system
        self.total_turn_budget = total_turn_budget

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._emit(event_type, payload)
        except Exception:
            logger.debug("Mesh emit failed", exc_info=True)

    # ── Planning ─────────────────────────────────────────────────────

    def plan(self, goal: str) -> tuple[list[WorkUnit], bool]:
        try:
            message = self.model.complete(
                [{"role": "system", "content": PLAN_PROMPT},
                 {"role": "user", "content": goal}],
                extras={"max_tokens": 900, "temperature": 0.1},
                on_delta=None)
            text = str(message.get("content") or "")
        except Exception:
            logger.warning("Mesh plan call failed; using default plan",
                           exc_info=True)
            text = ""
        return parse_plan(text, goal)

    # ── Execution ────────────────────────────────────────────────────

    def run(self, goal: str) -> dict[str, Any]:
        mesh_id = new_mesh_id()
        started = time.time()
        self.emit("mesh_started", {"mesh_id": mesh_id, "goal": goal})

        units, used_fallback = self.plan(goal)
        self.emit("mesh_plan", {
            "mesh_id": mesh_id,
            "units": [u.to_dict() for u in units],
            "fallback_plan": used_fallback,
        })

        results: list[MeshAgentResult] = []
        by_id: dict[str, WorkUnit] = {u.id: u for u in units}
        handoffs: list[str] = []
        turns_used = 0
        mesh_status = "completed"

        try:
            for unit in units:
                self.cancel_token.raise_if_cancelled()

                unavailable_deps = [d for d in unit.dependencies
                                    if by_id[d].status != "completed"]
                remaining_turns = self.total_turn_budget - turns_used
                if remaining_turns <= 0:
                    unit.status = "blocked"
                    self.emit("agent_completed", {
                        "mesh_id": mesh_id, "agent_id": unit.id,
                        "status": "blocked",
                        "summary": "Blocked: mesh turn budget exhausted."})
                    continue

                # A failed scout or test is a degraded handoff, not a reason
                # to abandon the entire goal. Every specialist can inspect the
                # current project state and make independent progress. Only a
                # cancellation or the global resource budget is a hard stop.
                if unavailable_deps:
                    dependency_details = ", ".join(
                        f"{dep} ({by_id[dep].status})"
                        for dep in unavailable_deps)
                    degraded = (
                        "Dependency handoff unavailable: " + dependency_details
                        + ". Inspect the current project state yourself and "
                          "continue with the work that is still possible.")
                    handoffs.append(f"[Orchestrator] {degraded}")
                    self.emit("agent_degraded", {
                        "mesh_id": mesh_id, "agent_id": unit.id,
                        "dependencies": unavailable_deps,
                        "summary": degraded})

                unit.status = "running"
                role = get_role(unit.role)
                self.emit("agent_started", {
                    "mesh_id": mesh_id, "agent_id": unit.id,
                    "role": unit.role, "display_name": role.display_name,
                    "title": unit.title})

                result = self._run_unit(
                    mesh_id, unit, goal, handoffs, remaining_turns)
                results.append(result)
                turns_used += result.turns
                unit.status = result.status if result.status in (
                    "completed", "failed", "cancelled") else "failed"

                if result.summary:
                    handoffs.append(
                        f"[{role.display_name} / {unit.id}] "
                        + result.summary[:HANDOFF_CHAR_CAP])
                self.emit("agent_completed", {
                    "mesh_id": mesh_id, "agent_id": unit.id,
                    "status": unit.status, "turns": result.turns,
                    "files": result.mutated_files,
                    "checkpoint_id": result.checkpoint_id,
                    "summary": result.summary[:1200]})
                if unit.status == "cancelled":
                    raise AgentCancelledError()
        except AgentCancelledError:
            mesh_status = "cancelled"
            for unit in units:
                if unit.status in ("queued", "running"):
                    unit.status = "cancelled"

        conflicts = detect_conflicts(results)
        for conflict in conflicts:
            self.emit("mesh_conflict", {"mesh_id": mesh_id, **conflict})

        if mesh_status != "cancelled" and any(
                u.status in ("failed", "blocked") for u in units):
            mesh_status = "completed_with_issues"

        report = self._synthesize(goal, units, results, conflicts,
                                  mesh_status)
        all_files = sorted({f for r in results for f in r.mutated_files})
        summary = {
            "mesh_id": mesh_id,
            "goal": goal,
            "status": mesh_status,
            "elapsed_seconds": round(time.time() - started, 1),
            "turns_used": turns_used,
            "units": [u.to_dict() for u in units],
            "agents": [{
                "unit_id": r.unit_id, "role": r.role, "status": r.status,
                "turns": r.turns, "files": r.mutated_files,
                "checkpoint_id": r.checkpoint_id,
                "summary": r.summary[:1200],
            } for r in results],
            "conflicts": conflicts,
            "mutated_files": all_files,
            "report": report,
        }
        self._persist(summary)
        self.emit("mesh_completed", summary)
        return summary

    def _run_unit(self, mesh_id: str, unit: WorkUnit, goal: str,
                  handoffs: list[str], remaining_turns: int) -> MeshAgentResult:
        role = get_role(unit.role)

        def forward(event: Any) -> None:
            # Summarized operational visibility only (roadmap §3.4):
            # tool activity, edits, and permission flow — not raw prose.
            if event.type in ("tool_started", "tool_result", "edit_applied",
                              "permission_request", "permission_resolved",
                              "tool_streaming"):
                self.emit("agent_activity", {
                    "mesh_id": mesh_id, "agent_id": unit.id,
                    "inner": {"type": event.type, "payload": event.payload}})

        criteria = "".join(f"\n- {c}" for c in unit.completion_criteria)
        handoff_text = ("\n\n# Handoffs from teammates\n"
                        + "\n\n".join(handoffs[-3:])) if handoffs else ""
        task = (f"Team goal: {goal}\n\n"
                f"YOUR work unit ({unit.id}): {unit.title}\n"
                f"{unit.description}"
                + (f"\n\nCompletion criteria:{criteria}" if criteria else "")
                + handoff_text)

        loop = AgentLoop(
            project_root=self.project_root,
            model=self.model,
            adapter=self.adapter,
            belt=_belt_for_role(role.tools),
            system_prompt=role.system_prompt,
            trajectory_mode=f"mesh-{role.name}",
            emit=forward,
            permission_gate=self.permission_gate,
            max_turns=max(1, min(role.max_turns, remaining_turns)),
            context_window=self.context_window,
            extra_system=self.extra_system,
            session_store=None,
            cancel_token=self.cancel_token,
        )
        try:
            result = loop.run(task)
        except AgentCancelledError:
            return MeshAgentResult(unit_id=unit.id, role=unit.role,
                                   status="cancelled")
        except Exception as exc:
            logger.exception("Mesh unit crashed: %s", unit.id)
            return MeshAgentResult(unit_id=unit.id, role=unit.role,
                                   status="failed", summary=str(exc)[:500])
        status = "completed" if result.get("success") else (
            "cancelled" if result.get("status") == "cancelled" else "failed")
        summary = str(result.get("final_text") or "").strip()
        if not summary:
            summary = (f"{role.display_name} ended with status "
                       f"{result.get('status') or 'failed'} and produced no handoff.")
        return MeshAgentResult(
            unit_id=unit.id, role=unit.role, status=status,
            summary=summary,
            mutated_files=list(result.get("mutated_files") or []),
            turns=int(result.get("turns") or 0),
            checkpoint_id=result.get("checkpoint_id"),
        )

    # ── Synthesis + persistence ──────────────────────────────────────

    def _synthesize(self, goal: str, units: list[WorkUnit],
                    results: list[MeshAgentResult],
                    conflicts: list[dict], mesh_status: str) -> str:
        mechanical = self._mechanical_report(goal, units, results,
                                             conflicts, mesh_status)
        try:
            message = self.model.complete(
                [{"role": "system", "content":
                  "You are the mesh orchestrator writing the final report "
                  "for the user. Summarize what the team did, what changed, "
                  "what was verified, open issues, and conflicts. Be "
                  "factual — only claim what the unit summaries support. "
                  "Under 250 words, plain text."},
                 {"role": "user", "content": mechanical}],
                extras={"max_tokens": 700, "temperature": 0.2},
                on_delta=None)
            text = str(message.get("content") or "").strip()
            return text or mechanical
        except Exception:
            return mechanical

    @staticmethod
    def _mechanical_report(goal: str, units: list[WorkUnit],
                           results: list[MeshAgentResult],
                           conflicts: list[dict], mesh_status: str) -> str:
        lines = [f"Goal: {goal}", f"Mesh status: {mesh_status}", ""]
        by_id = {r.unit_id: r for r in results}
        for unit in units:
            result = by_id.get(unit.id)
            lines.append(f"[{unit.role} / {unit.id}] {unit.title} — "
                         f"{unit.status}"
                         + (f", {len(result.mutated_files)} file(s) changed"
                            if result else ""))
            if result and result.summary:
                lines.append(f"  {result.summary[:400]}")
        if conflicts:
            lines.append("")
            lines.append("Conflicts (files touched by multiple units):")
            for conflict in conflicts:
                lines.append(f"  {conflict['file']}: "
                             + ", ".join(conflict["units"]))
        return "\n".join(lines)

    def _persist(self, summary: dict[str, Any]) -> None:
        try:
            folder = self.project_root / ".nexcoder" / "mesh"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{summary['mesh_id']}.json"
            path.write_text(json.dumps(summary, ensure_ascii=False,
                                       indent=2, default=str),
                            encoding="utf-8")
        except Exception:
            logger.warning("Mesh persist failed", exc_info=True)


def list_mesh_runs(project_root: str | Path, limit: int = 20) -> list[dict]:
    """Summaries of past mesh runs, newest first (for the panel)."""
    folder = Path(project_root) / ".nexcoder" / "mesh"
    if not folder.is_dir():
        return []
    out: list[dict] = []
    entries = sorted(folder.glob("mesh_*.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    for entry in entries[:limit]:
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
            out.append({
                "mesh_id": data.get("mesh_id"),
                "goal": str(data.get("goal") or "")[:160],
                "status": data.get("status"),
                "elapsed_seconds": data.get("elapsed_seconds"),
                "agents": len(data.get("agents") or []),
                "mutated_files": len(data.get("mutated_files") or []),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return out
