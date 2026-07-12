"""FileSystemHandler — file operations, tree building, search, and watching."""

import os
import re
import shutil
import tempfile
import fnmatch
import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, QThread

logger = logging.getLogger(__name__)

# Directories to always skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "env",
    ".nexcoder", "dist", "build", ".eggs", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".tox", ".next", ".nuxt", "target",
}

# Binary file extensions (skip content reading)
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".o", ".obj",
    ".pyc", ".pyo", ".class", ".wasm",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".sqlite", ".db",
}


class FileWatcher(QThread):
    """Background thread watching a directory for changes using watchdog."""

    tree_changed = Signal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self._running = True

    def run(self) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class Handler(FileSystemEventHandler):
                def __init__(self, signal):
                    self._signal = signal

                def on_any_event(self, event):
                    # Skip events in ignored directories
                    src = event.src_path
                    parts = Path(src).parts
                    if any(p in SKIP_DIRS for p in parts):
                        return
                    self._signal.emit(src)

            observer = Observer()
            handler = Handler(self.tree_changed)
            observer.schedule(handler, self._path, recursive=True)
            observer.start()

            while self._running:
                observer.join(timeout=1)

            observer.stop()
            observer.join()
        except ImportError:
            logger.warning("watchdog not installed, file watching disabled")
        except Exception as e:
            logger.error(f"File watcher error: {e}")

    def stop(self) -> None:
        self._running = False
        self.wait()


