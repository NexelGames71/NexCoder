"""Strict parsing for Plan Mode slash and approval commands."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PlanCommand:
    action: str
    argument: str = ""


_APPROVALS = {
    "proceed", "approve", "approve the plan", "implement this plan",
    "start implementation", "approve and proceed",
}


def parse_plan_command(value: str) -> PlanCommand | None:
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower().rstrip(".! ")
    if lowered in _APPROVALS:
        return PlanCommand("approve")
    revision_approval = re.fullmatch(r"approve revision (\d+)", lowered)
    if revision_approval:
        return PlanCommand("approve", revision_approval.group(1))
    if not lowered.startswith("/plan"):
        return None
    rest = text[5:].strip()
    if not rest:
        return PlanCommand("start")
    match = re.match(r"^(revise|save|cancel|status)(?:\s+(.*))?$", rest,
                     flags=re.IGNORECASE)
    if match:
        return PlanCommand(match.group(1).lower(), (match.group(2) or "").strip())
    return PlanCommand("start", rest)
