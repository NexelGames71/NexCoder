"""Deterministic Plan Mode transitions."""

from __future__ import annotations

from nexcoder.agent.planning.models import PlanStatus


TRANSITIONS: dict[str, frozenset[str]] = {
    PlanStatus.IDLE.value: frozenset({PlanStatus.CLARIFYING.value,
                                      PlanStatus.DRAFTING.value}),
    PlanStatus.CLARIFYING.value: frozenset({PlanStatus.DRAFTING.value,
                                            PlanStatus.CANCELLED.value}),
    PlanStatus.DRAFTING.value: frozenset({PlanStatus.CLARIFYING.value,
                                          PlanStatus.AWAITING_APPROVAL.value,
                                          PlanStatus.CANCELLED.value,
                                          PlanStatus.FAILED.value}),
    PlanStatus.AWAITING_APPROVAL.value: frozenset({
        PlanStatus.REVISION_REQUESTED.value, PlanStatus.APPROVED.value,
        PlanStatus.CANCELLED.value}),
    PlanStatus.REVISION_REQUESTED.value: frozenset({
        PlanStatus.CLARIFYING.value, PlanStatus.DRAFTING.value,
        PlanStatus.CANCELLED.value}),
    PlanStatus.APPROVED.value: frozenset({PlanStatus.EXECUTING.value,
                                         PlanStatus.CANCELLED.value}),
    PlanStatus.EXECUTING.value: frozenset({
        PlanStatus.PAUSED.value, PlanStatus.COMPLETED.value,
        PlanStatus.FAILED.value, PlanStatus.CANCELLED.value}),
    PlanStatus.PAUSED.value: frozenset({
        PlanStatus.REVISION_REQUESTED.value, PlanStatus.EXECUTING.value,
        PlanStatus.CANCELLED.value, PlanStatus.FAILED.value}),
    PlanStatus.FAILED.value: frozenset({PlanStatus.REVISION_REQUESTED.value,
                                       PlanStatus.CANCELLED.value}),
    PlanStatus.COMPLETED.value: frozenset(),
    PlanStatus.CANCELLED.value: frozenset(),
}


class InvalidPlanTransition(ValueError):
    pass


def validate_transition(current: str, target: str) -> None:
    if target == current:
        return
    if target not in TRANSITIONS.get(current, frozenset()):
        raise InvalidPlanTransition(
            f"Invalid plan transition: {current} -> {target}")
