"""File tools: read, precise search/replace edit, write, mkdir, move, ls.

Edits write straight to disk (Cursor-style autonomy); every mutation is
snapshotted into the run checkpoint first so the UI can revert any file
or the whole run.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.path_filters import should_skip_dir

MAX_READ_BYTES = 1024 * 1024
PROTECTED_PARTS = {".git", ".nexcoder", "node_modules", "venv", ".venv", "__pycache__"}


def _relative(ctx: ToolContext, path: Path) -> str:
    return path.relative_to(ctx.project_root).as_posix()


def _is_protected(relative_path: str) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in Path(relative_path).parts)


def _read_text(path: Path) -> str:
    # newline="" preserves CRLF so search/replace round-trips Windows files.
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(content)


def read_file(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    path = ctx.resolve(str(args.get("path") or ""))
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    if not path.is_file():
        return {"success": False, "error_code": "file_not_found",
                "error": f"File not found: {args.get('path')}"}
    if path.stat().st_size > MAX_READ_BYTES:
        return {"success": False, "error_code": "file_too_large",
                "error": "File exceeds 1MB read limit"}
    content = _read_text(path)
    lines = content.splitlines()
    total = len(lines)
    offset = int(args.get("offset") or 0)
    limit = int(args.get("limit") or 0)
    if offset or limit:
        start = max(0, offset - 1) if offset else 0
        end = start + limit if limit else total
        content = "\n".join(lines[start:end])
    return {"success": True, "content": content, "total_lines": total,
            "message": f"Read {args.get('path')} ({total} lines)"}


def _diff_payload(relative: str, old: str, new: str) -> dict[str, Any]:
    """Unified diff + added/removed counts for edit_applied events."""
    lines = list(difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile=f"a/{relative}", tofile=f"b/{relative}", lineterm=""))
    added = sum(1 for line in lines
                if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in lines
                  if line.startswith("-") and not line.startswith("---"))
    text = "\n".join(lines)
    if len(text) > 20000:
        text = text[:20000] + "\n... (diff truncated)"
    return {"diff": text, "added": added, "removed": removed}


def edit_file(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    target = str(args.get("path") or "")
    old = args.get("old_string")
    new = args.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str) or not old:
        return {"success": False, "error_code": "invalid_args",
                "error": "edit_file requires path, old_string, new_string"}
    if old == new:
        return {"success": False, "error_code": "no_change",
                "error": "old_string and new_string are identical"}
    path = ctx.resolve(target)
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    relative = _relative(ctx, path)
    if _is_protected(relative):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project path"}
    if ctx.safety.is_sensitive_file(relative):
        return {"success": False, "error_code": "tool_sensitive_file",
                "error": "Sensitive file edit blocked"}
    if not path.is_file():
        return {"success": False, "error_code": "file_not_found",
                "error": f"File not found: {target}"}
    content = _read_text(path)
    count = content.count(old)
    if count == 0:
        return {"success": False, "error_code": "not_found_in_file",
                "error": "old_string not found in file. Re-read the file and "
                         "copy the exact text, including whitespace."}
    replace_all = bool(args.get("replace_all"))
    if count > 1 and not replace_all:
        return {"success": False, "error_code": "ambiguous_match",
                "error": f"old_string matches {count} times. Add surrounding "
                         "context to make it unique, or set replace_all: true."}
    updated = content.replace(old, new) if replace_all else content.replace(old, new, 1)
    ctx.snapshot_before_mutation(relative)
    _write_text(path, updated)
    replacements = count if replace_all else 1
    ctx.emit(AgentEvent("edit_applied", {
        "path": relative, "replacements": replacements,
        **_diff_payload(relative, content, updated)}))
    return {"success": True, "replacements": replacements,
            "message": f"Edited {relative} ({replacements} replacement(s))"}


def write_file(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    target = str(args.get("path") or "")
    content = args.get("content")
    if not isinstance(content, str):
        return {"success": False, "error_code": "invalid_args",
                "error": "Missing file content"}
    path = ctx.resolve(target)
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    relative = _relative(ctx, path)
    if _is_protected(relative):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project path"}
    if ctx.safety.is_sensitive_file(relative):
        return {"success": False, "error_code": "tool_sensitive_file",
                "error": "Sensitive file write blocked"}
    append = bool(args.get("append"))
    existed = path.is_file()
    previous = _read_text(path) if existed else ""
    ctx.snapshot_before_mutation(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if append and existed:
        updated = previous + content
        _write_text(path, updated)
        ctx.emit(AgentEvent("edit_applied", {
            "path": relative, "created": False, "append": True,
            **_diff_payload(relative, previous, updated)}))
        return {"success": True,
                "message": f"Appended {len(content)} chars to {relative}"}
    _write_text(path, content)
    ctx.emit(AgentEvent("edit_applied", {
        "path": relative, "created": not existed,
        **_diff_payload(relative, previous, content)}))
    action = "Updated" if existed else "Created"
    return {"success": True, "message": f"{action} {relative}"}


def create_directory(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    path = ctx.resolve(str(args.get("path") or ""))
    if path is None or path == ctx.project_root:
        return {"success": False, "error_code": "blocked",
                "error": "Directory must be inside the active project"}
    relative = _relative(ctx, path)
    if _is_protected(relative):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project path"}
    if path.exists() and not path.is_dir():
        return {"success": False, "error_code": "path_conflict",
                "error": f"A file already exists at {relative}"}
    path.mkdir(parents=True, exist_ok=True)
    return {"success": True, "message": f"Directory ready: {relative}"}


def move_path(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    source = ctx.resolve(str(args.get("source") or ""))
    destination = ctx.resolve(str(args.get("destination") or ""))
    if source is None or destination is None or source == ctx.project_root:
        return {"success": False, "error_code": "blocked",
                "error": "Move must stay inside the active project"}
    source_rel = _relative(ctx, source)
    dest_rel = _relative(ctx, destination)
    if _is_protected(source_rel) or _is_protected(dest_rel):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project paths cannot be moved"}
    if ctx.safety.is_sensitive_file(source_rel) or ctx.safety.is_sensitive_file(dest_rel):
        return {"success": False, "error_code": "tool_sensitive_file",
                "error": "Sensitive file move blocked"}
    if not source.exists():
        return {"success": False, "error_code": "file_not_found",
                "error": f"Source not found: {source_rel}"}
    if destination.exists():
        return {"success": False, "error_code": "path_conflict",
                "error": f"Destination already exists: {dest_rel}"}
    if source.is_file():
        ctx.snapshot_before_mutation(source_rel)
        ctx.snapshot_before_mutation(dest_rel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    return {"success": True, "message": f"Moved {source_rel} -> {dest_rel}"}


def list_directory(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    path = ctx.resolve(str(args.get("path") or "."))
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    if not path.is_dir():
        return {"success": False, "error_code": "directory_not_found",
                "error": "Directory not found"}
    entries = []
    for child in sorted(path.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir() and should_skip_dir(child.name, skip_hidden=False):
            continue
        entries.append({"name": child.name,
                        "type": "directory" if child.is_dir() else "file"})
        if len(entries) >= 200:
            break
    return {"success": True, "entries": entries,
            "message": f"Listed {len(entries)} item(s)"}


_PATH_PARAM = {"type": "object",
               "properties": {"path": {"type": "string", "description": "Project-relative path"}},
               "required": ["path"]}


def register_file_tools(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="read_file",
        description="Read a file. Optional offset (1-based line) and limit narrow the range.",
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"}}, "required": ["path"]},
        handler=read_file))
    belt.register(ToolSpec(
        name="edit_file",
        description=("Replace an exact string in a file. old_string must match the file "
                     "text exactly (including whitespace) and exactly once, unless "
                     "replace_all is true. Preferred over write_file for existing files."),
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"}},
            "required": ["path", "old_string", "new_string"]},
        handler=edit_file, mutating=True))
    belt.register(ToolSpec(
        name="write_file",
        description=("Create a new file or fully overwrite an existing one. "
                     "For long files, write in parts: first call without "
                     "append, then continue with append=true — keep each "
                     "call under ~150 lines so it is never cut off."),
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "append": {"type": "boolean"}}, "required": ["path", "content"]},
        handler=write_file, mutating=True))
    belt.register(ToolSpec(
        name="create_directory", description="Create a directory (parents included).",
        parameters=_PATH_PARAM, handler=create_directory, mutating=True))
    belt.register(ToolSpec(
        name="move_path", description="Move or rename a file or directory.",
        parameters={"type": "object", "properties": {
            "source": {"type": "string"}, "destination": {"type": "string"}},
            "required": ["source", "destination"]},
        handler=move_path, mutating=True))
    belt.register(ToolSpec(
        name="list_directory", description="List directory entries.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=list_directory))
