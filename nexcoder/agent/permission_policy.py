"""Pattern-based tool permissions inspired by OpenCode's rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Literal


PermissionAction = Literal["allow", "ask", "deny"]


@dataclass(frozen=True)
class PermissionRule:
    permission: str
    action: PermissionAction
    pattern: str = "*"


@dataclass(frozen=True)
class PermissionDecision:
    permission: str
    action: PermissionAction
    pattern: str
    reason: str

    @property
    def allows_execution(self) -> bool:
        return self.action == "allow"


TOOL_PERMISSIONS = {
    "list_directory": "read",
    "read_file": "read",
    "search_grep": "read",
    "load_skill": "read",
    "write_file": "edit",
    "create_directory": "edit",
    "move_path": "edit",
    "run_command": "execute",
}


class PermissionPolicy:
    """Evaluate tool permissions with the last matching rule winning."""

    def __init__(self, rules: list[PermissionRule] | tuple[PermissionRule, ...]) -> None:
        self.rules = tuple(rules)

    @classmethod
    def for_access_mode(cls, access_mode: str | None) -> "PermissionPolicy":
        mode = str(access_mode or "full").strip().lower().replace("-", "_")
        if mode == "read_only":
            return cls([
                PermissionRule("*", "deny"),
                PermissionRule("read", "allow"),
            ])
        return cls([PermissionRule("*", "allow")])

    def evaluate(self, tool: str, target: str | None = None) -> PermissionDecision:
        permission = TOOL_PERMISSIONS.get(tool, tool)
        candidate = target or "*"
        match: PermissionRule | None = None
        for rule in self.rules:
            if fnmatchcase(permission, rule.permission) and fnmatchcase(candidate, rule.pattern):
                match = rule
        if match is None:
            return PermissionDecision(
                permission=permission,
                action="ask",
                pattern=candidate,
                reason=f"Permission is required for {permission}",
            )
        reason = {
            "allow": f"{permission.capitalize()} access allowed",
            "ask": f"Approval is required for {permission} access",
            "deny": f"{permission.capitalize()} access is disabled by the active tool policy",
        }[match.action]
        return PermissionDecision(permission, match.action, candidate, reason)
