"""ContextBuilder — builds AI context from project files and selections."""

import os
import logging
from typing import Any, Callable

from nexcoder.agent.path_filters import should_skip_dir

logger = logging.getLogger(__name__)

# Default context window size (characters, not tokens)
DEFAULT_MAX_CONTEXT_CHARS = 24000  # ~8K tokens

# Extensions to include in broad codebase scans
SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cpp", ".c", ".h", ".md"}

# Keywords in the prompt that trigger a broad codebase scan
BROAD_SCAN_TRIGGERS = {
    "codebase", "entire", "all files", "whole project", "all the", "every file",
    "project structure", "architecture", "overview", "across the", "entire project",
}


class ContextBuilder:
    """Builds context windows for AI queries from project files."""

    def __init__(self, max_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> None:
        self._max_chars = max_chars

    def build(
        self,
        context: dict[str, Any],
        project_root: str | None = None,
        on_file_read: Callable[[str], None] | None = None,
    ) -> str:
        """Build a context string from the provided context dict.

        Context dict can contain:
        - currentFile: path of the active file
        - currentContent: full content of the active file
        - selection: selected text in the editor
        - cursorLine: current cursor line number
        - openFiles: list of open file paths
        - errorOutput: terminal error output
        - relatedFiles: list of related file paths to include
        - prompt: the user's prompt (used for keyword extraction and scan mode)
        """
        parts: list[str] = []
        total_chars = 0

        # Get project root from context if not passed
        if not project_root:
            project_root = context.get("project_path") or context.get("projectPath")

        prompt = context.get("prompt", "").lower()

        # 1. Project structure summary
        if project_root:
            structure = self._get_project_structure(project_root)
            if structure:
                parts.append(f"## Project Structure\n```\n{structure}\n```\n")
                total_chars += len(parts[-1])

        # 2. Current file content
        current_file = context.get("currentFile")
        current_content = context.get("currentContent", "")

        if current_file and current_content:
            ext = os.path.splitext(current_file)[1].lstrip(".")
            header = f"## Current File: `{os.path.basename(current_file)}`\n"
            code_block = f"```{ext}\n{current_content}\n```\n"

            if total_chars + len(header) + len(code_block) < self._max_chars:
                parts.append(header + code_block)
                total_chars += len(parts[-1])
                if on_file_read:
                    on_file_read(os.path.basename(current_file))

        # 3. Selection (if any)
        selection = context.get("selection", "")
        if selection:
            cursor_line = context.get("cursorLine", "?")
            sel_block = f"## Selected Code (line {cursor_line})\n```\n{selection}\n```\n"
            if total_chars + len(sel_block) < self._max_chars:
                parts.append(sel_block)
                total_chars += len(parts[-1])

        # 4. Error output (for debug mode)
        error_output = context.get("errorOutput", "")
        if error_output:
            err_block = f"## Error Output\n```\n{error_output[:3000]}\n```\n"
            if total_chars + len(err_block) < self._max_chars:
                parts.append(err_block)
                total_chars += len(parts[-1])

        # 5. Related files — either explicitly listed or auto-discovered
        related_files = list(context.get("relatedFiles", []))

        # Detect if the user wants a broad codebase scan.
        # Skip auto-loading 20 files for short/trivial prompts (e.g. "hello").
        trivial_prompt = len(prompt.strip()) < 40 and not any(
            trigger in prompt for trigger in BROAD_SCAN_TRIGGERS
        )
        is_broad_scan = (
            not trivial_prompt
            and (
                not current_file  # no active file in editor
                or any(trigger in prompt for trigger in BROAD_SCAN_TRIGGERS)
            )
        )

        if is_broad_scan and project_root:
            # Broad scan: gather the most relevant source files
            broad_files = self._gather_broad_files(project_root, current_file)
            for path in broad_files:
                if path not in related_files:
                    related_files.append(path)
        elif project_root and prompt:
            # Targeted search: extract keywords from prompt and search index
            try:
                import re
                words = re.findall(r"\b[a-zA-Z_]{3,}\b", prompt.lower())
                stop_words = {
                    "the", "and", "for", "you", "that", "this", "with", "have", "can",
                    "your", "from", "are", "but", "not", "what", "all", "about", "how",
                    "codebase", "project", "code", "file", "files", "please", "scan",
                    "read", "find", "search", "check", "tell", "explain", "where", "show",
                    "get", "set", "use", "make", "need", "like", "should", "would", "here"
                }
                search_terms = [w for w in words if w not in stop_words]
                if search_terms:
                    from nexcoder.services.file_index import FileIndex
                    index = FileIndex(project_root)
                    index.index_directory(project_root)

                    query = " OR ".join(search_terms)
                    results = index.search(query, limit=5)
                    for r in results:
                        path = r["path"]
                        if current_file and os.path.abspath(path) == os.path.abspath(current_file):
                            continue
                        if path not in related_files:
                            related_files.append(path)
            except Exception as e:
                logger.debug(f"Error auto-retrieving context files: {e}")

        for rel_path in related_files:
            if total_chars >= self._max_chars:
                break
            try:
                abs_path = rel_path
                if not os.path.isabs(rel_path) and project_root:
                    abs_path = os.path.join(project_root, rel_path)

                if os.path.isfile(abs_path):
                    with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    ext = os.path.splitext(abs_path)[1].lstrip(".")
                    name = os.path.basename(abs_path)
                    file_block = f"## Related File: `{name}`\n```{ext}\n{content[:4000]}\n```\n"

                    if total_chars + len(file_block) < self._max_chars:
                        parts.append(file_block)
                        total_chars += len(parts[-1])
                        if on_file_read:
                            on_file_read(name)
            except Exception:
                continue

        return "\n".join(parts)

    def _gather_broad_files(
        self, root: str, current_file: str | None, max_files: int = 20
    ) -> list[str]:
        """Gather the most recently modified source files from the project."""
        candidates: list[tuple[float, str]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skip dirs in-place
            dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SCAN_EXTENSIONS:
                    continue
                full = os.path.join(dirpath, fname)
                if current_file and os.path.abspath(full) == os.path.abspath(current_file):
                    continue
                try:
                    mtime = os.path.getmtime(full)
                    candidates.append((mtime, full))
                except OSError:
                    pass

        # Sort by most recently modified, take top N
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [path for _, path in candidates[:max_files]]

    def _get_project_structure(self, root: str, max_depth: int = 3) -> str:
        """Generate a compact project structure summary."""
        lines: list[str] = []
        self._walk_structure(root, root, lines, 0, max_depth)
        return "\n".join(lines[:60])  # Cap at 60 lines

    def _walk_structure(
        self, path: str, root: str, lines: list[str], depth: int, max_depth: int
    ) -> None:
        """Recursively walk directory structure."""
        if depth > max_depth:
            return

        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        indent = "  " * depth
        for entry in entries:
            if entry.name.startswith(".") and depth == 0:
                continue
            if entry.is_dir():
                if should_skip_dir(entry.name, skip_hidden=False):
                    continue
                lines.append(f"{indent}{entry.name}/")
                self._walk_structure(entry.path, root, lines, depth + 1, max_depth)
            else:
                lines.append(f"{indent}{entry.name}")
