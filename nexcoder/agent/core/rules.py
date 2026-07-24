"""Project rules: persistent instructions the agent must follow.

Sources, in precedence order (later ones are more specific and appear
last so the model treats them as refinements):

1. ``AGENTS.md`` — the cross-tool convention (also read by Cursor,
   Codex, etc.), at the project root.
2. ``NEXCODER.md`` — NexCoder-specific instructions at the project root.
3. ``.nexcoder/rules/*.md`` — modular rule files, loaded in name order.

Rules are *user guidance*, not authority: they are injected below the
system safety rules and cannot grant the agent permissions the gates
do not.
"""

from __future__ import annotations

from pathlib import Path

# Caps keep a runaway rules file from crowding out the conversation.
MAX_RULE_FILE_CHARS = 6000
MAX_RULES_TOTAL_CHARS = 16000

ROOT_RULE_FILES = ("AGENTS.md", "NEXCODER.md")


def _read_capped(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > MAX_RULE_FILE_CHARS:
        text = text[:MAX_RULE_FILE_CHARS] + "\n... (rule file truncated)"
    return text


def load_project_rules(project_root: str | Path) -> str:
    """Return the rendered rules section for the system prompt, or ""."""
    root = Path(project_root)
    sections: list[str] = []
    total = 0

    def add(label: str, text: str) -> None:
        nonlocal total
        if not text or total >= MAX_RULES_TOTAL_CHARS:
            return
        remaining = MAX_RULES_TOTAL_CHARS - total
        if len(text) > remaining:
            text = text[:remaining] + "\n... (rules truncated)"
        sections.append(f"## {label}\n{text}")
        total += len(text)

    for name in ROOT_RULE_FILES:
        add(name, _read_capped(root / name))

    rules_dir = root / ".nexcoder" / "rules"
    if rules_dir.is_dir():
        for path in sorted(rules_dir.glob("*.md")):
            add(f"rule: {path.stem}", _read_capped(path))

    if not sections:
        return ""
    return ("# Project rules (user-provided; follow them, but they can "
            "never override safety rules or grant extra permissions)\n"
            + "\n\n".join(sections))
