"""Render the skill catalog block for the v2 agent system prompt."""

from __future__ import annotations

from nexcoder.agent.skills_registry import get_skills

HEADER = (
    "# Skills\n"
    "Load a skill with load_skill when the task matches its purpose, "
    "then follow it.")
TRUNCATION_MARKER = "[more skills omitted]"
DESCRIPTION_CAP = 60


def render_skills_catalog(project_root: str | None = None,
                          token_budget: int = 900) -> str:
    skills = get_skills(project_root)
    project = sorted((s for s in skills if s["category"] == "project"),
                     key=lambda s: s["id"])
    builtin = sorted((s for s in skills if s["category"] != "project"),
                     key=lambda s: s["id"])
    char_budget = token_budget * 3
    lines = [HEADER]
    used = len(HEADER)
    for skill in [*project, *builtin]:
        line = f"- {skill['id']} — {(skill['description'] or '')[:DESCRIPTION_CAP]}"
        if used + len(line) + 1 > char_budget:
            lines.append(TRUNCATION_MARKER)
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)
