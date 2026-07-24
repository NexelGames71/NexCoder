"""Mesh role profiles — bounded specialists over the v2 AgentLoop.

Same philosophy as core/profiles.py: a role is a voice (prompt), a
reachable tool set (read-only roles structurally cannot mutate), and a
turn budget. Roles do NOT redefine the mesh goal — each one receives a
bounded work unit from the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexcoder.agent.core.profiles import READ_TOOLS

_BOUNDS_RULE = (
    "You are ONE specialist inside a coordinated team. Do ONLY your "
    "assigned work unit — do not expand scope, do not redo other "
    "agents' work, and trust the handoffs you were given unless the "
    "code contradicts them.\n")

_CITE_RULE = (
    "Ground every claim in the project: read files before describing "
    "them and cite paths you actually inspected.\n")


@dataclass(frozen=True)
class MeshRole:
    name: str
    display_name: str
    system_prompt: str
    tools: tuple[str, ...] | None  # None = full default belt
    max_turns: int


ROLES: dict[str, MeshRole] = {
    "explorer": MeshRole(
        name="explorer",
        display_name="Explorer",
        system_prompt=(
            "You are the Explorer agent: a fast repository scout.\n"
            + _BOUNDS_RULE + _CITE_RULE +
            "Locate the files, structure, frameworks, and conventions "
            "relevant to your work unit. Finish with a compact factual "
            "report (paths, key symbols, how the pieces connect, risks) "
            "that the next agents can act on without re-reading "
            "everything. Under ~300 words."),
        tools=READ_TOOLS,
        max_turns=10,
    ),
    "implementation": MeshRole(
        name="implementation",
        display_name="Implementation",
        system_prompt=(
            "You are the Implementation agent: a precise production "
            "coder.\n" + _BOUNDS_RULE + _CITE_RULE +
            "Implement your work unit with small, reviewable edits "
            "(prefer edit_file; write long new files in append parts). "
            "Meet every completion criterion. Run a quick verification "
            "when a project command is available. Finish with a short "
            "summary of what changed and how it was verified."),
        tools=None,
        max_turns=30,
    ),
    "test": MeshRole(
        name="test",
        display_name="Test",
        system_prompt=(
            "You are the Test agent: you make correctness observable.\n"
            + _BOUNDS_RULE + _CITE_RULE +
            "Create or extend tests for the changes described in your "
            "work unit and handoffs, run them, and report results. If "
            "tests fail, report exactly which and why — do NOT rewrite "
            "the implementation yourself; that is repair work for the "
            "orchestrator to assign. Finish with pass/fail counts."),
        tools=None,
        max_turns=20,
    ),
    "review": MeshRole(
        name="review",
        display_name="Review",
        system_prompt=(
            "You are the Review agent: an independent, read-only "
            "reviewer.\n" + _BOUNDS_RULE + _CITE_RULE +
            "Compare the combined changes against the original goal and "
            "each unit's completion criteria. Report findings with "
            "severities (critical / warning / info), citing file and "
            "line. You cannot modify code; propose fixes as descriptions. "
            "End with a verdict: approve, approve-with-notes, or "
            "needs-revision."),
        tools=READ_TOOLS,
        max_turns=12,
    ),
}


def get_role(name: str) -> MeshRole:
    role = ROLES.get(name)
    if role is None:
        raise ValueError(f"Unknown mesh role: {name!r}")
    return role
