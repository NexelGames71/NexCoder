"""Bridge — QWebChannel IPC bridge between Python backend and React frontend."""

import json
import os
import logging
import tempfile
from typing import Any, Optional

from PySide6.QtCore import QObject, Slot, Signal

from nexcoder.agent.errors import ErrorEnvelope, envelope_from_exception

logger = logging.getLogger(__name__)


def slot_error_response(
    exc: BaseException,
    *,
    code: Optional[str] = None,
    category: Optional[str] = None,
    retryable: Optional[bool] = None,
    details: Optional[dict[str, Any]] = None,
    include_traceback: bool = False,
) -> str:
    """Return a JSON string for a failed @Slot call.

    The shape is::

        {
            "success": false,
            "error": "<human-readable message>",
            "error_envelope": {
                "code": "tool_path_blocked",
                "message": "...",
                "category": "safety",
                "details": {...},
                "retryable": false,
                "traceback": "..."   # only when include_traceback=True
            }
        }

    The legacy ``success`` / ``error`` keys are preserved for backwards
    compatibility with the existing frontend. New code should read
    ``error_envelope`` and branch on ``code`` / ``category``.
    """
    envelope = ErrorEnvelope.from_exception(
        exc,
        code=code,
        category=category,
        retryable=retryable,
        details=details,
        include_traceback=include_traceback,
    )
    return json.dumps({
        "success": False,
        "error": envelope.message,
        "error_envelope": envelope.to_dict(),
    })


