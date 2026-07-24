"""Persistent project memory: durable lessons that survive across runs.

A plain markdown file at ``<project>/.nexcoder/MEMORY.md``. The loop
injects it into the system prompt at run start; the ``remember`` tool
appends to it. Newest notes win when the file is trimmed to its cap —
old context should age out, not crowd out fresh knowledge.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

MEMORY_CAP_CHARS = 8000
TRIM_MARKER = "<!-- older notes trimmed -->\n"


def _memory_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".nexcoder" / "MEMORY.md"


def load_project_memory(project_root: str | Path) -> str:
    try:
        return _memory_path(project_root).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def remember_note(project_root: str | Path, note: str) -> None:
    path = _memory_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_project_memory(project_root)
    entry = f"- [{date.today().isoformat()}] {note.strip()}"
    content = f"{existing}\n{entry}".strip() + "\n"
    if len(content) > MEMORY_CAP_CHARS:
        # Trim whole lines from the top; the newest notes are the most
        # likely to still be true.
        lines = content.splitlines(keepends=True)
        while lines and sum(len(line) for line in lines) > MEMORY_CAP_CHARS - len(TRIM_MARKER):
            lines.pop(0)
        content = TRIM_MARKER + "".join(lines)
    path.write_text(content, encoding="utf-8")
