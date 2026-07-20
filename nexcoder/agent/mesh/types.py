"""Mesh data model + plan parsing/validation (pure, model-free).

The orchestrator asks the model for a JSON work-unit plan; everything
here defends against the ways a small local model mangles that JSON and
guarantees the mesh always ends up with a bounded, executable plan.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

MESH_ROLES = ("explorer", "implementation", "test", "review")
MAX_WORK_UNITS = 4


@dataclass
class WorkUnit:
    id: str
    title: str
    role: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    status: str = "queued"  # queued|running|completed|failed|blocked|cancelled

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "role": self.role,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "completion_criteria": list(self.completion_criteria),
            "status": self.status,
        }


@dataclass
class MeshAgentResult:
    unit_id: str
    role: str
    status: str
    summary: str = ""
    mutated_files: list[str] = field(default_factory=list)
    turns: int = 0
    checkpoint_id: str | None = None


def new_mesh_id() -> str:
    return f"mesh_{uuid.uuid4().hex[:8]}"


# ── Plan parsing ─────────────────────────────────────────────────────

def _extract_json_array(text: str) -> list | None:
    """Pull the first JSON array out of model text (fences tolerated)."""
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end <= start:
        # Maybe wrapped: {"work_units": [...]}
        try:
            obj = json.loads(cleaned.strip())
            if isinstance(obj, dict):
                units = obj.get("work_units") or obj.get("units")
                if isinstance(units, list):
                    return units
        except json.JSONDecodeError:
            pass
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
        return parsed if isinstance(parsed, list) else None
    except json.JSONDecodeError:
        return None


def default_plan(goal: str) -> list[WorkUnit]:
    """Safe fallback when the model cannot produce a valid plan."""
    return [
        WorkUnit(id="work_1", title="Explore the relevant code",
                 role="explorer",
                 description=("Locate the files, structure, and conventions "
                              f"relevant to: {goal}. Report findings.")),
        WorkUnit(id="work_2", title="Implement the goal",
                 role="implementation",
                 description=goal, dependencies=["work_1"]),
        WorkUnit(id="work_3", title="Review the changes",
                 role="review",
                 description=("Review the changes made for this goal for "
                              "correctness and consistency."),
                 dependencies=["work_2"]),
    ]


def parse_plan(text: str, goal: str) -> tuple[list[WorkUnit], bool]:
    """Parse a model-written plan. Returns (units, used_fallback)."""
    raw = _extract_json_array(text)
    if not raw:
        return default_plan(goal), True
    units: list[WorkUnit] = []
    seen_ids: set[str] = set()
    for item in raw[:MAX_WORK_UNITS * 2]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in MESH_ROLES:
            continue
        unit_id = str(item.get("id") or "").strip() or f"work_{len(units) + 1}"
        while unit_id in seen_ids:
            unit_id = f"{unit_id}_{len(units) + 1}"
        seen_ids.add(unit_id)
        deps = item.get("dependencies")
        criteria = item.get("completion_criteria")
        units.append(WorkUnit(
            id=unit_id,
            title=str(item.get("title") or item.get("description") or unit_id)[:120],
            role=role,
            description=str(item.get("description") or item.get("title") or "")[:2000],
            dependencies=[str(d) for d in deps if isinstance(d, (str, int))]
            if isinstance(deps, list) else [],
            completion_criteria=[str(c)[:200] for c in criteria[:6]]
            if isinstance(criteria, list) else [],
        ))
        if len(units) >= MAX_WORK_UNITS:
            break
    if not units or not any(u.description.strip() for u in units):
        return default_plan(goal), True
    # Dependencies may reference dropped/unknown units — filter them.
    known = {u.id for u in units}
    for unit in units:
        unit.dependencies = [d for d in unit.dependencies
                             if d in known and d != unit.id]
    return topo_sort(units), False


def topo_sort(units: list[WorkUnit]) -> list[WorkUnit]:
    """Order units so dependencies come first; cycles get their offending
    edges dropped (plan order wins) rather than failing the mesh."""
    by_id = {u.id: u for u in units}
    ordered: list[WorkUnit] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(unit: WorkUnit) -> None:
        if unit.id in done:
            return
        if unit.id in visiting:
            return  # cycle — drop the edge by ignoring it
        visiting.add(unit.id)
        for dep in list(unit.dependencies):
            dep_unit = by_id.get(dep)
            if dep_unit is None:
                unit.dependencies.remove(dep)
                continue
            if dep_unit.id in visiting:
                unit.dependencies.remove(dep)  # break the cycle
                continue
            visit(dep_unit)
        visiting.discard(unit.id)
        done.add(unit.id)
        ordered.append(unit)

    for unit in units:
        visit(unit)
    return ordered


def detect_conflicts(results: list[MeshAgentResult]) -> list[dict[str, Any]]:
    """Files touched by more than one agent (sequential runs still make
    this worth surfacing: a later agent rewriting an earlier agent's
    file is the #1 silent-overwrite hazard)."""
    touched: dict[str, list[str]] = {}
    for result in results:
        for path in result.mutated_files:
            touched.setdefault(path, []).append(result.unit_id)
    return [{"file": path, "units": units}
            for path, units in sorted(touched.items()) if len(units) > 1]
