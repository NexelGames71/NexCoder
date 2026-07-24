"""Typed records used by Plan Mode.

The JSON representation is intentionally boring and versioned.  Plans are
project data that must survive application upgrades and partial failures, so
the runtime never persists Python-specific object graphs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanStatus(str, Enum):
    IDLE = "idle"
    CLARIFYING = "clarifying"
    DRAFTING = "drafting"
    AWAITING_APPROVAL = "awaiting_approval"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class ClarificationOption:
    id: str
    label: str
    description: str = ""


@dataclass
class ClarificationQuestion:
    id: str
    title: str
    kind: str = "single"
    explanation: str = ""
    options: list[ClarificationOption] = field(default_factory=list)
    required: bool = True
    answer: Any = None


@dataclass
class PlannedFileChange:
    path: str
    operation: str = "modify"
    description: str = ""
    confirmed: bool = True


@dataclass
class PlanRisk:
    title: str
    mitigation: str
    severity: str = "medium"


@dataclass
class ValidationStep:
    description: str
    command: str = ""
    status: str = TaskStatus.PENDING.value


@dataclass
class PlanTask:
    id: str
    title: str
    description: str = ""
    status: str = TaskStatus.PENDING.value


@dataclass
class PlanPhase:
    id: str
    title: str
    description: str = ""
    tasks: list[PlanTask] = field(default_factory=list)
    status: str = TaskStatus.PENDING.value


@dataclass
class PlanRevision:
    revision: int
    markdown_content: str
    summary: str
    created_at: str = field(default_factory=utcnow)


@dataclass
class PlanDeviation:
    id: str
    classification: str
    description: str
    proposed_amendment: str = ""
    created_at: str = field(default_factory=utcnow)


@dataclass
class ImplementationPlan:
    id: str
    conversation_id: str
    title: str
    objective: str
    original_request: str
    project_name: str = ""
    status: str = PlanStatus.DRAFTING.value
    task_id: str = ""
    clarified_requirements: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    current_state_findings: list[str] = field(default_factory=list)
    proposed_architecture: list[str] = field(default_factory=list)
    questions: list[ClarificationQuestion] = field(default_factory=list)
    phases: list[PlanPhase] = field(default_factory=list)
    files: list[PlannedFileChange] = field(default_factory=list)
    risks: list[PlanRisk] = field(default_factory=list)
    validation_steps: list[ValidationStep] = field(default_factory=list)
    definition_of_done: list[str] = field(default_factory=list)
    markdown_content: str = ""
    revision: int = 0
    revisions: list[PlanRevision] = field(default_factory=list)
    deviations: list[PlanDeviation] = field(default_factory=list)
    project_fingerprint: str = ""
    inspected_files: list[str] = field(default_factory=list)
    saved_markdown_path: str = ""
    approval_revision: int | None = None
    approved_at: str = ""
    approved_by: str = ""
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    schema_version: int = 1

    @classmethod
    def create(cls, *, conversation_id: str, request: str,
               title: str = "Implementation Plan",
               project_name: str = "") -> "ImplementationPlan":
        return cls(
            id=f"plan_{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            title=title,
            objective=request.strip(),
            original_request=request.strip(),
            project_name=project_name,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImplementationPlan":
        questions = []
        for raw in data.get("questions") or []:
            options = [ClarificationOption(**item)
                       for item in raw.get("options") or []]
            questions.append(ClarificationQuestion(
                id=str(raw.get("id", "")), title=str(raw.get("title", "")),
                kind=str(raw.get("kind", "single")),
                explanation=str(raw.get("explanation", "")),
                options=options, required=bool(raw.get("required", True)),
                answer=raw.get("answer")))
        phases = []
        for raw in data.get("phases") or []:
            phases.append(PlanPhase(
                id=str(raw.get("id", "")), title=str(raw.get("title", "")),
                description=str(raw.get("description", "")),
                status=str(raw.get("status", TaskStatus.PENDING.value)),
                tasks=[PlanTask(**item) for item in raw.get("tasks") or []]))
        values = dict(data)
        values["questions"] = questions
        values["phases"] = phases
        values["files"] = [PlannedFileChange(**item)
                           for item in data.get("files") or []]
        values["risks"] = [PlanRisk(**item) for item in data.get("risks") or []]
        values["validation_steps"] = [ValidationStep(**item)
                                      for item in data.get("validation_steps") or []]
        values["revisions"] = [PlanRevision(**item)
                               for item in data.get("revisions") or []]
        values["deviations"] = [PlanDeviation(**item)
                                for item in data.get("deviations") or []]
        allowed = cls.__dataclass_fields__
        return cls(**{key: value for key, value in values.items()
                      if key in allowed})
