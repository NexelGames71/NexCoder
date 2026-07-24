"""Application service for the complete Plan Mode lifecycle."""

from __future__ import annotations

from pathlib import Path
import threading
import uuid

from nexcoder.agent.planning.fingerprint import project_fingerprint
from nexcoder.agent.planning.markdown import render_plan_markdown
from nexcoder.agent.planning.models import (
    ClarificationOption, ClarificationQuestion, ImplementationPlan,
    PlanDeviation, PlanPhase, PlanRevision, PlanRisk, PlanStatus, PlanTask,
    PlannedFileChange, ValidationStep, utcnow,
)
from nexcoder.agent.planning.state_machine import validate_transition
from nexcoder.agent.planning.store import PlanStore


class PlanConflictError(RuntimeError):
    pass


class PlanApprovalError(RuntimeError):
    pass


class PlanManager:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.store = PlanStore(self.project_root)
        self._lock = threading.RLock()

    def create(self, *, conversation_id: str, request: str,
               title: str = "Implementation Plan") -> ImplementationPlan:
        plan = ImplementationPlan.create(
            conversation_id=conversation_id, request=request, title=title,
            project_name=self.project_root.name)
        plan.project_fingerprint = project_fingerprint(self.project_root)
        self.store.save(plan)
        return plan

    def load(self, plan_id: str) -> ImplementationPlan:
        return self.store.load(plan_id)

    def list(self, conversation_id: str = "") -> list[ImplementationPlan]:
        return self.store.list(conversation_id=conversation_id)

    def transition(self, plan: ImplementationPlan, target: str) -> None:
        validate_transition(plan.status, target)
        plan.status = target
        plan.updated_at = utcnow()

    def set_questions(self, plan_id: str, questions: list[dict]) -> ImplementationPlan:
        with self._lock:
            plan = self.load(plan_id)
            if plan.status not in (PlanStatus.DRAFTING.value,
                                   PlanStatus.CLARIFYING.value,
                                   PlanStatus.REVISION_REQUESTED.value):
                raise PlanConflictError("This plan is not accepting clarification questions")
            if plan.status != PlanStatus.CLARIFYING.value:
                self.transition(plan, PlanStatus.CLARIFYING.value)
            parsed: list[ClarificationQuestion] = []
            for index, raw in enumerate(questions):
                title = str(raw.get("title") or "").strip()
                if not title:
                    raise ValueError("Every clarification question needs a title")
                options = [ClarificationOption(
                    id=str(item.get("id") or f"option_{position}"),
                    label=str(item.get("label") or "").strip(),
                    description=str(item.get("description") or "").strip())
                    for position, item in enumerate(raw.get("options") or [])]
                parsed.append(ClarificationQuestion(
                    id=str(raw.get("id") or f"question_{index + 1}"),
                    title=title, kind=str(raw.get("kind") or "single"),
                    explanation=str(raw.get("explanation") or "").strip(),
                    options=options, required=bool(raw.get("required", True))))
            plan.questions = parsed
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def answer_questions(self, plan_id: str, expected_revision: int,
                         answers: dict) -> ImplementationPlan:
        with self._lock:
            plan = self._current(plan_id, expected_revision)
            if plan.status != PlanStatus.CLARIFYING.value:
                raise PlanConflictError("This plan is not waiting for answers")
            for question in plan.questions:
                if question.id in answers:
                    question.answer = answers[question.id]
                if question.required and question.answer in (None, "", []):
                    raise ValueError(f"Answer required: {question.title}")
            self.transition(plan, PlanStatus.DRAFTING.value)
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def submit_draft(self, plan_id: str, draft: dict,
                     summary: str = "Generated plan") -> ImplementationPlan:
        with self._lock:
            plan = self.load(plan_id)
            if plan.status not in (PlanStatus.DRAFTING.value,
                                   PlanStatus.REVISION_REQUESTED.value):
                raise PlanConflictError("This plan is not accepting a draft")
            plan.title = str(draft.get("title") or plan.title).strip()
            plan.objective = str(draft.get("objective") or plan.objective).strip()
            plan.current_state_findings = _strings(draft.get("current_state_findings"))
            plan.proposed_architecture = _strings(draft.get("proposed_architecture"))
            plan.clarified_requirements = _strings(draft.get("confirmed_requirements"))
            plan.assumptions = _strings(draft.get("assumptions"))
            plan.inspected_files = _strings(draft.get("inspected_files"))
            plan.files = [PlannedFileChange(
                path=str(item.get("path") or "").strip(),
                operation=str(item.get("operation") or "modify"),
                description=str(item.get("description") or "").strip(),
                confirmed=bool(item.get("confirmed", True)))
                for item in draft.get("files") or [] if item.get("path")]
            plan.risks = [PlanRisk(
                title=str(item.get("title") or "Risk"),
                mitigation=str(item.get("mitigation") or ""),
                severity=str(item.get("severity") or "medium"))
                for item in draft.get("risks") or []]
            plan.validation_steps = [ValidationStep(
                description=str(item.get("description") or ""),
                command=str(item.get("command") or ""))
                for item in draft.get("validation_steps") or []]
            plan.definition_of_done = _strings(draft.get("definition_of_done"))
            plan.phases = _parse_phases(draft.get("phases") or [])
            plan.revision += 1
            if plan.status == PlanStatus.REVISION_REQUESTED.value:
                self.transition(plan, PlanStatus.DRAFTING.value)
            self.transition(plan, PlanStatus.AWAITING_APPROVAL.value)
            plan.project_fingerprint = project_fingerprint(
                self.project_root, plan.inspected_files)
            plan.markdown_content = render_plan_markdown(plan)
            plan.revisions.append(PlanRevision(
                revision=plan.revision,
                markdown_content=plan.markdown_content,
                summary=summary or "Generated plan"))
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def request_revision(self, plan_id: str, expected_revision: int,
                         review: str) -> ImplementationPlan:
        with self._lock:
            plan = self._current(plan_id, expected_revision)
            if plan.status not in (PlanStatus.AWAITING_APPROVAL.value,
                                   PlanStatus.PAUSED.value,
                                   PlanStatus.FAILED.value):
                raise PlanConflictError("Only reviewable plans can be revised")
            self.transition(plan, PlanStatus.REVISION_REQUESTED.value)
            plan.assumptions.append(f"Revision request: {review.strip()}")
            plan.approved_at = ""
            plan.approved_by = ""
            plan.approval_revision = None
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def approve(self, plan_id: str, expected_revision: int,
                approved_by: str = "local-user") -> ImplementationPlan:
        with self._lock:
            plan = self._current(plan_id, expected_revision)
            if plan.status != PlanStatus.AWAITING_APPROVAL.value:
                raise PlanApprovalError("The current plan is not awaiting approval")
            current = project_fingerprint(self.project_root, plan.inspected_files)
            if current != plan.project_fingerprint:
                raise PlanApprovalError(
                    "The project changed after this plan was generated. Regenerate or revise it before approval.")
            self.transition(plan, PlanStatus.APPROVED.value)
            plan.approved_at = utcnow()
            plan.approved_by = approved_by
            plan.approval_revision = plan.revision
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def begin_execution(self, plan_id: str, expected_revision: int) -> ImplementationPlan:
        with self._lock:
            plan = self._current(plan_id, expected_revision)
            if (plan.status != PlanStatus.APPROVED.value
                    or plan.approval_revision != plan.revision):
                raise PlanApprovalError("Execution blocked: the implementation plan has not been approved.")
            self.transition(plan, PlanStatus.EXECUTING.value)
            if plan.phases and plan.phases[0].status == "pending":
                plan.phases[0].status = "in_progress"
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def complete(self, plan_id: str, success: bool) -> ImplementationPlan:
        with self._lock:
            plan = self.load(plan_id)
            # A material deviation deliberately pauses at an approval gate.
            # The worker finishing must not silently complete that plan.
            if plan.status == PlanStatus.PAUSED.value:
                return plan
            if plan.status != PlanStatus.EXECUTING.value:
                return plan
            if success:
                for phase in plan.phases:
                    phase.status = "completed"
                    for task in phase.tasks:
                        task.status = "completed"
                for step in plan.validation_steps:
                    step.status = "completed"
            else:
                for phase in plan.phases:
                    if phase.status == "in_progress":
                        phase.status = "failed"
                        for task in phase.tasks:
                            if task.status == "in_progress":
                                task.status = "failed"
            self.transition(plan, PlanStatus.COMPLETED.value if success
                            else PlanStatus.FAILED.value)
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def sync_progress(self, plan_id: str,
                      todos: list[dict]) -> ImplementationPlan:
        """Mirror execution todos into persisted plan tasks by position."""
        with self._lock:
            plan = self.load(plan_id)
            if plan.status != PlanStatus.EXECUTING.value:
                return plan
            tasks = [task for phase in plan.phases for task in phase.tasks]
            valid = {"pending", "in_progress", "completed"}
            for task, todo in zip(tasks, todos):
                status = str(todo.get("status") or "pending")
                task.status = status if status in valid else "pending"
            for phase in plan.phases:
                statuses = {task.status for task in phase.tasks}
                if statuses and statuses == {"completed"}:
                    phase.status = "completed"
                elif "in_progress" in statuses or "completed" in statuses:
                    phase.status = "in_progress"
                else:
                    phase.status = "pending"
            plan.updated_at = utcnow()
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def cancel(self, plan_id: str) -> ImplementationPlan:
        with self._lock:
            plan = self.load(plan_id)
            if plan.status in (PlanStatus.COMPLETED.value,
                               PlanStatus.CANCELLED.value):
                return plan
            self.transition(plan, PlanStatus.CANCELLED.value)
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def record_deviation(self, plan_id: str, classification: str,
                         description: str, amendment: str = "") -> ImplementationPlan:
        with self._lock:
            plan = self.load(plan_id)
            if plan.status != PlanStatus.EXECUTING.value:
                raise PlanConflictError("The plan is not executing")
            kind = "material" if classification == "material" else "minor"
            plan.deviations.append(PlanDeviation(
                id=f"deviation_{uuid.uuid4().hex[:8]}", classification=kind,
                description=description, proposed_amendment=amendment))
            if kind == "material":
                self.transition(plan, PlanStatus.PAUSED.value)
            plan.markdown_content = render_plan_markdown(plan)
            self.store.save(plan)
            return plan

    def note_saved(self, plan_id: str, path: str) -> ImplementationPlan:
        with self._lock:
            plan = self.load(plan_id)
            plan.saved_markdown_path = path
            plan.updated_at = utcnow()
            self.store.save(plan)
            return plan

    def assert_mutation_allowed(self, plan_id: str,
                                expected_revision: int) -> None:
        plan = self._current(plan_id, expected_revision)
        if (plan.status != PlanStatus.EXECUTING.value
                or plan.approval_revision != plan.revision):
            raise PlanApprovalError(
                "Execution blocked: the implementation plan has not been approved.")

    def _current(self, plan_id: str,
                 expected_revision: int) -> ImplementationPlan:
        plan = self.load(plan_id)
        if plan.revision != expected_revision:
            raise PlanConflictError(
                f"Stale plan revision: expected {expected_revision}, current {plan.revision}")
        return plan


def _strings(value: object) -> list[str]:
    return [str(item).strip() for item in (value or []) if str(item).strip()]


def _parse_phases(raw_phases: list[dict]) -> list[PlanPhase]:
    phases: list[PlanPhase] = []
    for index, raw in enumerate(raw_phases):
        tasks = [PlanTask(
            id=str(item.get("id") or f"phase_{index + 1}_task_{position + 1}"),
            title=str(item.get("title") or "Task").strip(),
            description=str(item.get("description") or "").strip())
            for position, item in enumerate(raw.get("tasks") or [])]
        phases.append(PlanPhase(
            id=str(raw.get("id") or f"phase_{index + 1}"),
            title=str(raw.get("title") or f"Phase {index + 1}").strip(),
            description=str(raw.get("description") or "").strip(), tasks=tasks))
    return phases
