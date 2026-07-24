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
MAX_DIAGNOSTICS = 40
MAX_DIAGNOSTIC_MESSAGE_CHARS = 500

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


def _severity_label(value: object) -> str:
    if value == 1:
        return "error"
    if value == 2:
        return "warning"
    if value == 4:
        return "hint"
    return "info"


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

    diagnostics = context.get("diagnostics")
    if isinstance(diagnostics, list) and diagnostics:
        counts = context.get("diagnostic_counts")
        if isinstance(counts, dict):
            total = counts.get("total", len(diagnostics))
            errors = counts.get("errors", 0)
            warnings = counts.get("warnings", 0)
            header = (
                f"Open IDE problems: {total} total"
                f" ({errors} errors, {warnings} warnings)."
            )
        else:
            header = f"Open IDE problems: {len(diagnostics)} total."
        problem_lines = [header]
        for item in diagnostics[:MAX_DIAGNOSTICS]:
            if not isinstance(item, dict):
                continue
            path = item.get("relative_path") or item.get("path")
            if isinstance(path, str):
                display_path = _relative(path.strip(), project_root)
            else:
                display_path = "unknown"
            line = item.get("line")
            column = item.get("column")
            location = display_path
            if isinstance(line, int) and line > 0:
                location += f":{line}"
                if isinstance(column, int) and column > 0:
                    location += f":{column}"
            message = str(item.get("message") or "").strip()
            if len(message) > MAX_DIAGNOSTIC_MESSAGE_CHARS:
                message = message[:MAX_DIAGNOSTIC_MESSAGE_CHARS] + " ... (truncated)"
            source = str(item.get("source") or "").strip()
            label = _severity_label(item.get("severity"))
            source_suffix = f" [{source}]" if source else ""
            problem_lines.append(f"- {label} {location}{source_suffix}: {message}")
        lines.append("\n".join(problem_lines))

    text_attachments = context.get("text_attachments")
    if isinstance(text_attachments, list) and text_attachments:
        file_lines = ["Referenced files from the composer:"]
        for item in text_attachments[:12]:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not isinstance(path, str) or not path.strip():
                continue
            name = str(item.get("name") or Path(path).name).strip()
            size = item.get("size")
            size_label = f", {size} bytes" if isinstance(size, int) else ""
            file_lines.append(
                f"- {name}: {_relative(path.strip(), project_root)}{size_label}. "
                "Read this file if it is relevant to the user's task.")
        if len(file_lines) > 1:
            lines.append("\n".join(file_lines))

    if not lines:
        return ""
    return ("\n\n--- Editor context (auto-attached; the user is currently "
            "looking at this) ---\n" + "\n".join(lines))
