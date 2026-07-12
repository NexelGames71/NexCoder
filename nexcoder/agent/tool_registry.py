"""Project-scoped tool registry for NexCoder agent mode."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
import subprocess
from typing import Any, Callable, Optional

from nexcoder.agent.cancellation import CancellationToken
from nexcoder.agent.errors import AgentCancelledError
from nexcoder.agent.patch_generator import PatchGenerator
from nexcoder.agent.path_filters import has_skipped_part, should_skip_dir
from nexcoder.agent.safety import SafetyChecker
from nexcoder.agent.skills_registry import get_skill_body
from nexcoder.services.checkpoint import CheckpointManager


TEXT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".toml", ".txt", ".css", ".html", ".yaml", ".yml"}


class ToolRegistry:
    """Executes trusted local tools inside the selected project root."""

    MAX_READ_BYTES = 1024 * 1024
    # Default budget for a single ``run_command`` invocation. Long enough
    # for builds and tests, short enough that an infinite-loop command
    # gets cut off in a reasonable time even without cancellation.
    DEFAULT_COMMAND_TIMEOUT = 180
    TOOL_ALIASES = {
        "list_project_tree": "list_directory",
        "search_code": "search_grep",
        "run_terminal_command": "run_command",
        "run_tests": "run_command",
        "create_folder": "create_directory",
        "make_directory": "create_directory",
        "mkdir": "create_directory",
        "move_file": "move_path",
        "rename_file": "move_path",
        "rename_path": "move_path",
    }

    @classmethod
    def canonical_tool_name(cls, tool: str) -> str:
        """Normalize common model aliases before policy and execution checks."""
        return cls.TOOL_ALIASES.get(tool, tool)

    def __init__(
        self,
        project_root: str | Path,
        *,
        on_diff: Callable[[dict[str, Any]], None] | None = None,
        modified_files: set[str] | None = None,
        cancellation_token: Optional[CancellationToken] = None,
        defer_diffs: bool = False,
        pending_patches: list[dict[str, Any]] | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.on_diff = on_diff or (lambda _diff: None)
        self.modified_files = modified_files if modified_files is not None else set()
        self.patch_gen = PatchGenerator(str(self.project_root))
        self.checkpoints = CheckpointManager(str(self.project_root))
        self.safety = SafetyChecker()
        self.cancellation_token = cancellation_token
        self.defer_diffs = defer_diffs
        self._pending_contents: dict[str, str] = {}
        self._pending_diffs: dict[str, dict[str, Any]] = {}
        self._pending_directories: set[str] = set()
        self._pending_removed_paths: set[str] = set()
        self._pending_moves: dict[str, str] = {}
        self._dirty_pending_keys: set[str] = set()
        self._seed_pending_patches(pending_patches or [])

    def _seed_pending_patches(self, patches: list[dict[str, Any]]) -> None:
        """Load an existing review patchset as a virtual filesystem."""
        for original in patches:
            patch = dict(original)
            target = str(patch.get("file") or "").replace("\\", "/").strip("/")
            if not target:
                continue
            action = patch.get("action", "modify")
            patch.pop("id", None)
            self._pending_diffs[target] = patch
            if action == "mkdir":
                self._pending_directories.add(target)
            elif action == "rmdir":
                self._pending_removed_paths.add(target)
            elif isinstance(patch.get("content"), str):
                self._pending_contents[target] = patch["content"]
            source = str(patch.get("source") or "").replace("\\", "/").strip("/")
            if source:
                self._pending_removed_paths.add(source)
                self._pending_moves[source] = target

    def execute(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> dict[str, Any]:
        # Per-call token wins over the registry-level one. Callers
        # (e.g. the executor) pass the active token explicitly; the
        # instance attribute is the fallback for tests that drive
        # ``execute`` directly.
        token = cancellation_token if cancellation_token is not None else self.cancellation_token
        if token is not None:
            token.raise_if_cancelled()

        tool = self.canonical_tool_name(tool)
        handlers = {
            "list_directory": self.list_directory,
            "read_file": self.read_file,
            "search_grep": self.search_grep,
            "write_file": self.write_file,
            "create_directory": self.create_directory,
            "move_path": self.move_path,
            "run_command": self.run_command,
            "load_skill": self.load_skill,
        }
        handler = handlers.get(tool)
        if handler is None:
            return {"success": False, "error_code": "unknown_tool", "error": f"Unknown tool: {tool}"}
        # Cancellation tokens flow into long-running tools that
        # know how to honour them. The simple tools (list_directory,
        # read_file, search_grep) are fast enough that they finish
        # before any user-driven cancel becomes meaningful, so we
        # only thread the token into ``run_command``.
        if tool == "run_command":
            return handler(args, cancellation_token=token)
        return handler(args)

    def target_for(self, tool: str, args: dict[str, Any]) -> str | None:
        tool = self.canonical_tool_name(tool)
        if tool in {"read_file", "write_file", "create_directory"}:
            return str(args.get("path") or "")
        if tool == "move_path":
            source = str(args.get("source") or "")
            destination = str(args.get("destination") or "")
            return f"{source} -> {destination}"
        if tool in {"list_directory", "list_project_tree"}:
            return str(args.get("path") or ".")
        if tool in {"search_grep", "search_code"}:
            return str(args.get("query") or "")
        if tool in {"run_command", "run_terminal_command", "run_tests"}:
            return str(args.get("command") or "")
        if tool == "load_skill":
            return str(args.get("id") or "")
        return None

    def label_for(self, tool: str) -> str:
        tool = self.canonical_tool_name(tool)
        return {
            "list_directory": "List directory",
            "list_project_tree": "List project tree",
            "read_file": "Read file",
            "search_grep": "Search code",
            "search_code": "Search code",
            "write_file": "Edit file",
            "create_directory": "Create folder",
            "move_path": "Move path",
            "run_command": "Run command",
            "run_terminal_command": "Run command",
            "run_tests": "Run tests",
            "load_skill": "Load skill",
        }.get(tool, f"Run {tool}")

    def _resolve(self, target: str) -> Path | None:
        try:
            path = (self.project_root / (target or ".")).resolve()
            common = os.path.commonpath([str(self.project_root), str(path)])
        except (OSError, ValueError):
            return None
        if common != str(self.project_root):
            return None
        return path

    @staticmethod
    def _normalize_relative(path: Path, root: Path) -> str:
        return path.relative_to(root).as_posix()

    @staticmethod
    def _is_protected_path(relative_path: str) -> bool:
        protected = {".git", ".nexcoder", "node_modules", "venv", ".venv", "__pycache__"}
        return any(part.lower() in protected for part in Path(relative_path).parts)

    def _path_is_removed(self, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/").strip("/")
        return any(
            normalized == removed or normalized.startswith(removed.rstrip("/") + "/")
            for removed in self._pending_removed_paths
        )

    def _suggest_matches(self, target: str) -> list[str]:
        name = Path(target).name.lower()
        if not name:
            return []
        matches: list[str] = []
        for path in self.project_root.rglob("*"):
            if has_skipped_part(path.relative_to(self.project_root).parts):
                continue
            if path.is_file() and path.name.lower() == name:
                matches.append(path.relative_to(self.project_root).as_posix())
                if len(matches) >= 8:
                    break
        return matches

    def virtual_text_files(self) -> dict[str, str]:
        """Return readable project text after applying the staged virtual state."""
        files: dict[str, str] = {}
        for path in self.project_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            relative = self._normalize_relative(path, self.project_root)
            if self._path_is_removed(relative) or has_skipped_part(Path(relative).parts):
                continue
            try:
                if path.stat().st_size <= self.MAX_READ_BYTES:
                    files[relative] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
        files.update(self._pending_contents)
        return {
            path: content
            for path, content in files.items()
            if not self._path_is_removed(path)
        }

    def _summary(self, result: dict[str, Any]) -> str:
        if result.get("success"):
            return result.get("message") or "Tool completed"
        code = result.get("error_code")
        if code == "file_not_found":
            return "File not found"
        if code == "blocked":
            return "Tool blocked"
        return result.get("error") or "Tool failed"

    def list_directory(self, args: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve(str(args.get("path") or "."))
        if path is None:
            return {"success": False, "error_code": "blocked", "error": "Path is outside the active project"}
        relative_path = path.relative_to(self.project_root).as_posix()
        pending_prefix = "" if relative_path == "." else relative_path.rstrip("/") + "/"
        is_virtual_dir = (
            any(item.startswith(pending_prefix) for item in self._pending_contents)
            or any(item == relative_path or item.startswith(pending_prefix) for item in self._pending_directories)
            or any(
                str(patch.get("file") or "").startswith(pending_prefix)
                for patch in self._pending_diffs.values()
            )
        )
        if (not path.exists() or not path.is_dir()) and not is_virtual_dir:
            return {"success": False, "error_code": "directory_not_found", "error": "Directory not found"}
        entries = []
        seen_names: set[str] = set()
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda item: item.name.lower()):
                if child.is_dir() and should_skip_dir(child.name, skip_hidden=False):
                    continue
                child_relative = child.relative_to(self.project_root).as_posix()
                if self._path_is_removed(child_relative):
                    continue
                entries.append({"name": child.name, "type": "directory" if child.is_dir() else "file"})
                seen_names.add(child.name.lower())

        relative_dir = relative_path
        relative_dir = "" if relative_dir == "." else relative_dir.rstrip("/") + "/"
        for pending_path in self._pending_contents:
            if relative_dir and not pending_path.startswith(relative_dir):
                continue
            remainder = pending_path[len(relative_dir):] if relative_dir else pending_path
            if not remainder:
                continue
            name, separator, _tail = remainder.partition("/")
            if name.lower() in seen_names:
                continue
            entries.append({
                "name": name,
                "type": "directory" if separator else "file",
                "staged": True,
            })
            seen_names.add(name.lower())

        for patch in self._pending_diffs.values():
            if patch.get("action") in {"mkdir", "rmdir", "delete"}:
                continue
            pending_path = str(patch.get("file") or "")
            if not pending_path or (relative_dir and not pending_path.startswith(relative_dir)):
                continue
            remainder = pending_path[len(relative_dir):] if relative_dir else pending_path
            name, separator, _tail = remainder.partition("/")
            if not name or name.lower() in seen_names:
                continue
            entries.append({
                "name": name,
                "type": "directory" if separator else "file",
                "staged": True,
            })
            seen_names.add(name.lower())

        for pending_directory in self._pending_directories:
            if relative_dir and not pending_directory.startswith(relative_dir):
                continue
            remainder = pending_directory[len(relative_dir):] if relative_dir else pending_directory
            if not remainder:
                continue
            name = remainder.split("/", 1)[0]
            if name.lower() in seen_names:
                continue
            entries.append({"name": name, "type": "directory", "staged": True})
            seen_names.add(name.lower())

        entries.sort(key=lambda item: str(item["name"]).lower())
        return {"success": True, "entries": entries[:200], "message": f"Listed {len(entries[:200])} item(s)"}

    def read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("path") or "")
        normalized_target = target.replace("\\", "/")
        if normalized_target.startswith("./"):
            normalized_target = normalized_target[2:]
        if self._path_is_removed(normalized_target):
            moved_to = self._pending_moves.get(normalized_target)
            return {
                "success": False,
                "error_code": "path_moved",
                "error": f"Path is staged to move: {normalized_target}",
                "destination": moved_to,
            }
        if normalized_target in self._pending_contents:
            return {
                "success": True,
                "content": self._pending_contents[normalized_target],
                "staged": True,
                "message": "Staged file read successfully",
            }
        path = self._resolve(target)
        if path is None:
            return {"success": False, "error_code": "blocked", "error": "Path is outside the active project"}
        if not path.exists() or not path.is_file():
            return {
                "success": False,
                "error_code": "file_not_found",
                "error": f"File not found: {target}",
                "suggested_matches": self._suggest_matches(target),
            }
        if path.stat().st_size > self.MAX_READ_BYTES:
            return {"success": False, "error_code": "file_too_large", "error": "File exceeds read limit"}
        content = path.read_text(encoding="utf-8", errors="replace")
        return {"success": True, "content": content, "message": "File read successfully"}

    def search_grep(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "")
        root = self._resolve(str(args.get("path") or "."))
        if not query:
            return {"success": False, "error_code": "invalid_args", "error": "Missing query"}
        if root is None:
            return {"success": False, "error_code": "blocked", "error": "Path is outside the active project"}
        results: list[dict[str, Any]] = []
        token = self.cancellation_token
        # Coarse cancellation check every 32 files. The full directory
        # walk is cheap on small projects, but a 100k-file project would
        # otherwise pin a thread for seconds after a cancel.
        check_every = 32
        files_scanned = 0
        for path in root.rglob("*"):
            if files_scanned % check_every == 0 and token is not None and token.is_cancelled():
                return {
                    "success": False,
                    "error_code": "agent_cancelled",
                    "error": "Search cancelled",
                    "partial_results": results,
                }
            files_scanned += 1
            if has_skipped_part(path.relative_to(self.project_root).parts):
                continue
            if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if query.lower() in line.lower():
                        results.append({
                            "file": path.relative_to(self.project_root).as_posix(),
                            "line": line_no,
                            "content": line.strip()[:240],
                        })
                        break
            except Exception:
                continue
            if len(results) >= 50:
                break
        return {"success": True, "results": results, "message": f"Found {len(results)} match(es)"}

    def create_directory(self, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("path") or "").strip()
        path = self._resolve(target)
        if path is None or path == self.project_root:
            return {"success": False, "error_code": "blocked", "error": "Directory must be inside the active project"}
        normalized = self._normalize_relative(path, self.project_root)
        if self._is_protected_path(normalized):
            return {"success": False, "error_code": "blocked", "error": "Protected project path cannot be reorganized"}
        if path.exists() and not path.is_dir():
            return {"success": False, "error_code": "path_conflict", "error": f"A file already exists at {normalized}"}
        if path.is_dir() or normalized in self._pending_directories:
            return {"success": True, "message": f"Directory already exists: {normalized}", "changed_file": normalized}

        patch = {
            "file": normalized,
            "action": "mkdir",
            "operation": "create_directory",
            "original_content": "",
            "diff_display": f"Create directory: {normalized}",
            "checkpoint_id": None,
        }
        self._pending_directories.add(normalized)
        self._pending_removed_paths.discard(normalized)
        self._pending_diffs[normalized] = patch
        self._dirty_pending_keys.add(normalized)
        self.modified_files.add(normalized)
        if not self.defer_diffs:
            self.on_diff(dict(patch))
        return {
            "success": True,
            "message": f"Staged directory creation: {normalized}",
            "changed_file": normalized,
            "action": "mkdir",
        }

    def _stage_remove_directory(self, path: Path) -> None:
        normalized = self._normalize_relative(path, self.project_root)
        key = f"rmdir:{normalized}"
        self._pending_removed_paths.add(normalized)
        self._pending_diffs[key] = {
            "file": normalized,
            "action": "rmdir",
            "operation": "remove_directory",
            "original_content": "",
            "diff_display": f"Remove empty directory after move: {normalized}",
            "checkpoint_id": None,
        }
        self._dirty_pending_keys.add(key)
        self.modified_files.add(normalized)
        if not self.defer_diffs:
            self.on_diff(dict(self._pending_diffs[key]))

    def _stage_move_file(self, source: Path, destination: Path) -> dict[str, Any]:
        source_relative = self._normalize_relative(source, self.project_root)
        destination_relative = self._normalize_relative(destination, self.project_root)
        if source_relative == destination_relative:
            return {"success": False, "error_code": "invalid_args", "error": "Source and destination are the same"}
        if self._is_protected_path(source_relative) or self._is_protected_path(destination_relative):
            return {"success": False, "error_code": "blocked", "error": "Protected project paths cannot be moved"}
        if self.safety.is_sensitive_file(source_relative) or self.safety.is_sensitive_file(destination_relative):
            return {"success": False, "error_code": "tool_sensitive_file", "error": "Sensitive file move blocked"}
        if destination.exists() or destination_relative in self._pending_contents:
            return {"success": False, "error_code": "path_conflict", "error": f"Destination already exists: {destination_relative}"}

        previous_patch = self._pending_diffs.get(source_relative)
        content: str | None
        if source_relative in self._pending_contents:
            content = self._pending_contents.pop(source_relative)
        elif source.is_file():
            if source.stat().st_size > self.MAX_READ_BYTES:
                return {"success": False, "error_code": "file_too_large", "error": "File exceeds move limit"}
            with source.open("rb") as handle:
                is_binary = b"\x00" in handle.read(1024)
            content = None if is_binary else source.read_text(encoding="utf-8", errors="replace")
        else:
            return {"success": False, "error_code": "file_not_found", "error": f"Source file not found: {source_relative}"}

        source_on_disk = source.is_file()
        original_source = source_relative
        if previous_patch and previous_patch.get("source"):
            original_source = str(previous_patch["source"]).replace("\\", "/")
            source_on_disk = bool((self.project_root / original_source).is_file())
        if previous_patch:
            self._pending_diffs.pop(source_relative, None)
            self._dirty_pending_keys.discard(source_relative)

        action = "move" if source_on_disk else "create"
        patch: dict[str, Any] = {
            "file": destination_relative,
            "source": original_source,
            "action": action,
            "operation": "move",
            "supersedes": [source_relative],
            "original_content": content or "",
            "diff_display": f"Move {source_relative} to {destination_relative}",
            "checkpoint_id": None,
        }
        if content is not None:
            patch["content"] = content
            self._pending_contents[destination_relative] = content
        else:
            patch["binary"] = True
        self._pending_removed_paths.add(source_relative)
        if original_source != source_relative:
            self._pending_removed_paths.add(original_source)
        self._pending_moves[source_relative] = destination_relative
        self._pending_moves[original_source] = destination_relative
        self._pending_diffs[destination_relative] = patch
        self._dirty_pending_keys.add(destination_relative)
        self.modified_files.discard(source_relative)
        self.modified_files.update({source_relative, destination_relative})
        if not self.defer_diffs:
            self.on_diff(dict(patch))
        return {
            "success": True,
            "message": f"Staged move: {source_relative} -> {destination_relative}",
            "changed_file": destination_relative,
            "source": source_relative,
            "action": "move",
        }

    def move_path(self, args: dict[str, Any]) -> dict[str, Any]:
        source_target = str(args.get("source") or "").strip()
        destination_target = str(args.get("destination") or "").strip()
        source = self._resolve(source_target)
        destination = self._resolve(destination_target)
        if source is None or destination is None or source == self.project_root:
            return {"success": False, "error_code": "blocked", "error": "Move must stay inside the active project"}
        source_relative = self._normalize_relative(source, self.project_root)
        destination_relative = self._normalize_relative(destination, self.project_root)
        if self._is_protected_path(source_relative) or self._is_protected_path(destination_relative):
            return {"success": False, "error_code": "blocked", "error": "Protected project paths cannot be moved"}

        if source_relative in self._pending_contents or source.is_file():
            return self._stage_move_file(source, destination)
        if not source.is_dir():
            return {"success": False, "error_code": "file_not_found", "error": f"Source path not found: {source_relative}"}
        if destination.exists() or destination_relative in self._pending_directories:
            return {"success": False, "error_code": "path_conflict", "error": f"Destination already exists: {destination_relative}"}

        files = [item for item in source.rglob("*") if item.is_file()]
        directories = [source, *[item for item in source.rglob("*") if item.is_dir()]]
        if len(files) > 200:
            return {"success": False, "error_code": "too_many_files", "error": "Directory move exceeds 200-file review limit"}

        for directory in directories:
            relative_tail = directory.relative_to(source)
            target_directory = destination / relative_tail
            result = self.create_directory({"path": self._normalize_relative(target_directory, self.project_root)})
            if not result.get("success"):
                return result
        moved = 0
        for source_file in files:
            target_file = destination / source_file.relative_to(source)
            result = self._stage_move_file(source_file, target_file)
            if not result.get("success"):
                return result
            moved += 1
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            self._stage_remove_directory(directory)
        return {
            "success": True,
            "message": f"Staged directory move with {moved} file(s): {source_relative} -> {destination_relative}",
            "changed_file": destination_relative,
            "source": source_relative,
            "action": "move",
            "files_moved": moved,
        }

    def write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("path") or "")
        content = args.get("content")
        if not isinstance(content, str):
            return {"success": False, "error_code": "invalid_args", "error": "Missing file content"}
        path = self._resolve(target)
        if path is None:
            return {"success": False, "error_code": "blocked", "error": "Path is outside the active project"}
        if self.safety.is_sensitive_file(target):
            return {"success": False, "error_code": "tool_sensitive_file", "error": "Sensitive file write blocked"}

        normalized_target = path.relative_to(self.project_root).as_posix()
        disk_original = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        existing_patch = self._pending_diffs.get(normalized_target)
        original_for_diff = (
            str(existing_patch.get("original_content") or "")
            if existing_patch else disk_original
        )
        diff = self.patch_gen.generate_diff(original_for_diff, content, normalized_target)
        action = (
            str(existing_patch.get("action"))
            if existing_patch and existing_patch.get("operation") == "move"
            else ("modify" if path.exists() else "create")
        )
        self.modified_files.add(normalized_target)
        self._pending_contents[normalized_target] = content
        patch = {
            "file": normalized_target,
            "action": action,
            "original_content": disk_original,
            "content": content,
            "diff": diff,
            "diff_display": diff,
            "checkpoint_id": None,
        }
        if existing_patch and existing_patch.get("operation") == "move":
            patch.update({
                "source": existing_patch.get("source"),
                "operation": "move",
                "supersedes": existing_patch.get("supersedes", []),
            })
        self._pending_diffs[normalized_target] = patch
        self._dirty_pending_keys.add(normalized_target)
        if not self.defer_diffs:
            self.on_diff(patch)
        return {
            "success": True,
            "message": f"Staged patch for {normalized_target}",
            "changed_file": normalized_target,
            "action": action,
            "staged_files": list(self._pending_diffs),
        }

    def flush_pending_diffs(self) -> list[dict[str, Any]]:
        """Emit the final version of every staged patch exactly once."""
        patches = [
            self._pending_diffs[key]
            for key in self._pending_diffs
            if key in self._dirty_pending_keys
        ]
        if self.defer_diffs:
            for patch in patches:
                self.on_diff(dict(patch))
        return patches

    @property
    def pending_files(self) -> tuple[str, ...]:
        return tuple(self._pending_diffs)

    @property
    def pending_contents(self) -> dict[str, str]:
        return dict(self._pending_contents)

    def run_command(
        self,
        args: dict[str, Any],
        *,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> dict[str, Any]:
        """Run a shell command inside the project root.

        Cancellation-aware: uses ``Popen`` + a poll loop so the subprocess
        can be killed mid-run when the active ``CancellationToken`` is
        flipped. The poll interval is small (200ms) so the user gets a
        snappy stop button even when a long test suite is running.
        """
        command = str(args.get("command") or "")
        if not command:
            return {"success": False, "error_code": "invalid_args", "error": "Missing command"}
        if self._pending_diffs:
            return {
                "success": False,
                "error_code": "approval_required",
                "error": "Changes are staged for review and are not on disk yet. Apply the patchset before running validation.",
                "staged_files": list(self._pending_diffs),
            }
        if self.safety.is_command_blocked(command):
            return {"success": False, "error_code": "tool_command_blocked", "error": "Blocked dangerous command"}
        token = cancellation_token if cancellation_token is not None else self.cancellation_token

        timeout = float(args.get("timeout", self.DEFAULT_COMMAND_TIMEOUT))
        poll_interval = 0.2
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(self.project_root),
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            return {"success": False, "error_code": "tool_command_failed", "error": str(exc)}

        deadline = time.monotonic() + timeout
        cancelled = False
        while True:
            if token is not None and token.is_cancelled():
                cancelled = True
                try:
                    proc.kill()
                except Exception:
                    pass
                break
            if proc.poll() is not None:
                break
            if time.monotonic() > deadline:
                try:
                    proc.kill()
                except Exception:
                    pass
                return {
                    "success": False,
                    "error_code": "tool_timeout",
                    "error": f"Command exceeded {timeout:.0f}s timeout",
                    "timeout": timeout,
                }
            time.sleep(poll_interval)

        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()

        if cancelled:
            return {
                "success": False,
                "error_code": "agent_cancelled",
                "error": "Command cancelled",
                "stdout": stdout[-8000:] if stdout else "",
                "stderr": stderr[-8000:] if stderr else "",
                "exit_code": proc.returncode,
            }

        return {
            "success": proc.returncode == 0,
            "stdout": stdout[-8000:] if stdout else "",
            "stderr": stderr[-8000:] if stderr else "",
            "exit_code": proc.returncode,
            "message": f"Command exited with code {proc.returncode}",
        }

    def load_skill(self, args: dict[str, Any]) -> dict[str, Any]:
        skill_id = str(args.get("id") or "").strip()
        record = get_skill_body(skill_id) if skill_id else None
        if record is None:
            return {"success": False, "error_code": "skill_not_found", "error": f"Unknown skill: {skill_id}"}
        body = (record.get("body") or "")[:12000]
        return {"success": True, "skill": {**record, "body": body}, "message": "Skill loaded"}

    def summarize_result(self, result: dict[str, Any]) -> str:
        return self._summary(result)



