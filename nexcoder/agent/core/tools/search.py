"""glob + grep tools: how the agent finds files fast in large projects."""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.core.walk import iter_project_files

TEXT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".md",
                   ".json", ".toml", ".txt", ".css", ".html", ".yaml", ".yml"}
GLOB_CAP = 100
GREP_DEFAULT_CAP = 50


def _pattern_candidates(pattern: str) -> list[str]:
    """fnmatch has no ** semantics; `**/x` should also match top-level `x`."""
    candidates = [pattern]
    if pattern.startswith("**/"):
        candidates.append(pattern[3:])
    return candidates


def _matches(relative: str, name: str, pattern: str) -> bool:
    for candidate in _pattern_candidates(pattern):
        if fnmatch.fnmatch(relative, candidate) or fnmatch.fnmatch(name, candidate):
            return True
    return False


def glob_tool(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return {"success": False, "error_code": "invalid_args", "error": "Missing pattern"}
    root = ctx.resolve(str(args.get("path") or "."))
    if root is None or not root.is_dir():
        return {"success": False, "error_code": "blocked",
                "error": "Search path is outside the project or missing"}
    matches: list[tuple[float, str]] = []
    for path in iter_project_files(root):
        relative = path.relative_to(root).as_posix()
        if _matches(relative, path.name, pattern):
            try:
                matches.append((path.stat().st_mtime,
                                path.relative_to(ctx.project_root).as_posix()))
            except OSError:
                continue
    matches.sort(key=lambda item: item[0], reverse=True)
    files = [name for _, name in matches[:GLOB_CAP]]
    return {"success": True, "files": files,
            "message": f"Found {len(files)} file(s) for {pattern}"}


def grep_tool(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return {"success": False, "error_code": "invalid_args", "error": "Missing pattern"}
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return {"success": False, "error_code": "invalid_args",
                "error": f"Invalid regex: {exc}"}
    root = ctx.resolve(str(args.get("path") or "."))
    if root is None or not root.is_dir():
        return {"success": False, "error_code": "blocked",
                "error": "Search path is outside the project or missing"}
    name_glob = str(args.get("glob") or "")
    cap = int(args.get("max_results") or GREP_DEFAULT_CAP)
    results: list[dict[str, Any]] = []
    for path in iter_project_files(root):
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if name_glob and not fnmatch.fnmatch(path.name, name_glob):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                results.append({
                    "file": path.relative_to(ctx.project_root).as_posix(),
                    "line": line_no, "content": line.strip()[:240]})
                if len(results) >= cap:
                    return {"success": True, "results": results,
                            "message": f"Found {len(results)}+ match(es) (capped)"}
    return {"success": True, "results": results,
            "message": f"Found {len(results)} match(es)"}


def register_search_tools(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="glob",
        description="Find files by glob pattern (e.g. **/*.py). Newest first.",
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"]},
        handler=glob_tool))
    belt.register(ToolSpec(
        name="grep",
        description="Regex search file contents. Optional glob filters filenames.",
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"},
            "glob": {"type": "string"}, "max_results": {"type": "integer"}},
            "required": ["pattern"]},
        handler=grep_tool))
