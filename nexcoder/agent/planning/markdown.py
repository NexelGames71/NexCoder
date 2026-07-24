"""Render a structured plan to stable, reviewable Markdown."""

from __future__ import annotations

from nexcoder.agent.planning.models import ImplementationPlan


def render_plan_markdown(plan: ImplementationPlan) -> str:
    lines = [
        f"# Implementation Plan: {plan.title}", "",
        f"- Status: {plan.status}",
        f"- Revision: {plan.revision}",
        f"- Created: {plan.created_at}",
        f"- Plan ID: {plan.id}",
    ]
    if plan.project_name:
        lines.append(f"- Project: {plan.project_name}")
    if plan.approved_at:
        lines.append(f"- Approved: {plan.approved_at}")
    lines += ["", "## Objective", "", plan.objective or plan.original_request]

    def section(title: str, values: list[str]) -> None:
        if not values:
            return
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- {value}" for value in values)

    section("Current-State Findings", plan.current_state_findings)
    section("Proposed Architecture", plan.proposed_architecture)
    section("Confirmed Requirements", plan.clarified_requirements)
    section("Assumptions", plan.assumptions)

    if plan.phases:
        lines.extend(["", "## Implementation Phases", ""])
        for index, phase in enumerate(plan.phases, 1):
            lines.extend([f"### Phase {index}: {phase.title}", ""])
            if phase.description:
                lines.extend([phase.description, ""])
            lines.extend(f"- [{_task_mark(task.status)}] {task.title}"
                         + (f" — {task.description}" if task.description else "")
                         for task in phase.tasks)
            lines.append("")

    if plan.files:
        lines.extend(["", "## File Changes", ""])
        for item in plan.files:
            qualifier = "confirmed" if item.confirmed else "proposed"
            lines.append(
                f"- `{item.path}` — {item.operation}; {item.description} ({qualifier})")

    if plan.risks:
        lines.extend(["", "## Risks and Mitigations", ""])
        for risk in plan.risks:
            lines.append(f"- **{risk.title}** ({risk.severity}): {risk.mitigation}")

    if plan.validation_steps:
        lines.extend(["", "## Testing Strategy", ""])
        for step in plan.validation_steps:
            suffix = f" — `{step.command}`" if step.command else ""
            lines.append(f"- {step.description}{suffix}")

    section("Definition of Done", plan.definition_of_done)

    if plan.revisions:
        lines.extend(["", "## Revision History", ""])
        for revision in plan.revisions:
            lines.append(
                f"- Revision {revision.revision} — {revision.summary} "
                f"({revision.created_at})")
    return "\n".join(lines).strip() + "\n"


def _task_mark(status: str) -> str:
    return "x" if status in ("completed", "skipped") else " "