class FileSystemHandler(QObject):
    """Handles all file system operations for the IPC bridge."""

    tree_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._watcher: FileWatcher | None = None
        self._gitignore_patterns: list[str] = []
        self._trusted_root: str | None = None

    def set_trusted_root(self, root: str | None) -> None:
        """Limit mutating and file-read operations to the active project root."""
        self._trusted_root = os.path.abspath(root) if root else None

    def _resolve_path(self, path: str, *, must_exist: bool = False) -> str:
        """Resolve a user-provided path and ensure it stays inside the trusted root."""
        if not path:
            raise ValueError("Path is required")

        if self._trusted_root:
            abs_path = (
                os.path.abspath(path)
                if os.path.isabs(path)
                else os.path.abspath(os.path.join(self._trusted_root, path))
            )
            try:
                common = os.path.commonpath([self._trusted_root, abs_path])
            except ValueError as exc:
                raise PermissionError("Path is outside the active project") from exc
            if common != self._trusted_root:
                raise PermissionError("Path is outside the active project")
        else:
            abs_path = os.path.abspath(path)

        if must_exist and not os.path.exists(abs_path):
            raise FileNotFoundError(f"Path not found: {abs_path}")

        return abs_path

    # ── File Operations ───────────────────────────────────────────────

    def read_file(self, path: str) -> str:
        """Read a text file, with encoding detection."""
        abs_path = self._resolve_path(path)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"File not found: {abs_path}")

        ext = os.path.splitext(abs_path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            raise ValueError(f"Cannot read binary file: {abs_path}")

        # Try UTF-8 first, then fallback
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                with open(abs_path, "r", encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue

        raise ValueError(f"Could not decode file: {abs_path}")

    def write_file(self, path: str, content: str) -> None:
        """Write content to file using atomic write (temp → rename)."""
        abs_path = self._resolve_path(path)
        dir_path = os.path.dirname(abs_path)

        # Ensure directory exists
        os.makedirs(dir_path, exist_ok=True)

        # Atomic write: write to temp file, then rename
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".nexcoder_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            # On Windows, we need to remove the target first
            if os.path.exists(abs_path):
                os.replace(tmp_path, abs_path)
            else:
                os.rename(tmp_path, abs_path)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def delete_path(self, path: str) -> None:
        """Delete a file or directory."""
        abs_path = self._resolve_path(path, must_exist=True)
        if os.path.isfile(abs_path):
            os.unlink(abs_path)
        elif os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        else:
            raise FileNotFoundError(f"Path not found: {abs_path}")

    def rename_path(self, old_path: str, new_path: str) -> None:
        """Rename / move a file or directory."""
        abs_old = self._resolve_path(old_path, must_exist=True)
        abs_new = self._resolve_path(new_path)
        if not os.path.exists(abs_old):
            raise FileNotFoundError(f"Path not found: {abs_old}")
        os.makedirs(os.path.dirname(abs_new), exist_ok=True)
        os.rename(abs_old, abs_new)

    def create_directory(self, path: str) -> None:
        """Create a directory (mkdir -p)."""
        os.makedirs(self._resolve_path(path), exist_ok=True)

    # ── File Tree ─────────────────────────────────────────────────────

    def get_file_tree(self, root: str) -> list[dict[str, Any]]:
        """Build a recursive file tree, respecting .gitignore and skip dirs."""
        abs_root = os.path.abspath(root)
        if not os.path.isdir(abs_root):
            raise NotADirectoryError(f"Not a directory: {abs_root}")

        # Load .gitignore if present
        self._load_gitignore(abs_root)

        return self._build_tree(abs_root, abs_root)

    def _build_tree(self, path: str, root: str) -> list[dict[str, Any]]:
        """Recursively build a file tree."""
        items: list[dict[str, Any]] = []

        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return items

        for entry in entries:
            name = entry.name

            # Skip hidden files/dirs (except .env.example, .gitignore)
            if name.startswith(".") and name not in (".env.example", ".gitignore", ".eslintrc.json"):
                continue

            # Skip known directories
            if entry.is_dir() and name in SKIP_DIRS:
                continue

            # Check gitignore
            rel_path = os.path.relpath(entry.path, root)
            if self._is_gitignored(rel_path, entry.is_dir()):
                continue

            if entry.is_dir():
                children = self._build_tree(entry.path, root)
                items.append({
                    "name": name,
                    "path": entry.path.replace("\\", "/"),
                    "type": "directory",
                    "children": children,
                })
            else:
                ext = os.path.splitext(name)[1].lower()
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0

                items.append({
                    "name": name,
                    "path": entry.path.replace("\\", "/"),
                    "type": "file",
                    "extension": ext,
                    "size": size,
                })

        return items

    def _load_gitignore(self, root: str) -> None:
        """Load .gitignore patterns from the project root."""
        gitignore_path = os.path.join(root, ".gitignore")
        self._gitignore_patterns = []
        if os.path.isfile(gitignore_path):
            try:
                with open(gitignore_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            self._gitignore_patterns.append(line)
            except Exception:
                pass

    def _is_gitignored(self, rel_path: str, is_dir: bool) -> bool:
        """Check if a relative path matches any .gitignore pattern."""
        # Normalize to forward slashes
        rel_path = rel_path.replace("\\", "/")
        name = os.path.basename(rel_path)

        for pattern in self._gitignore_patterns:
            # Directory-specific patterns
            if pattern.endswith("/"):
                if is_dir and fnmatch.fnmatch(name, pattern.rstrip("/")):
                    return True
                continue

            # Match against name and full relative path
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return True

        return False

    # ── Search ────────────────────────────────────────────────────────

    def search_files(self, query: str, root: str) -> list[dict[str, Any]]:
        """Search for text in project files (grep-like)."""
        results: list[dict[str, Any]] = []
        abs_root = os.path.abspath(root)
        query_lower = query.lower()
        max_results = 200

        for dirpath, dirnames, filenames in os.walk(abs_root):
            # Skip ignored directories (modifying in-place to prune walk)
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for filename in filenames:
                if len(results) >= max_results:
                    return results

                ext = os.path.splitext(filename)[1].lower()
                if ext in BINARY_EXTENSIONS:
                    continue

                filepath = os.path.join(dirpath, filename)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if query_lower in line.lower():
                                results.append({
                                    "file": filepath.replace("\\", "/"),
                                    "line": line_num,
                                    "content": line.rstrip()[:200],
                                    "column": line.lower().index(query_lower),
                                })
                                if len(results) >= max_results:
                                    return results
                except (OSError, UnicodeDecodeError):
                    continue

        return results

    # ── File Watching ─────────────────────────────────────────────────

    def watch_directory(self, path: str) -> None:
        """Start watching a directory for changes."""
        # Stop existing watcher
        if self._watcher:
            self._watcher.stop()

        self._watcher = FileWatcher(path)
        self._watcher.tree_changed.connect(self.tree_changed.emit)
        self._watcher.start()

    def stop_watching(self) -> None:
        """Stop the file watcher."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    # ── Utilities ─────────────────────────────────────────────────────

    @staticmethod
    def get_file_stats(path: str) -> dict[str, Any]:
        """Get file stats (size, modified time, type)."""
        abs_path = os.path.abspath(path)
        stat = os.stat(abs_path)
        ext = os.path.splitext(abs_path)[1].lower()
        return {
            "path": abs_path.replace("\\", "/"),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "isDirectory": os.path.isdir(abs_path),
            "isBinary": ext in BINARY_EXTENSIONS,
            "extension": ext,
        }