class Bridge(QObject):
    """Master IPC bridge exposed to JavaScript via QWebChannel.

    All @Slot methods are callable from the React frontend.
    Signals push data from Python → JavaScript.
    """

    # ── Signals (Python → JavaScript) ─────────────────────────────────
    file_tree_updated = Signal(str)         # JSON file tree
    file_changed = Signal(str)              # JSON {path, content}
    terminal_output = Signal(str, str)      # session_id, data
    terminal_exited = Signal(str, int)      # session_id, exit_code
    agent_stream = Signal(str)              # streaming text chunk
    agent_status = Signal(str)              # JSON status update
    agent_diff = Signal(str)                # JSON diff for approval
    agent_complete = Signal(str)            # JSON completion result
    git_updated = Signal(str)               # JSON git status
    project_opened = Signal(str)            # JSON project info
    search_results = Signal(str)            # JSON search results

    def __init__(self, main_window: Any = None) -> None:
        super().__init__()
        self._main_window = main_window

        # Initialize IPC handlers
        from nexcoder.ipc.filesystem import FileSystemHandler
        from nexcoder.ipc.terminal import TerminalHandler
        from nexcoder.ipc.git_ops import GitHandler
        from nexcoder.ipc.dialogs import DialogHandler
        from nexcoder.agent.runtime import AgentRuntime
        from nexcoder.services.project_manager import ProjectManager
        from nexcoder.services.appwrite_client import AppwriteClient

        self._fs = FileSystemHandler()
        self._terminal = TerminalHandler()
        self._git = GitHandler()
        self._dialogs = DialogHandler(main_window)
        self._agent = AgentRuntime()
        self._project = ProjectManager()
        self._appwrite = AppwriteClient()

        # Connect terminal output signal
        self._terminal.output_received.connect(self.terminal_output.emit)
        self._terminal.process_exited.connect(self.terminal_exited.emit)

        # Connect agent signals
        self._agent.stream_chunk.connect(self.agent_stream.emit)
        self._agent.status_update.connect(self.agent_status.emit)
        self._agent.diff_ready.connect(self.agent_diff.emit)
        self._agent.completed.connect(self.agent_complete.emit)

        # Connect filesystem watcher
        self._fs.tree_changed.connect(self.on_fs_changed)

        self._current_project_path: str | None = None

    def _require_project_path(self) -> str:
        if not self._current_project_path:
            raise ValueError("No project open")
        return os.path.abspath(self._current_project_path)

    def _resolve_project_path(self, path: str = "") -> str:
        root = self._require_project_path()
        if not path:
            target = root
        elif os.path.isabs(path):
            target = os.path.abspath(path)
        else:
            target = os.path.abspath(os.path.join(root, path))
        try:
            common = os.path.commonpath([root, target])
        except ValueError as exc:
            raise PermissionError("Path is outside the active project") from exc
        if common != root:
            raise PermissionError("Path is outside the active project")
        return target

    # ── Filesystem ────────────────────────────────────────────────────

    @Slot(result=str)
    def open_folder_dialog(self) -> str:
        """Open native folder picker and load the project."""
        folder = self._dialogs.open_folder()
        if folder:
            self._open_project(folder)
        return folder or ""

    @Slot(str, result=str)
    def open_project(self, path: str) -> str:
        """Open a project at the given path."""
        return self._open_project(path)

    def _open_project(self, path: str) -> str:
        """Internal: load a project directory."""
        try:
            info = self._project.open_project(path)
            self._current_project_path = path
            self._fs.set_trusted_root(path)

            if self._main_window:
                self._main_window.set_project_name(info.get("name", os.path.basename(path)))

            # Start file watching
            self._fs.watch_directory(path)

            # Get initial file tree
            tree = self._fs.get_file_tree(path)

            result = json.dumps({
                "success": True,
                "project": info,
                "tree": tree,
            })
            self.project_opened.emit(result)
            return result
        except Exception as e:
            logger.error(f"Failed to open project: {e}")
            return slot_error_response(e)

    def on_fs_changed(self, path: str) -> None:
        """Called when any file/directory is modified. Broadcasts updated tree to frontend."""
        if self._current_project_path:
            try:
                tree = self._fs.get_file_tree(self._current_project_path)
                self.file_tree_updated.emit(json.dumps(tree))
            except Exception as e:
                logger.error(f"Error updating file tree after change: {e}")

    @Slot(str, result=str)
    def read_file(self, path: str) -> str:
        """Read file content."""
        try:
            self._require_project_path()
            content = self._fs.read_file(path)
            return json.dumps({"success": True, "content": content, "path": path})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def write_file(self, path: str, content: str) -> str:
        """Write content to file (atomic write)."""
        try:
            self._require_project_path()
            self._fs.write_file(path, content)
            return json.dumps({"success": True, "path": path})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def save_file_as(self, suggested_path: str, content: str) -> str:
        """Save content to a user-selected path using a native save dialog."""
        try:
            project_root = self._require_project_path()
            initial_path = suggested_path or project_root
            if initial_path and not os.path.isabs(initial_path):
                initial_path = os.path.join(project_root, initial_path)
            selected = self._dialogs.save_file(
                "Save As",
                "All Files (*)",
                os.path.abspath(initial_path),
            )
            if not selected:
                return json.dumps({"success": False, "cancelled": True})
            selected = os.path.abspath(selected)
            self._write_absolute_file(selected, content)
            return json.dumps({"success": True, "path": selected.replace("\\", "/")})
        except Exception as e:
            return slot_error_response(e)

    def _write_absolute_file(self, path: str, content: str) -> None:
        """Atomic write for native-dialog-selected Save As targets."""
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=parent, prefix=".nexcoder_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    @Slot(str, result=str)
    def delete_file(self, path: str) -> str:
        """Delete a file or directory after confirmation."""
        name = os.path.basename(path)
        if not self._dialogs.confirm(f"Delete '{name}'?", "This action cannot be undone."):
            return slot_error_response(
                RuntimeError("Cancelled by user"),
                code="tool_invalid_args",
                category="user_recoverable",
                details={"path": path, "reason": "user_cancelled"},
            )
        try:
            self._require_project_path()
            self._fs.delete_path(path)
            return json.dumps({"success": True, "path": path})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def rename_file(self, old_path: str, new_path: str) -> str:
        """Rename / move a file."""
        try:
            self._require_project_path()
            self._fs.rename_path(old_path, new_path)
            return json.dumps({"success": True, "oldPath": old_path, "newPath": new_path})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def create_directory(self, path: str) -> str:
        """Create a directory (mkdir -p)."""
        try:
            self._require_project_path()
            self._fs.create_directory(path)
            return json.dumps({"success": True, "path": path})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def create_file(self, path: str, content: str = "") -> str:
        """Create a new file with optional content."""
        try:
            self._require_project_path()
            self._fs.write_file(path, content)
            return json.dumps({"success": True, "path": path})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def get_file_tree(self, root: str) -> str:
        """Get the full file tree as JSON."""
        try:
            tree = self._fs.get_file_tree(self._resolve_project_path(root))
            return json.dumps({"success": True, "tree": tree})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def search_files(self, query: str, root: str = "") -> str:
        """Search for text across project files."""
        try:
            search_root = self._resolve_project_path(root)
            results = self._fs.search_files(query, search_root)
            result_json = json.dumps({"success": True, "results": results})
            self.search_results.emit(result_json)
            return result_json
        except Exception as e:
            return slot_error_response(e)

    # ── Terminal ──────────────────────────────────────────────────────

    @Slot(str, result=str)
    def spawn_terminal(self, cwd: str = "") -> str:
        """Spawn a new PTY terminal session."""
        try:
            working_dir = self._resolve_project_path(cwd)
            session_id = self._terminal.spawn(working_dir)
            return json.dumps({"success": True, "sessionId": session_id})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str)
    def write_terminal(self, session_id: str, data: str) -> None:
        """Write data to a terminal session."""
        self._terminal.write(session_id, data)

    @Slot(str, int, int)
    def resize_terminal(self, session_id: str, cols: int, rows: int) -> None:
        """Resize a terminal session."""
        self._terminal.resize(session_id, cols, rows)

    @Slot(str)
    def kill_terminal(self, session_id: str) -> None:
        """Kill a terminal session."""
        self._terminal.kill(session_id)

    # ── Git ───────────────────────────────────────────────────────────

    @Slot(str, result=str)
    def git_status(self, root: str = "") -> str:
        """Get git status for the project."""
        repo_root = root or self._current_project_path or ""
        try:
            status = self._git.status(repo_root)
            result = json.dumps({"success": True, "status": status})
            self.git_updated.emit(result)
            return result
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def git_diff(self, root: str = "") -> str:
        """Get git diff."""
        repo_root = root or self._current_project_path or ""
        try:
            diff = self._git.diff(repo_root)
            return json.dumps({"success": True, "diff": diff})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def git_stage(self, root: str, files_json: str) -> str:
        """Stage files for commit."""
        repo_root = root or self._current_project_path or ""
        try:
            files = json.loads(files_json)
            self._git.stage(repo_root, files)
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def git_commit(self, root: str, message: str) -> str:
        """Create a commit."""
        repo_root = root or self._current_project_path or ""
        try:
            commit_hash = self._git.commit(repo_root, message)
            return json.dumps({"success": True, "hash": commit_hash})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def git_branch(self, root: str = "") -> str:
        """Get the current git branch."""
        repo_root = root or self._current_project_path or ""
        try:
            branch = self._git.branch(repo_root)
            return json.dumps({"success": True, "branch": branch})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, int, result=str)
    def git_log(self, root: str = "", count: int = 20) -> str:
        """Get recent git commits."""
        repo_root = root or self._current_project_path or ""
        try:
            commits = self._git.log(repo_root, count)
            return json.dumps({"success": True, "commits": commits})
        except Exception as e:
            return slot_error_response(e)

    # ── Agent / AI ────────────────────────────────────────────────────

    @Slot(str, str, result=str)
    def agent_ask(self, prompt: str, context_json: str) -> str:
        """AI Ask mode — read-only questions."""
        try:
            context = json.loads(context_json) if context_json else {}
            context["project_path"] = self._current_project_path
            context["prompt"] = prompt
            # Default ask tasks to the "question" task type so the loop
            # produces a structured final_answer even when the runtime
            # did not classify the prompt itself.
            context.setdefault("task_type", "question")
            self._agent.run_mode("ask", prompt, context)
            return json.dumps({"success": True, "mode": "ask"})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def agent_edit(self, prompt: str, context_json: str) -> str:
        """AI Edit mode — controlled single-file edits."""
        try:
            context = json.loads(context_json) if context_json else {}
            context["project_path"] = self._current_project_path
            context["prompt"] = prompt
            context.setdefault("task_type", "edit")
            self._agent.run_mode("edit", prompt, context)
            return json.dumps({"success": True, "mode": "edit"})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def agent_run(self, prompt: str, context_json: str) -> str:
        """AI Agent mode — multi-step autonomous."""
        try:
            context = json.loads(context_json) if context_json else {}
            context["project_path"] = self._current_project_path
            context["prompt"] = prompt
            lower_prompt = prompt.lower()
            scan_requested = any(
                phrase in lower_prompt
                for phrase in (
                    "scan the codebase",
                    "scan codebase",
                    "scan the project",
                    "scan through",
                    "codebase scan",
                    "project scan",
                    "create a codebase map",
                    "understand the codebase",
                    "understand the project",
                )
            )
            if scan_requested:
                context["project_path"] = self._require_project_path()
                context["task_type"] = "scan"
                self._agent.start_task("scan", "Scan the project and create a codebase map.", context)
                return json.dumps({"success": True, "mode": "scan"})
            # Let the runtime pick the task type from the prompt; the
            # default is "implement" but questions and scans get
            # re-classified automatically.
            context.setdefault("task_type", "implement")
            self._agent.run_mode("agent", prompt, context)
            return json.dumps({"success": True, "mode": "agent"})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_scan(self, context_json: str = "") -> str:
        """Structured scan task; bypasses normal chat completions."""
        try:
            context = json.loads(context_json) if context_json else {}
            context["project_path"] = self._require_project_path()
            prompt = "Scan the project and create a codebase map."
            context["task_type"] = "scan"
            self._agent.start_task("scan", prompt, context)
            return json.dumps({"success": True, "mode": "scan"})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def agent_debug(self, prompt: str, context_json: str) -> str:
        """AI Debug mode — error-focused fixes."""
        try:
            context = json.loads(context_json) if context_json else {}
            context["project_path"] = self._current_project_path
            context["prompt"] = prompt
            context.setdefault("task_type", "debug")
            self._agent.run_mode("debug", prompt, context)
            return json.dumps({"success": True, "mode": "debug"})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def agent_review(self, prompt: str, context_json: str) -> str:
        """AI Review mode — code audit."""
        try:
            context = json.loads(context_json) if context_json else {}
            context["project_path"] = self._current_project_path
            context["prompt"] = prompt
            context.setdefault("task_type", "review")
            self._agent.run_mode("review", prompt, context)
            return json.dumps({"success": True, "mode": "review"})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_approve_diff(self, diff_id: str) -> str:
        """Approve a pending diff from the agent."""
        try:
            self._agent.approve_diff(diff_id, self._require_project_path())
            try:
                tree = self._fs.get_file_tree(self._require_project_path())
                self.file_tree_updated.emit(json.dumps(tree))
            except Exception:
                logger.debug("Could not refresh file tree after diff apply", exc_info=True)
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_approve_patchset(self, diff_ids_json: str) -> str:
        """Apply all selected agent changes atomically and verify the writes."""
        try:
            diff_ids = json.loads(diff_ids_json) if diff_ids_json else []
            if not isinstance(diff_ids, list) or not all(isinstance(item, str) for item in diff_ids):
                raise ValueError("Patchset ids must be a JSON list of strings")
            result = self._agent.approve_patchset(diff_ids, self._require_project_path())
            try:
                tree = self._fs.get_file_tree(self._require_project_path())
                self.file_tree_updated.emit(json.dumps(tree))
            except Exception:
                logger.debug("Could not refresh file tree after patchset apply", exc_info=True)
            return json.dumps({"success": True, **result})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_apply_patchset(self, patches_json: str) -> str:
        """Apply a JSON-serialized list of patches atomically (from UI approval).

        Each patch should be in the same format produced by PatchGenerator.parse_response.
        """
        try:
            patches = json.loads(patches_json)
            from nexcoder.agent.patch_generator import PatchGenerator
            from nexcoder.services.checkpoint import CheckpointManager

            project_root = self._require_project_path()
            files = [p.get("file") for p in patches if p.get("file")]
            cp = CheckpointManager(project_root)
            checkpoint_id = cp.create([os.path.join(project_root, f) for f in files], label="ui-patchset")

            patch_gen = PatchGenerator(project_root)
            patch_gen.apply_patchset(patches)

            return json.dumps({"success": True, "checkpoint_id": checkpoint_id})
        except Exception as e:
            logger.error(f"Failed to apply patchset from UI: {e}")
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_reject_diff(self, diff_id: str) -> str:
        """Reject a pending diff from the agent."""
        try:
            self._agent.reject_diff(diff_id, self._require_project_path())
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def update_ai_settings(self, endpoint: str, model: str) -> str:
        """Update AI model connector settings from the UI."""
        try:
            self._agent.set_ai_settings(endpoint, model)
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def agent_get_memory(self) -> str:
        """Return the agent memory for the current project as JSON."""
        try:
            project_root = self._require_project_path()
            mem = self._agent.get_memory(project_root)
            return json.dumps({"success": True, "memory": mem._data})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def agent_set_memory(self, key: str, value_json: str) -> str:
        """Set a memory key to a JSON value for the current project."""
        try:
            project_root = self._require_project_path()
            mem = self._agent.get_memory(project_root)
            value = json.loads(value_json)
            mem.set(key, value)
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def get_skills(self) -> str:
        """Return list of available agent skills with metadata, grouped by category."""
        try:
            from nexcoder.agent.skills_registry import get_skills_grouped
            return json.dumps({"success": True, **get_skills_grouped()})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def get_skill_body(self, skill_id: str) -> str:
        """Return the SKILL.md body content for a specific skill id."""
        try:
            from nexcoder.agent.skills_registry import get_skill_body
            record = get_skill_body(skill_id)
            if record is None:
                return slot_error_response(
                    LookupError(f"Unknown skill: {skill_id}"),
                    code="tool_skill_not_found",
                    category="user_recoverable",
                    details={"skill_id": skill_id},
                )
            return json.dumps({"success": True, **record})
        except Exception as e:
            return slot_error_response(e)

    # ── Appwrite ──────────────────────────────────────────────────────

    @Slot(str, str, result=str)
    def appwrite_login(self, email: str, password: str) -> str:
        """Login to Appwrite with email/password."""
        try:
            return json.dumps(self._appwrite.login(email, password))
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, str, result=str)
    def appwrite_register(self, email: str, password: str, name: str = "") -> str:
        """Register an Appwrite account."""
        try:
            return json.dumps(self._appwrite.register(email, password, name))
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def appwrite_logout(self) -> str:
        """Logout from Appwrite."""
        try:
            return json.dumps(self._appwrite.logout())
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def save_to_appwrite(self, collection: str, data_json: str) -> str:
        """Save data to an Appwrite collection."""
        try:
            data = json.loads(data_json)
            doc_id = self._appwrite.create_document(collection, data)
            return json.dumps({"success": True, "documentId": doc_id})
        except Exception as e:
            return slot_error_response(e)

    # ── Utility (called from native menus) ────────────────────────────

    def trigger_save(self) -> None:
        """Trigger save in the React frontend."""
        if self._main_window:
            self._main_window._run_js("window.nexcoder?.saveActiveFile()")

    def trigger_save_all(self) -> None:
        """Trigger save all in the React frontend."""
        if self._main_window:
            self._main_window._run_js("window.nexcoder?.saveAllFiles()")

    def trigger_save_as(self) -> None:
        """Trigger Save As in the React frontend."""
        if self._main_window:
            self._main_window._run_js("window.nexcoder?.saveActiveFileAs()")

    @Slot(result=str)
    def get_recent_projects(self) -> str:
        """Get list of recent projects."""
        try:
            projects = self._project.get_recent_projects()
            return json.dumps({"success": True, "projects": projects})
        except Exception as e:
            return slot_error_response(e)

    # ── Cancellation ──────────────────────────────────────────────────

    @Slot(result=str)
    def cancel_agent(self) -> str:
        """Request cooperative cancellation of the currently-running agent task.

        Returns ``{"success": true, "cancelled": true}`` if a run was
        active and the cancel signal was sent, or
        ``{"success": true, "cancelled": false}`` if no run is in flight.

        The cancellation is cooperative: the worker checks the token at
        the next safe checkpoint (between turns, between tool calls,
        during long-running commands) and exits cleanly with a
        ``agent_complete`` payload carrying
        ``error_kind == "agent_cancelled"``.
        """
        try:
            cancelled = self._agent.cancel_active_run("cancelled by user")
            return json.dumps({"success": True, "cancelled": cancelled})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def agent_is_active(self) -> str:
        """True while a run is in progress. UI uses this to gate the cancel button."""
        try:
            return json.dumps({"success": True, "active": self._agent.is_active()})
        except Exception as e:
            return slot_error_response(e)

    # ── Sessions (conversation persistence) ──────────────────────────

    @Slot(str, result=str)
    def list_sessions(self, project_path: str = "") -> str:
        """Return the metadata for all sessions in the project, newest-first.

        ``project_path`` may be empty — the bridge falls back to the
        currently-open project. Missing / unreadable projects return
        an empty list rather than an error so the UI can degrade
        gracefully on a fresh install.
        """
        try:
            root = project_path or self._current_project_path
            if not root:
                return json.dumps({"success": True, "sessions": []})
            store = self._agent.get_session_store(os.path.abspath(root))
            sessions = [m.to_dict() for m in store.list_sessions()]
            return json.dumps({"success": True, "sessions": sessions})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def load_session(self, project_path: str, session_id: str) -> str:
        """Return the metadata + full message list for a session."""
        try:
            root = project_path or self._current_project_path
            if not root:
                return slot_error_response(
                    RuntimeError("No project open"),
                    code="no_active_project",
                )
            store = self._agent.get_session_store(os.path.abspath(root))
            meta, messages = store.load_session(session_id)
            return json.dumps({
                "success": True,
                "metadata": meta.to_dict(),
                "messages": [m.to_dict() for m in messages],
            })
        except FileNotFoundError:
            return slot_error_response(
                LookupError(f"Session not found: {session_id}"),
                code="session_not_found",
                category="user_recoverable",
                details={"session_id": session_id},
            )
        except ValueError as exc:
            return slot_error_response(
                exc,
                code="session_corrupt",
                category="system",
                retryable=True,
            )
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def delete_session(self, project_path: str, session_id: str) -> str:
        """Delete a session and remove it from the index."""
        try:
            root = project_path or self._current_project_path
            if not root:
                return slot_error_response(
                    RuntimeError("No project open"),
                    code="no_active_project",
                )
            store = self._agent.get_session_store(os.path.abspath(root))
            removed = store.delete_session(session_id)
            return json.dumps({"success": True, "removed": removed})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, str, result=str)
    def archive_session(self, project_path: str, session_id: str, archived_json: str = "true") -> str:
        """Archive or unarchive a session without deleting its files."""
        try:
            root = project_path or self._current_project_path
            if not root:
                return slot_error_response(
                    RuntimeError("No project open"),
                    code="no_active_project",
                )
            archived = json.loads(archived_json) if archived_json else True
            store = self._agent.get_session_store(os.path.abspath(root))
            meta = store.archive_session(session_id, bool(archived))
            return json.dumps({"success": True, "metadata": meta.to_dict()})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, str, result=str)
    def create_session(self, project_path: str, title: str = "New session", mode: str = "ask") -> str:
        """Create an empty chat session and return its metadata."""
        try:
            root = project_path or self._current_project_path
            if not root:
                return slot_error_response(
                    RuntimeError("No project open"),
                    code="no_active_project",
                )
            store = self._agent.get_session_store(os.path.abspath(root))
            meta = store.create_session(title=title or "New session", mode=mode or "ask")
            return json.dumps({"success": True, "metadata": meta.to_dict()})
        except Exception as e:
            return slot_error_response(e)

    # ── Redaction (UI-side pre-check) ────────────────────────────────

    @Slot(str, result=str)
    def redact_text(self, text: str) -> str:
        """Return the redacted version of *text* plus a redaction report.

        The UI can call this when the user pastes text that might
        contain secrets (e.g. an env file, a config dump) and the
        redaction layer should run **before** the prompt is sent. The
        result shape is::

            {
                "success": true,
                "text": "...sanitised...",
                "count": 3,
                "labels": ["openai_api_key", "email", "github_pat"]
            }

        Note that the agent runtime already redacts both the user
        prompt and streamed chunks automatically. This slot is for
        cases where the UI wants to surface a "redacted N items"
        affordance to the user, or apply the same redaction to text
        it displays (e.g. pasted logs).
        """
        try:
            result = self._agent._redactor.redact(text or "")
            return json.dumps({
                "success": True,
                "text": result.text,
                "count": result.count,
                "labels": sorted(set(result.labels)),
            })
        except Exception as e:
            return slot_error_response(e)
