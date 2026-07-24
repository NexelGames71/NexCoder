"""Command risk classification and autonomy levels.

Instead of one flat "prompt for every command" policy, commands are
classified by what they can do, and the user picks an autonomy level
that decides which classes run without asking:

- ``read_only`` commands inspect state and can always run.
- ``write`` commands change the project (build, test, file writes via
  shell) — routine agent work.
- ``risky`` commands change things that are hard to undo or that leave
  the workspace: dependency installs, network access, git history
  rewrites, publishing, system changes.

The hard blocklist (``SafetyChecker``) still runs before any of this
and cannot be relaxed by autonomy.
"""

from __future__ import annotations

import re

from nexcoder.agent.core.tools.base import ALLOW, DENY, PermissionGate

READ_ONLY = "read_only"
WRITE = "write"
RISKY = "risky"

AUTONOMY_LEVELS = ("read_only", "ask", "risky_only", "full_auto")

# Inspection-only commands. Matched against the first token(s); these
# never modify state so every autonomy level runs them silently.
_READ_ONLY_PATTERNS = [
    r"^(dir|ls|pwd|tree)\b",
    r"^(type|cat|head|tail|more)\b",
    r"^(rg|grep|findstr|find|where|which)\b",
    r"^git (status|log|diff|show|branch|remote -v|blame)\b",
    r"^(python|python3|py|node|npm|pip|cargo|go|dotnet|java|rustc)"
    r" (--version|-v|version)\b",
    r"^pip (list|show|freeze)\b",
    r"^npm (ls|list|view|outdated)\b",
    r"^Get-(ChildItem|Content|Item|Location|Process|Command)\b",
]

# Commands that are hard to undo, leave the workspace, or change the
# environment. Full-auto denies these; risky_only prompts for them.
_RISKY_PATTERNS = [
    # dependency changes
    r"\bpip3? install\b", r"\bpip3? uninstall\b",
    r"\bnpm (install|i|uninstall|update|audit fix)\b",
    r"\byarn (add|remove|upgrade)\b", r"\bpnpm (add|remove|update)\b",
    r"\bcargo (install|add|remove)\b", r"\bgo (get|install)\b",
    r"\bdotnet add package\b", r"\bchoco install\b", r"\bwinget install\b",
    # network
    r"\bcurl\b", r"\bwget\b", r"\bInvoke-WebRequest\b", r"\biwr\b",
    r"\bInvoke-RestMethod\b", r"\birm\b", r"\bssh\b", r"\bscp\b",
    # git history / remotes / destructive
    r"\bgit push\b", r"\bgit reset --hard\b", r"\bgit clean\b",
    r"\bgit rebase\b", r"\bgit filter-branch\b",
    r"\bnpm publish\b", r"\bcargo publish\b", r"\btwine upload\b",
    # deletion / destructive filesystem
    r"\brm -r", r"\brm -f", r"\bdel /[sfq]", r"\brd /s", r"\brmdir /s",
    r"\bRemove-Item\b.*(-Recurse|-Force)", r"\bformat\b",
    # system / environment changes
    r"\bsetx\b", r"\breg (add|delete)\b", r"\bschtasks\b",
    r"\bnet (user|localgroup)\b", r"\bsc (create|config|delete)\b",
    r"\bshutdown\b", r"\bSet-ExecutionPolicy\b",
    r"\btaskkill\b", r"\bStop-Process\b",
    # env files / secrets
    r"\.env\b.*(>|Set-Content|Out-File)", r">\s*\.env\b",
]

_READ_ONLY_RES = [re.compile(p, re.IGNORECASE) for p in _READ_ONLY_PATTERNS]
_RISKY_RES = [re.compile(p, re.IGNORECASE) for p in _RISKY_PATTERNS]


def classify_command(command: str) -> str:
    """Classify a shell command as read_only / write / risky."""
    text = " ".join((command or "").split())
    if not text:
        return READ_ONLY
    # Compound commands are as risky as their riskiest part; a read-only
    # classification must hold for the whole line.
    for pattern in _RISKY_RES:
        if pattern.search(text):
            return RISKY
    if any(sep in text for sep in (";", "&&", "||", "|", "`", "$(")):
        return WRITE
    for pattern in _READ_ONLY_RES:
        if pattern.match(text):
            return READ_ONLY
    return WRITE


class AutonomyGate:
    """Applies the workspace autonomy level before asking the user.

    - ``ask``: every command goes to the inner gate (classic behavior).
    - ``risky_only``: read-only and routine write commands auto-allow;
      risky commands go to the inner gate.
    - ``full_auto``: read-only and write auto-allow; risky commands are
      DENIED outright (never silently executed).
    - ``read_only``: only read-only commands run; everything else is
      denied. (The runtime additionally strips mutating tools from the
      belt at this level; this gate is defense in depth.)
    """

    def __init__(self, inner: PermissionGate, level: str = "ask") -> None:
        self.inner = inner
        self.level = level if level in AUTONOMY_LEVELS else "ask"

    def request(self, *, tool: str, detail: str) -> str:
        risk = classify_command(detail)
        if self.level == "read_only":
            return ALLOW if risk == READ_ONLY else DENY
        if risk == READ_ONLY:
            return ALLOW
        if self.level == "full_auto":
            return DENY if risk == RISKY else ALLOW
        if self.level == "risky_only" and risk == WRITE:
            return ALLOW
        return self.inner.request(tool=tool, detail=detail)
