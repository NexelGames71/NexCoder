"""File, regex, and relevance-ranked code search for project retrieval."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.core.walk import iter_project_files

TEXT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".md",
                   ".json", ".toml", ".txt", ".css", ".html", ".yaml", ".yml",
                   ".java", ".kt", ".kts", ".go", ".rs", ".cs", ".cpp", ".cc",
                   ".c", ".h", ".hpp", ".rb", ".php", ".swift", ".vue", ".svelte"}
GLOB_CAP = 100
GREP_DEFAULT_CAP = 50
CODE_SEARCH_DEFAULT_CAP = 12
CODE_SEARCH_FILE_CAP = 1200
CODE_SEARCH_BYTES = 512 * 1024
_WORD_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$-]*")
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "with", "where", "which",
}


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


def _search_files(target: Path):
    """Yield files below a directory, or the file itself.

    Agents naturally narrow searches by passing a path returned from glob or
    code_search. Treating a file path as invalid made that sensible workflow
    fail and encouraged repeated, increasingly broad searches.
    """
    if target.is_file():
        yield target
        return
    yield from iter_project_files(target)


def _target_relative(path: Path, target: Path) -> str:
    return path.name if target.is_file() else path.relative_to(target).as_posix()


def glob_tool(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return {"success": False, "error_code": "invalid_args", "error": "Missing pattern"}
    root = ctx.resolve(str(args.get("path") or "."))
    if root is None or not (root.is_file() or root.is_dir()):
        return {"success": False, "error_code": "blocked",
                "error": "Search path is outside the project or missing"}
    matches: list[tuple[float, str]] = []
    for path in _search_files(root):
        relative = _target_relative(path, root)
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
    if root is None or not (root.is_file() or root.is_dir()):
        return {"success": False, "error_code": "blocked",
                "error": "Search path is outside the project or missing"}
    name_glob = str(args.get("glob") or "")
    cap = int(args.get("max_results") or GREP_DEFAULT_CAP)
    results: list[dict[str, Any]] = []
    for path in _search_files(root):
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        relative = _target_relative(path, root)
        if name_glob and not _matches(relative, path.name, name_glob):
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


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for token in _WORD_RE.findall(query):
        expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token).lower()
        for part in expanded.split():
            if len(part) >= 2 and part not in _STOP_WORDS and part not in terms:
                terms.append(part)
    return terms[:12]


def code_search_tool(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Rank relevant files and matching lines for a natural-language query.

    This deliberately stays local and deterministic: path/symbol-like terms,
    exact phrases, and line density are combined without sending repository
    content to an embedding service.
    """
    query = str(args.get("query") or "").strip()
    terms = _query_terms(query)
    if not terms:
        return {"success": False, "error_code": "invalid_args",
                "error": "Query needs at least one meaningful term"}
    root = ctx.resolve(str(args.get("path") or "."))
    if root is None or not (root.is_file() or root.is_dir()):
        return {"success": False, "error_code": "blocked",
                "error": "Search path is outside the project or missing"}
    cap = max(1, min(30, int(args.get("max_results") or CODE_SEARCH_DEFAULT_CAP)))
    phrase = " ".join(query.lower().split())
    ranked: list[tuple[float, str, list[dict[str, Any]]]] = []
    scanned = 0
    for path in _search_files(root):
        if scanned >= CODE_SEARCH_FILE_CAP:
            break
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        scanned += 1
        try:
            if path.stat().st_size > CODE_SEARCH_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        relative = path.relative_to(ctx.project_root).as_posix()
        path_lower = relative.lower()
        text_lower = text.lower()
        score = 0.0
        for term in terms:
            if term in path_lower:
                score += 10.0 + (5.0 if term in path.stem.lower() else 0.0)
            score += min(text_lower.count(term), 10) * 1.25
        if phrase and phrase in text_lower:
            score += 18.0
        if score <= 0:
            continue

        line_hits: list[tuple[int, int, str]] = []
        for line_number, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            density = sum(1 for term in terms if term in lowered)
            if density:
                line_hits.append((density, line_number, line.strip()[:300]))
        line_hits.sort(key=lambda item: (-item[0], item[1]))
        snippets = [
            {"line": line_number, "content": content}
            for _, line_number, content in line_hits[:3]
        ]
        score += sum(hit[0] for hit in line_hits[:3]) * 2.0
        ranked.append((score, relative, snippets))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    results = [
        {"file": relative, "score": round(score, 2), "snippets": snippets}
        for score, relative, snippets in ranked[:cap]
    ]
    return {"success": True, "results": results, "scanned_files": scanned,
            "message": f"Ranked {len(results)} relevant file(s) from {scanned} scanned"}


def register_search_tools(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="glob",
        description=("Find files by glob pattern (e.g. **/*.py). Newest first. "
                     "The optional path may be a project-relative file or directory."),
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"]},
        handler=glob_tool))
    belt.register(ToolSpec(
        name="grep",
        description=("Regex search file contents. Optional glob filters paths. "
                     "The optional path may be a project-relative file or directory."),
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"},
            "glob": {"type": "string"}, "max_results": {"type": "integer"}},
            "required": ["pattern"]},
        handler=grep_tool))
    belt.register(ToolSpec(
        name="code_search",
        description=("Find files relevant to a natural-language code question. "
                     "Returns ranked paths and matching line snippets; use before "
                     "grep when you do not know exact symbols. The optional path "
                     "may be a project-relative file or directory."),
        parameters={"type": "object", "properties": {
            "query": {"type": "string"}, "path": {"type": "string"},
            "max_results": {"type": "integer"}}, "required": ["query"]},
        handler=code_search_tool))
