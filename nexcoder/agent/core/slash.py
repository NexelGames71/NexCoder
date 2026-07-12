"""Slash-command parsing shared by the CLI and the UI bridge."""

from __future__ import annotations

DEFAULT_SKILL_TASK = "Follow the skill instructions on the current project state."


def parse_slash_command(text: str, known_ids: set[str]) -> tuple[str | None, str]:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return None, text
    first, _, rest = stripped[1:].partition(" ")
    if first in known_ids:
        return first, rest.strip() or DEFAULT_SKILL_TASK
    return None, text
