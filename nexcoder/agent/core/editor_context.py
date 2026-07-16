"""Render IDE editor state (active file, selection) into the task prompt.

The UI attaches what the user is looking at to every run; the loop sees
it as a trailing context section, so "fix this" means the selected code
without the user having to paste it.
"""

from __future__ import annotations

from pathlib import Path

# Selections beyond this are truncated: enough to ground the model,
# small enough to never crowd out the conversation budget.
MAX_SELECTION_CHARS = 4000

# Prior-conversation replay: a few recent exchanges give follow-up
# prompts ("now add tests for that") their referent without flooding
# the fresh run's context.
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 700


def render_chat_history(messages: list[dict] | None) -> str:
    """Render recent session messages as a prompt preamble, or "".

    Each item needs ``role`` ("user"/"assistant") and ``content``. The
    result ends with a "Current request" header so the model can tell
    replayed context from the live task.
    """
    if not messages:
        return ""
    lines: list[str] = []
    for message in messages[-MAX_HISTORY_MESSAGES:]:
        role = str(message.get("role", "")).strip().lower()
        text = str(message.get("content", "")).strip()
        if role not in ("user", "assistant") or not text:
            continue
        if len(text) > MAX_HISTORY_CHARS:
            text = text[:MAX_HISTORY_CHARS] + " …(truncated)"
        lines.append(f"{'User' if role == 'user' else 'Assistant'}: {text}")
    if not lines:
        return ""
    return ("--- Prior conversation (earlier in this chat session) ---\n"
            + "\n\n".join(lines)
            + "\n--- Current request ---\n")


def _relative(path: str, project_root: Path | str | None) -> str:
    if not project_root:
        return path
    try:
        return Path(path).resolve().relative_to(
            Path(project_root).resolve()).as_posix()
    except (ValueError, OSError):
        return path


def render_editor_context(context: dict | None,
                          project_root: Path | str | None = None) -> str:
    """Return a prompt section for the editor state, or "" if empty.

    ``context`` keys (all optional): ``active_file`` (str), ``selection``
    (dict with ``path``/``start_line``/``end_line``/``text``, or a bare
    string of selected text).
    """
    if not context:
        return ""
    lines: list[str] = []

    active_file = context.get("active_file")
    if isinstance(active_file, str) and active_file.strip():
        lines.append(f"Active file: {_relative(active_file.strip(), project_root)}")

    selection = context.get("selection")
    if isinstance(selection, str):
        selection = {"text": selection}
    if isinstance(selection, dict):
        text = selection.get("text")
        if isinstance(text, str) and text.strip():
            if len(text) > MAX_SELECTION_CHARS:
                text = text[:MAX_SELECTION_CHARS] + "\n... (selection truncated)"
            where = ""
            sel_path = selection.get("path")
            if isinstance(sel_path, str) and sel_path.strip():
                where = f" in {_relative(sel_path.strip(), project_root)}"
            start, end = selection.get("start_line"), selection.get("end_line")
            if isinstance(start, int) and isinstance(end, int):
                where += f" (lines {start}-{end})"
            lines.append(f"Selected code{where}:\n```\n{text}\n```")

    if not lines:
        return ""
    return ("\n\n--- Editor context (auto-attached; the user is currently "
            "looking at this) ---\n" + "\n".join(lines))
