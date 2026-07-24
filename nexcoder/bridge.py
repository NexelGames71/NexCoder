"""Bridge — QWebChannel IPC bridge between Python backend and React frontend."""

import json
import os
import logging
import re
import shutil
import base64
import secrets
import subprocess
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from typing import Any, Optional

from PySide6.QtCore import QObject, Qt, Slot, Signal, QStandardPaths

from nexcoder.agent.errors import ErrorEnvelope, envelope_from_exception
from nexcoder.agent.image_inputs import (
    attachment_metadata, validate_image_attachments,
)

logger = logging.getLogger(__name__)

MAX_PREVIEW_BYTES = 100 * 1024 * 1024
APP_STATE_FILE = "state.json"
WEB_AUTH_SESSION_FILE = "web-session.dat"


def _nexcoder_app_data_dir() -> Path:
    """Return NexCoder's user-scoped desktop data directory."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "NexCoder"
        return Path.home() / "AppData" / "Roaming" / "NexCoder"

    qt_location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation)
    if qt_location:
        return Path(qt_location)
    return Path.home() / ".config" / "NexCoder"


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


class _LspSignalHub(QObject):
    """Thread-safe funnel for LSP results produced on worker threads."""

    response = Signal(str)
    diagnostics = Signal(str)


class _CloneSignalHub(QObject):
    """Thread-safe funnel for clone results produced off the UI thread."""

    completed = Signal(str)


class Bridge(QObject):
    """Master IPC bridge exposed to JavaScript via QWebChannel.

    All @Slot methods are callable from the React frontend.
    Signals push data from Python → JavaScript.
    """

    # ── Signals (Python → JavaScript) ─────────────────────────────────
    file_tree_updated = Signal(str)         # JSON file tree
    file_changed = Signal(str)              # JSON {path, content}
    terminal_output = Signal(str, str, int) # session_id, data, output sequence
    terminal_exited = Signal(str, int)      # session_id, exit_code
    agent_stream = Signal(str)              # streaming text chunk
    agent_status = Signal(str)              # JSON status update
    agent_diff = Signal(str)                # JSON diff for approval
    agent_complete = Signal(str)            # JSON completion result
    agent_event = Signal(str)               # JSON AgentEvent (v2 engine)
    plan_updated = Signal(str)              # JSON persisted ImplementationPlan
    mesh_event = Signal(str)                # JSON mesh event (Agent Mesh)
    lsp_response = Signal(str)              # JSON {id, kind, result|error}
    lsp_diagnostics = Signal(str)           # JSON {path, diagnostics}
    clone_completed = Signal(str)           # JSON {success, clone_id, project?}
    web_auth_completed = Signal(str)        # JSON {success, user?}
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
        from nexcoder.services.project_manager import ProjectManager
        from nexcoder.services.appwrite_client import AppwriteClient

        self._fs = FileSystemHandler()
        self._terminal = TerminalHandler()
        self._git = GitHandler()
        self._dialogs = DialogHandler(main_window)
        self._project = ProjectManager()
        self._appwrite = AppwriteClient()

        # Connect terminal output signal
        self._terminal.output_received.connect(self.terminal_output.emit)
        self._terminal.process_exited.connect(self.terminal_exited.emit)

        # Connect filesystem watcher
        self._fs.tree_changed.connect(self.on_fs_changed)

        self._current_project_path: str | None = None
        self._agent_v2_worker = None
        self._agent_v2_gate = None
        self._mesh_worker = None
        self._mesh_gate = None
        self._session_stores: dict[str, Any] = {}
        self._plan_managers: dict[str, Any] = {}
        self._active_plan_context: dict[str, Any] = {}
        self._active_plan_execution = False
        self._redactor = None
        self._dialog_file_allowlist: set[str] = set()
        self._web_auth_server: ThreadingHTTPServer | None = None
        self._web_auth_state: str | None = None

        # LSP: worker threads publish through this hub; queued
        # connections hop results onto the main thread, because
        # QWebChannel silently drops signals emitted off it.
        self._lsp_hub = _LspSignalHub()
        self._lsp_hub.response.connect(
            self._relay_lsp_response, Qt.ConnectionType.QueuedConnection)
        self._lsp_hub.diagnostics.connect(
            self._relay_lsp_diagnostics, Qt.ConnectionType.QueuedConnection)
        self._lsp_manager = None
        self._lsp_pool = None
        self._clone_hub = _CloneSignalHub()
        self._clone_hub.completed.connect(
            self._on_clone_completed, Qt.ConnectionType.QueuedConnection)
        self._clone_jobs: dict[str, dict[str, Any]] = {}

    def _session_store(self, project_root: str):
        """Per-project chat session store (cached)."""
        from nexcoder.agent.session import AgentSessionStore
        key = os.path.abspath(project_root)
        store = self._session_stores.get(key)
        if store is None:
            store = AgentSessionStore(key)
            self._session_stores[key] = store
        return store

    def _plan_manager(self, project_root: str | None = None):
        from nexcoder.agent.planning.manager import PlanManager
        root = os.path.abspath(project_root or self._require_project_path())
        manager = self._plan_managers.get(root)
        if manager is None:
            manager = PlanManager(root)
            self._plan_managers[root] = manager
        return manager

    def _require_project_path(self) -> str:
        if not self._current_project_path:
            raise ValueError("No project open")
        return os.path.abspath(self._current_project_path)

    def _app_state_path(self) -> Path:
        return _nexcoder_app_data_dir() / APP_STATE_FILE

    def _web_auth_session_path(self) -> Path:
        return _nexcoder_app_data_dir() / WEB_AUTH_SESSION_FILE

    def _read_app_state(self) -> dict[str, Any]:
        path = self._app_state_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_app_state(self, state: dict[str, Any]) -> None:
        path = self._app_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    def _protect_auth_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if os.name != "nt":
            return {
                "version": 1,
                "storage": "base64",
                "payload": base64.b64encode(raw).decode("ascii"),
            }

        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
            ]

        data_buffer = ctypes.create_string_buffer(raw)
        blob_in = DATA_BLOB(len(raw), ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        blob_out = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            "NexCoder Web Session",
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        ):
            raise OSError("Windows could not protect the NexCoder web session")
        try:
            encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
        return {
            "version": 1,
            "storage": "dpapi",
            "payload": base64.b64encode(encrypted).decode("ascii"),
        }

    def _unprotect_auth_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = record.get("payload")
        if not isinstance(payload, str):
            raise ValueError("Stored web auth session payload is invalid")
        encrypted = base64.b64decode(payload.encode("ascii"))

        if record.get("storage") == "base64" and os.name != "nt":
            decoded = encrypted.decode("utf-8")
            data = json.loads(decoded)
            return data if isinstance(data, dict) else {}

        if record.get("storage") != "dpapi" or os.name != "nt":
            raise ValueError("Stored web auth session is not readable on this platform")

        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
            ]

        data_buffer = ctypes.create_string_buffer(encrypted)
        blob_in = DATA_BLOB(len(encrypted), ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        blob_out = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        ):
            raise OSError("Windows could not read the NexCoder web session")
        try:
            decoded = ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(blob_out.pbData)
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}

    def _write_web_auth_session(self, session: dict[str, Any] | None) -> None:
        path = self._web_auth_session_path()
        if not session:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        if not isinstance(session, dict):
            raise ValueError("Web auth session must be an object")
        if not session.get("accessToken") or not session.get("refreshToken"):
            raise ValueError("Web auth session is missing token fields")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(
            json.dumps(self._protect_auth_payload(session), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _read_web_auth_session(self) -> dict[str, Any] | None:
        path = self._web_auth_session_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        session = self._unprotect_auth_payload(data)
        return session if session.get("accessToken") and session.get("refreshToken") else None

    def _session_status_payload(self) -> dict[str, Any]:
        session = self._read_web_auth_session()
        return {
            "success": True,
            "authenticated": bool(session),
            "expiresAt": session.get("expiresAt") if session else None,
            "tokenType": session.get("tokenType") if session else None,
        }

    def _migrate_legacy_web_session(self, state: dict[str, Any]) -> dict[str, Any]:
        legacy_session = state.get("web_session")
        if legacy_session is not None:
            self._write_web_auth_session(legacy_session if isinstance(legacy_session, dict) else None)
            state = dict(state)
            state.pop("web_session", None)
            self._write_app_state(state)
        return state

    @Slot(result=str)
    def app_state_get(self) -> str:
        """Read NexCoder desktop app state from the user's AppData folder."""
        try:
            state = self._migrate_legacy_web_session(self._read_app_state())
            return json.dumps({
                "success": True,
                "state": state,
                "path": str(self._app_state_path()),
            })
        except Exception as exc:
            return slot_error_response(exc)

    @Slot(str, result=str)
    def app_state_update(self, patch_json: str) -> str:
        """Merge desktop app state into AppData\\NexCoder\\state.json."""
        try:
            patch = json.loads(patch_json) if patch_json else {}
            if not isinstance(patch, dict):
                raise ValueError("App state patch must be a JSON object")
            if "web_session" in patch:
                legacy_session = patch.pop("web_session")
                self._write_web_auth_session(legacy_session if isinstance(legacy_session, dict) else None)
            state = self._read_app_state()
            state.pop("web_session", None)
            state.update(patch)
            self._write_app_state(state)
            return json.dumps({
                "success": True,
                "state": state,
                "path": str(self._app_state_path()),
            })
        except Exception as exc:
            return slot_error_response(exc)

    @Slot(result=str)
    def web_auth_session_status(self) -> str:
        """Return non-sensitive status for the stored NexCoder Web session."""
        try:
            return json.dumps(self._session_status_payload())
        except Exception as exc:
            return slot_error_response(exc)

    @Slot(result=str)
    def web_auth_clear(self) -> str:
        """Clear the stored NexCoder Web session."""
        try:
            self._write_web_auth_session(None)
            return json.dumps({"success": True})
        except Exception as exc:
            return slot_error_response(exc)

    @Slot(str, result=str)
    def app_shell_set_stage(self, stage: str) -> str:
        """Tell the native window whether the React UI is auth-gated or in the IDE."""
        try:
            normalized = stage if stage in {"auth", "ide"} else "auth"
            if self._main_window is not None and hasattr(self._main_window, "set_shell_stage"):
                self._main_window.set_shell_stage(normalized)
            return json.dumps({"success": True, "stage": normalized})
        except Exception as exc:
            return slot_error_response(exc)

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

    @Slot(result=str)
    def open_file_dialog(self) -> str:
        """Open native file picker."""
        file_path = self._dialogs.open_file()
        if file_path:
            self._dialog_file_allowlist.add(os.path.abspath(file_path))
        return file_path or ""

    @Slot(str, result=str)
    def select_folder_dialog(self, title: str = "Select Folder") -> str:
        """Open a native folder picker without changing the active project."""
        folder = self._dialogs.select_folder(title or "Select Folder")
        return folder or ""

    def _resolve_readable_file(self, path: str) -> tuple[str, bool]:
        """Resolve a file that is either inside the project or user-selected."""
        if not path:
            raise ValueError("Path is required")
        root = os.path.abspath(self._current_project_path) if self._current_project_path else None
        if os.path.isabs(path):
            target = os.path.abspath(path)
        elif root:
            target = os.path.abspath(os.path.join(root, path))
        else:
            target = os.path.abspath(path)

        if root:
            try:
                if os.path.commonpath([root, target]) == root:
                    return target, True
            except ValueError:
                pass

        if target in self._dialog_file_allowlist:
            return target, False
        raise PermissionError("Path is outside the active project")

    @Slot(str, result=str)
    def open_project(self, path: str) -> str:
        """Open a project at the given path."""
        return self._open_project(path)

    @Slot(str, str, str, result=str)
    def clone_repository(
        self,
        repository_url: str,
        destination_parent: str = "",
        directory_name: str = "",
    ) -> str:
        """Clone a git repository in the background, then open it as a project."""
        try:
            url = self._normalize_clone_url(repository_url)
            parent = self._normalize_clone_parent(destination_parent)
            name = self._derive_clone_directory_name(url, directory_name)
            target = os.path.abspath(os.path.join(parent, name))
            if os.path.commonpath([parent, target]) != parent:
                raise ValueError("Clone directory must stay inside the selected folder")
            if os.path.exists(target) and os.listdir(target):
                raise FileExistsError(f"Destination folder is not empty: {target}")
            git_exe = shutil.which("git")
            if not git_exe:
                raise RuntimeError("Git is not installed or is not available on PATH")

            clone_id = f"clone_{os.urandom(6).hex()}"
            self._clone_jobs[clone_id] = {
                "status": "running",
                "repository_url": url,
                "target": target,
            }
            thread = threading.Thread(
                target=self._run_clone_job,
                args=(clone_id, git_exe, url, target),
                daemon=True,
            )
            thread.start()
            return json.dumps({
                "success": True,
                "clone_id": clone_id,
                "target": target.replace("\\", "/"),
            })
        except Exception as e:
            return slot_error_response(e)

    def _normalize_clone_url(self, value: str) -> str:
        url = str(value or "").strip()
        if not url:
            raise ValueError("Repository URL is required")
        if any(ch.isspace() for ch in url):
            raise ValueError("Repository URL cannot contain spaces")
        parsed = urlparse(url)
        if parsed.scheme:
            if parsed.scheme.lower() not in {"https", "http", "ssh", "git", "file"}:
                raise ValueError("Unsupported repository URL scheme")
            if parsed.scheme.lower() != "file" and not parsed.netloc:
                raise ValueError("Repository URL is missing a host")
            return url
        if re.fullmatch(r"[\w.\-]+@[\w.\-]+:.+", url):
            return url
        raise ValueError("Use an HTTPS, SSH, git, file, or scp-style repository URL")

    def _normalize_clone_parent(self, value: str) -> str:
        raw = str(value or "").strip()
        parent = os.path.abspath(raw) if raw else os.path.join(
            os.path.expanduser("~"), "NexCoder Projects")
        os.makedirs(parent, exist_ok=True)
        if not os.path.isdir(parent):
            raise NotADirectoryError(f"Clone location is not a folder: {parent}")
        return parent

    def _derive_clone_directory_name(self, url: str, directory_name: str) -> str:
        explicit = str(directory_name or "").strip()
        if explicit:
            name = explicit
        else:
            parsed = urlparse(url)
            source = parsed.path if parsed.scheme else url.rsplit(":", 1)[-1]
            name = os.path.basename(source.rstrip("/\\")) or "repository"
            if name.endswith(".git"):
                name = name[:-4]
        name = re.sub(r"[^A-Za-z0-9._ -]+", "-", name).strip(" .-")
        if not name:
            raise ValueError("Clone directory name is invalid")
        if name in {".", ".."}:
            raise ValueError("Clone directory name is invalid")
        return name[:120]

    def _run_clone_job(
        self,
        clone_id: str,
        git_exe: str,
        repository_url: str,
        target: str,
    ) -> None:
        try:
            parent = os.path.dirname(target)
            os.makedirs(parent, exist_ok=True)
            completed = subprocess.run(
                [git_exe, "clone", "--", repository_url, target],
                cwd=parent,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60 * 30,
                shell=False,
            )
            if completed.returncode != 0:
                output = (completed.stderr or completed.stdout or "git clone failed").strip()
                raise RuntimeError(output[-1200:])
            self._clone_hub.completed.emit(json.dumps({
                "success": True,
                "clone_id": clone_id,
                "target": target,
            }))
        except Exception as exc:
            self._clone_hub.completed.emit(slot_error_response(
                exc,
                details={"clone_id": clone_id, "target": target},
            ))

    @Slot(str)
    def _on_clone_completed(self, payload: str) -> None:
        try:
            result = json.loads(payload)
        except json.JSONDecodeError:
            self.clone_completed.emit(payload)
            return
        envelope_details = result.get("error_envelope", {}).get("details", {})
        clone_id = str(
            result.get("clone_id")
            or result.get("details", {}).get("clone_id")
            or envelope_details.get("clone_id")
            or "")
        if clone_id:
            self._clone_jobs.pop(clone_id, None)
        if not result.get("success"):
            self.clone_completed.emit(json.dumps(result))
            return
        opened = json.loads(self._open_project(str(result.get("target") or "")))
        opened["clone_id"] = clone_id
        self.clone_completed.emit(json.dumps(opened))

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
            target, in_project = self._resolve_readable_file(path)
            if in_project:
                content = self._fs.read_file(target)
            else:
                from nexcoder.ipc.filesystem import BINARY_EXTENSIONS
                if not os.path.isfile(target):
                    raise FileNotFoundError(f"File not found: {target}")
                if os.path.splitext(target)[1].lower() in BINARY_EXTENSIONS:
                    raise ValueError(f"Cannot read binary file: {target}")
                content = None
                for encoding in ("utf-8", "utf-8-sig", "latin-1"):
                    try:
                        with open(target, "r", encoding=encoding) as handle:
                            content = handle.read()
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                if content is None:
                    raise ValueError(f"Could not decode file: {target}")
            return json.dumps({"success": True, "content": content, "path": path})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def read_file_base64(self, path: str) -> str:
        """Read a bounded project file as a MIME-aware data URL for previews."""
        import base64
        import mimetypes

        mime_overrides = {
            ".wav": "audio/wav", ".flac": "audio/flac", ".m4a": "audio/mp4", ".aac": "audio/aac",
            ".opus": "audio/ogg", ".weba": "audio/webm",
            ".m4v": "video/mp4", ".ogv": "video/ogg", ".mkv": "video/x-matroska",
            ".avif": "image/avif", ".heic": "image/heic", ".heif": "image/heif",
            ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
            ".otf": "font/otf",
        }
        try:
            target, _ = self._resolve_readable_file(path)
            size = os.path.getsize(target)
            if size > MAX_PREVIEW_BYTES:
                limit_mb = MAX_PREVIEW_BYTES // (1024 * 1024)
                return slot_error_response(
                    ValueError(f"File is too large to preview ({limit_mb} MB limit)"))
            extension = os.path.splitext(target)[1].lower()
            mime = mime_overrides.get(extension) or mimetypes.guess_type(target)[0]
            mime = mime or "application/octet-stream"
            with open(target, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode("ascii")
            return json.dumps({
                "success": True,
                "path": path,
                "size": size,
                "mime_type": mime,
                "data_url": f"data:{mime};base64,{encoded}",
            })
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def write_file_base64(self, path: str, b64: str) -> str:
        """Write a binary file from base64 (drag-drop import of images etc.)."""
        import base64
        try:
            root = self._require_project_path()
            target = os.path.abspath(path if os.path.isabs(path)
                                     else os.path.join(root, path))
            if os.path.commonpath([root, target]) != root:
                return slot_error_response(
                    ValueError("Path is outside the active project"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(base64.b64decode(b64))
            return json.dumps({"success": True, "path": path})
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

    @Slot(str, result=str)
    def delete_artifact_file(self, path: str) -> str:
        """Delete a generated artifact file without the general file prompt.

        This is limited to NexCoder's project-owned artifact folder so clearing
        generated reports does not expose a broad silent delete capability to
        the UI.
        """
        try:
            project_root = self._require_project_path()
            normalized = (path or "").replace("\\", "/").lstrip("/")
            artifact_root = os.path.abspath(
                os.path.join(project_root, ".nexcoder", "artifacts"))
            target = os.path.abspath(os.path.join(project_root, normalized))
            if os.path.commonpath([artifact_root, target]) != artifact_root:
                raise ValueError("Artifact delete is limited to .nexcoder/artifacts")
            basename = os.path.basename(target)
            if basename != "index.json" and os.path.splitext(target)[1].lower() != ".md":
                raise ValueError("Only artifact markdown files and index.json can be deleted")
            if not os.path.exists(target):
                return json.dumps({"success": True, "path": normalized, "missing": True})
            if os.path.isdir(target):
                raise ValueError("Artifact delete cannot remove directories")
            os.unlink(target)
            return json.dumps({"success": True, "path": normalized})
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
            requested_dir = (cwd or "").strip()
            if requested_dir:
                working_dir = self._resolve_project_path(requested_dir)
            elif self._current_project_path and os.path.isdir(self._current_project_path):
                working_dir = self._current_project_path
            else:
                # The terminal remains useful before a project is opened. The
                # user home is stable and avoids depending on the launch cwd.
                working_dir = os.path.expanduser("~")
            session_id = self._terminal.spawn(working_dir)
            snapshot = self._terminal.snapshot(session_id) or {}
            return json.dumps({"success": True, **snapshot})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def terminal_snapshot(self, session_id: str) -> str:
        """Return terminal state and buffered output for UI reattachment."""
        snapshot = self._terminal.snapshot(session_id)
        if snapshot is None:
            return json.dumps({
                "success": False,
                "error": "Terminal session no longer exists",
                "code": "terminal_not_found",
            })
        return json.dumps({"success": True, **snapshot})

    @Slot(str, str, result=str)
    def write_terminal(self, session_id: str, data: str) -> str:
        """Write data to a terminal session."""
        accepted = self._terminal.write(session_id, data)
        return json.dumps({"success": accepted})

    @Slot(str, int, int, result=str)
    def resize_terminal(self, session_id: str, cols: int, rows: int) -> str:
        """Resize a terminal session."""
        resized = self._terminal.resize(session_id, cols, rows)
        return json.dumps({"success": resized})

    @Slot(str, result=str)
    def kill_terminal(self, session_id: str) -> str:
        """Kill a terminal session."""
        removed = self._terminal.kill(session_id)
        return json.dumps({"success": True, "removed": removed})

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

    # Legacy per-mode slots delegate to the v2 engine so every surface —
    # including older callers — runs on the same AgentLoop profiles.
    # Their legacy context shape (currentFile/selection) is translated to
    # the v2 editor-context shape; everything else v2 gathers itself.

    @staticmethod
    def _legacy_context(context_json: str) -> str:
        try:
            legacy = json.loads(context_json) if context_json else {}
        except ValueError:
            legacy = {}
        if not isinstance(legacy, dict):
            legacy = {}
        translated = {
            "active_file": legacy.get("currentFile"),
            "selection": legacy.get("selection"),
        }
        return json.dumps(translated) if any(translated.values()) else ""

    @Slot(str, str, result=str)
    def agent_ask(self, prompt: str, context_json: str = "") -> str:
        """AI Ask mode — read-only questions (v2 engine)."""
        return self.agent_run_v2(prompt, "", "ask",
                                 self._legacy_context(context_json))

    @Slot(str, str, result=str)
    def agent_edit(self, prompt: str, context_json: str = "") -> str:
        """AI Edit mode — precise scoped edits (v2 engine)."""
        return self.agent_run_v2(prompt, "", "edit",
                                 self._legacy_context(context_json))

    @Slot(str, str, result=str)
    def agent_run(self, prompt: str, context_json: str = "") -> str:
        """AI Agent mode — multi-step autonomous (v2 engine)."""
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
            )
        )
        return self.agent_run_v2(prompt, "", "scan" if scan_requested else "agent",
                                 self._legacy_context(context_json))

    @Slot(str, str, str, str, result=str)
    def agent_run_v2(self, prompt: str, skill_id: str = "",
                     mode: str = "agent", context_json: str = "") -> str:
        """v2 engine for every AI mode (agent/ask/edit/debug/review/scan)."""
        try:
            busy = self._engine_busy()
            if busy:
                return json.dumps({"success": False, "error": busy})
            project_root = self._require_project_path()
            from nexcoder.agent.agent_runtime_v2 import AgentV2Worker, UiPermissionGate
            try:
                editor_context = json.loads(context_json) if context_json else None
            except ValueError:
                editor_context = None
            if not isinstance(editor_context, dict):
                editor_context = None
            plan_context: dict[str, Any] = {}
            if editor_context is not None:
                raw_plan_context = editor_context.pop("plan_context", {})
                if isinstance(raw_plan_context, dict):
                    plan_context = dict(raw_plan_context)
            attachments: list[dict] = []
            if editor_context is not None:
                attachments = validate_image_attachments(
                    editor_context.pop("attachments", []))
            prompt = str(prompt or "").strip()
            if not prompt and attachments:
                prompt = (
                    "Analyze the attached image, diagnose the visible problem, "
                    "and use the project tools to fix it.")
            if not prompt:
                raise ValueError("Prompt cannot be empty")
            # Persist the prompt into the project chat history. The UI's
            # active session rides in the context payload; without one a
            # session is created so the run is never lost on restart.
            session_id = None
            client_prompt_id = None
            if editor_context is not None:
                session_id = editor_context.pop("session_id", None) or None
                client_prompt_id = (
                    str(editor_context.pop("client_prompt_id", "") or "").strip()
                    or None)
                if not any(editor_context.values()):
                    editor_context = None
            session_id, history = self._persist_v2_prompt(
                project_root, session_id, prompt, mode or "agent",
                attachment_metadata(attachments), client_prompt_id)
            if (mode or "agent") == "plan" and not plan_context.get("plan_id"):
                plan = self._plan_manager(project_root).create(
                    conversation_id=session_id or "", request=prompt,
                    title=(prompt[:72] or "Implementation Plan"))
                plan_context = {"plan_id": plan.id, "revision": plan.revision}
                if session_id:
                    self._session_store(project_root).set_plan(session_id, plan.id)
                self.plan_updated.emit(json.dumps(
                    plan.to_dict(), ensure_ascii=False, default=str))
            self._active_plan_context = dict(plan_context)
            self._active_plan_execution = bool(
                plan_context.get("plan_id") and (mode or "agent") != "plan")
            resume_messages = self._resume_v2_messages(project_root, history)
            # The UI's permission card is driven by the loop's own
            # permission_request event (relayed below); the gate only blocks.
            self._agent_v2_gate = UiPermissionGate(on_request=lambda *args: None)
            self._agent_v2_worker = AgentV2Worker(
                project_root, prompt, self._agent_v2_gate,
                autonomy=str(getattr(self, "_agent_v2_autonomy", "ask")),
                full_auto=bool(getattr(self, "_agent_v2_full_auto", False)),
                skill_id=skill_id, mode=mode or "agent",
                editor_context=editor_context, history=history,
                resume_messages=resume_messages, attachments=attachments,
                plan_context=plan_context)
            # Explicitly queued to real @Slot methods: PySide connects plain
            # Python callables as DIRECT connections, which would run the
            # relay on the worker thread — and QWebChannel silently drops
            # (and can crash on) signals emitted off the owner thread.
            self._agent_v2_worker.event_json.connect(
                self._relay_agent_event, Qt.ConnectionType.QueuedConnection)
            self._agent_v2_worker.finished_json.connect(
                self._on_agent_v2_finished, Qt.ConnectionType.QueuedConnection)
            self._agent_v2_worker.start()
            return json.dumps({"success": True, "mode": mode or "agent",
                               "engine": "v2", "session_id": session_id,
                               "plan_id": plan_context.get("plan_id"),
                               "plan_revision": plan_context.get("revision", 0)})
        except Exception as e:
            return slot_error_response(e)

    def _persist_v2_prompt(self, project_root: str, session_id: str | None,
                           prompt: str, mode: str,
                           attachments: list[dict] | None = None,
                           client_prompt_id: str | None = None,
                           ) -> tuple[str | None, list[dict]]:
        """Append the user prompt to the chat session; create one if needed.

        Returns ``(session_id, prior_messages)`` — the prior messages give
        follow-up prompts their conversation context. History must never
        block a run: any failure returns ``(None, [])`` and the run
        proceeds unpersisted.
        """
        try:
            store = self._session_store(os.path.abspath(project_root))
            history: list[dict] = []
            if session_id:
                try:
                    history = [
                        {"role": m.role, "content": m.content,
                         "metadata": dict(m.metadata or {})}
                        for m in store.iter_messages(session_id)
                    ][-12:]
                    store.append_message(session_id, "user", prompt, {
                        "mode": mode,
                        "attachments": list(attachments or []),
                        "client_prompt_id": client_prompt_id,
                    })
                    self._agent_v2_session_id = session_id
                    return session_id, history
                except (FileNotFoundError, ValueError):
                    session_id = None
            meta = store.create_session(mode=mode)
            store.append_message(meta.session_id, "user", prompt, {
                "mode": mode,
                "attachments": list(attachments or []),
                "client_prompt_id": client_prompt_id,
            })
            self._agent_v2_session_id = meta.session_id
            return meta.session_id, []
        except Exception:
            self._agent_v2_session_id = None
            return None, []

    @staticmethod
    def _resume_v2_messages(project_root: str,
                            history: list[dict]) -> list[dict]:
        """Load the last agent run transcript for a real continuation.

        Chat messages alone only contain the final summary. Their assistant
        metadata points at the full AgentLoop session, including completed
        tool calls and results, so a follow-up can continue without reading
        the same files again.
        """
        try:
            from nexcoder.agent.core.session_store import SessionStore
            run_id = ""
            for message in reversed(history):
                metadata = message.get("metadata") or {}
                candidate = str(metadata.get("run_id") or "")
                if message.get("role") == "assistant" and candidate:
                    run_id = candidate
                    break
            if not run_id:
                return []
            saved = SessionStore(project_root).load(run_id) or {}
            messages = saved.get("messages") or []
            return [dict(item) for item in messages if isinstance(item, dict)]
        except Exception:
            return []

    @Slot(str)
    def _relay_agent_event(self, event_json: str) -> None:
        """Re-emit agent events from the main thread for QWebChannel."""
        self.agent_event.emit(event_json)
        try:
            event = json.loads(event_json)
            plan = (event.get("payload") or {}).get("plan")
            if event.get("type") in {
                    "plan_updated", "plan_questions", "plan_deviation"} and plan:
                self.plan_updated.emit(json.dumps(
                    plan, ensure_ascii=False, default=str))
            elif (event.get("type") == "todo_updated"
                  and self._active_plan_execution
                  and self._active_plan_context.get("plan_id")):
                progress = self._plan_manager().sync_progress(
                    str(self._active_plan_context["plan_id"]),
                    list((event.get("payload") or {}).get("todos") or []))
                self.plan_updated.emit(json.dumps(
                    progress.to_dict(), ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            pass

    @Slot(str)
    def _on_agent_v2_finished(self, result_json: str) -> None:
        if self._active_plan_execution and self._active_plan_context.get("plan_id"):
            try:
                result = json.loads(result_json)
                success = str(result.get("status") or "") == "completed"
                plan = self._plan_manager().complete(
                    str(self._active_plan_context["plan_id"]), success)
                payload = json.dumps({"type": "plan_updated", "payload": {
                    "plan": plan.to_dict()}}, ensure_ascii=False, default=str)
                self.agent_event.emit(payload)
                self.plan_updated.emit(json.dumps(
                    plan.to_dict(), ensure_ascii=False, default=str))
            except Exception:
                logger.exception("Could not finalize implementation plan")
        self._active_plan_execution = False
        result_json = self._persist_v2_result(result_json)
        self.agent_complete.emit(result_json)
        try:
            if self._current_project_path:
                tree = self._fs.get_file_tree(self._current_project_path)
                self.file_tree_updated.emit(json.dumps(tree))
        except Exception:
            pass

    def _persist_v2_result(self, result_json: str) -> str:
        """Record the run's final answer in the chat session.

        Returns the result JSON with ``session_id`` attached so the UI
        can adopt the session the bridge created.
        """
        session_id = getattr(self, "_agent_v2_session_id", None)
        if not session_id or not self._current_project_path:
            return result_json
        try:
            result = json.loads(result_json)
            store = self._session_store(
                os.path.abspath(self._current_project_path))
            content = str(result.get("final_text") or "").strip()
            if not content:
                # Never store a blank assistant turn — restored chats
                # would show an empty bubble.
                mutated = result.get("mutated_files") or []
                status = str(result.get("status") or "finished")
                content = (f"(run {status}; {len(mutated)} file(s) changed)"
                           if mutated else f"(run {status})")
            store.append_message(
                session_id, "assistant", content,
                {"run_id": result.get("run_id"),
                 "status": result.get("status"),
                 "checkpoint_id": result.get("checkpoint_id"),
                 "mutated_files": result.get("mutated_files") or []})
            status = str(result.get("status") or "")
            store.set_status(session_id, {
                "cancelled": "cancelled", "error": "error",
            }.get(status, "complete"))
            result["session_id"] = session_id
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return result_json

    @Slot(result=str)
    def agent_cancel_v2(self) -> str:
        worker = self._agent_v2_worker
        if worker is None or not worker.isRunning():
            return json.dumps({"success": False, "error": "No agent run active"})
        worker.cancel()
        # A run blocked on a permission prompt must also unblock.
        if self._agent_v2_gate is not None:
            from nexcoder.agent.core.tools.base import DENY
            self._agent_v2_gate.resolve("cancel-all", DENY)
        return json.dumps({"success": True})

    @Slot(str, str, str, result=str)
    def agent_steer_v2(self, prompt: str, attachments_json: str = "",
                       client_prompt_id: str = "") -> str:
        """Inject a follow-up prompt into the active single-agent run."""
        value = str(prompt or "").strip()
        try:
            raw_attachments = (json.loads(attachments_json)
                               if attachments_json else [])
            attachments = validate_image_attachments(raw_attachments)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return slot_error_response(exc)
        if not value and not attachments:
            return json.dumps({"success": False,
                               "error": "Steering prompt cannot be empty"})
        if not value:
            value = "Analyze the attached image and apply it to the active task."
        worker = self._agent_v2_worker
        if worker is None or not worker.isRunning():
            return json.dumps({"success": False,
                               "error": "No agent run active"})
        if attachments:
            worker.steer(value, attachments)
        else:
            worker.steer(value)
        session_id = getattr(self, "_agent_v2_session_id", None)
        if session_id and self._current_project_path:
            try:
                store = self._session_store(
                    os.path.abspath(self._current_project_path))
                store.append_message(session_id, "user", value, {
                    "mode": "steer",
                    "attachments": attachment_metadata(attachments),
                    "client_prompt_id": str(client_prompt_id or "").strip()
                    or None,
                })
            except Exception:
                # Persistence failure must not block live steering.
                pass
        return json.dumps({"success": True})

    # -- Interactive implementation plans ---------------------------------

    def _plan_response(self, plan: Any, **extra: Any) -> str:
        payload = {"success": True, "plan": plan.to_dict(), **extra}
        rendered = json.dumps(plan.to_dict(), ensure_ascii=False, default=str)
        self.plan_updated.emit(rendered)
        return json.dumps(payload, ensure_ascii=False, default=str)

    @Slot(str, result=str)
    def plan_get(self, plan_id: str) -> str:
        try:
            return self._plan_response(self._plan_manager().load(plan_id))
        except Exception as exc:
            return slot_error_response(exc, code="plan_not_found")

    @Slot(str, result=str)
    def plan_list(self, conversation_id: str = "") -> str:
        try:
            plans = [item.to_dict() for item in
                     self._plan_manager().list(conversation_id)]
            return json.dumps({"success": True, "plans": plans},
                              ensure_ascii=False, default=str)
        except Exception as exc:
            return slot_error_response(exc)

    @Slot(str, int, str, result=str)
    def plan_answer(self, plan_id: str, revision: int,
                    answers_json: str) -> str:
        try:
            answers = json.loads(answers_json) if answers_json else {}
            if not isinstance(answers, dict):
                raise ValueError("Answers must be an object")
            plan = self._plan_manager().answer_questions(
                plan_id, revision, answers)
            return self._plan_response(
                plan,
                resume_prompt=(
                    "Continue the implementation plan using the submitted "
                    "clarification answers:\n"
                    + json.dumps(answers, ensure_ascii=False, default=str)
                    + "\nInspect any remaining relevant "
                    "files, then submit the complete structured plan."))
        except Exception as exc:
            return slot_error_response(exc, code="plan_answer_failed")

    @Slot(str, int, str, result=str)
    def plan_request_revision(self, plan_id: str, revision: int,
                              review: str) -> str:
        try:
            if not str(review or "").strip():
                raise ValueError("Describe the requested plan changes")
            plan = self._plan_manager().request_revision(
                plan_id, revision, review)
            return self._plan_response(
                plan,
                resume_prompt=(
                    "Revise the implementation plan to address this review: "
                    + review.strip()))
        except Exception as exc:
            return slot_error_response(exc, code="plan_revision_failed")

    @Slot(str, int, result=str)
    def plan_approve_and_execute(self, plan_id: str, revision: int) -> str:
        """Atomically approve the current revision and start its agent run."""
        try:
            busy = self._engine_busy()
            if busy:
                raise RuntimeError(busy)
            manager = self._plan_manager()
            plan = manager.approve(plan_id, revision)
            plan = manager.begin_execution(plan_id, revision)
            execution_prompt = (
                "Execute the approved implementation plan below phase by phase. "
                "Keep todo progress current, run every validation step, and report "
                "minor deviations with report_plan_deviation. For a material "
                "deviation, report it as material and stop for renewed approval.\n\n"
                + plan.markdown_content)
            context = json.dumps({
                "plan_context": {"plan_id": plan.id,
                                 "revision": plan.revision},
                "session_id": plan.conversation_id or None,
            }, ensure_ascii=False)
            started = json.loads(self.agent_run_v2(
                execution_prompt, "", "agent", context))
            if not started.get("success"):
                manager.complete(plan_id, False)
                raise RuntimeError(started.get("error") or "Could not start execution")
            self.plan_updated.emit(json.dumps(
                plan.to_dict(), ensure_ascii=False, default=str))
            return json.dumps({"success": True, "plan": plan.to_dict(),
                               "run": started}, ensure_ascii=False, default=str)
        except Exception as exc:
            return slot_error_response(exc, code="plan_approval_failed")

    @Slot(str, result=str)
    def plan_cancel(self, plan_id: str) -> str:
        try:
            if (self._active_plan_context.get("plan_id") == plan_id
                    and self._agent_v2_worker is not None
                    and self._agent_v2_worker.isRunning()):
                self.agent_cancel_v2()
            return self._plan_response(self._plan_manager().cancel(plan_id))
        except Exception as exc:
            return slot_error_response(exc, code="plan_cancel_failed")

    @Slot(str, str, result=str)
    def plan_save_markdown(self, plan_id: str, suggested_path: str = "") -> str:
        try:
            manager = self._plan_manager()
            plan = manager.load(plan_id)
            slug = "-".join(plan.title.lower().split())[:72] or plan.id
            suggested = suggested_path or f"docs/plans/{slug}.md"
            saved = json.loads(self.save_file_as(suggested, plan.markdown_content))
            if not saved.get("success"):
                return json.dumps(saved)
            plan = manager.note_saved(plan_id, str(saved.get("path") or ""))
            return self._plan_response(plan, path=saved.get("path"))
        except Exception as exc:
            return slot_error_response(exc, code="plan_save_failed")

    @Slot(str, str, result=str)
    def agent_permission_response(self, request_id: str, decision: str) -> str:
        # Whichever engine is waiting gets the answer; UiPermissionGate
        # resolves by id (or its single pending request), so answering
        # the idle gate is a no-op.
        if self._agent_v2_gate is not None:
            self._agent_v2_gate.resolve(request_id, decision)
        if self._mesh_gate is not None:
            self._mesh_gate.resolve(request_id, decision)
        return json.dumps({"success": True})

    # ── Agent Mesh ───────────────────────────────────────────────────

    def _engine_busy(self) -> str | None:
        if self._agent_v2_worker is not None and self._agent_v2_worker.isRunning():
            return "A single-agent run is active — wait for it to finish."
        if self._mesh_worker is not None and self._mesh_worker.isRunning():
            return "A mesh run is already active."
        return None

    @Slot(str, result=str)
    def mesh_run(self, goal: str) -> str:
        """Start an Agent Mesh run: orchestrator + bounded specialists."""
        try:
            if not (goal or "").strip():
                return json.dumps({"success": False,
                                   "error": "Describe a goal for the mesh."})
            busy = self._engine_busy()
            if busy:
                return json.dumps({"success": False, "error": busy})
            project_root = self._require_project_path()
            from nexcoder.agent.agent_runtime_v2 import UiPermissionGate
            from nexcoder.agent.mesh_runtime import MeshWorker
            self._mesh_gate = UiPermissionGate(on_request=lambda *args: None)
            self._mesh_worker = MeshWorker(
                project_root, goal.strip(), self._mesh_gate,
                autonomy=str(getattr(self, "_agent_v2_autonomy", "ask")))
            self._mesh_worker.event_json.connect(
                self._relay_mesh_event, Qt.ConnectionType.QueuedConnection)
            self._mesh_worker.finished_json.connect(
                self._on_mesh_finished, Qt.ConnectionType.QueuedConnection)
            self._mesh_worker.start()
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str)
    def _relay_mesh_event(self, event_json: str) -> None:
        """Re-emit mesh events from the main thread for QWebChannel."""
        self.mesh_event.emit(event_json)

    @Slot(str)
    def _on_mesh_finished(self, summary_json: str) -> None:
        try:
            if self._current_project_path:
                tree = self._fs.get_file_tree(self._current_project_path)
                self.file_tree_updated.emit(json.dumps(tree))
        except Exception:
            pass

    @Slot(result=str)
    def mesh_cancel(self) -> str:
        worker = self._mesh_worker
        if worker is None or not worker.isRunning():
            return json.dumps({"success": False, "error": "No mesh active"})
        worker.cancel()
        if self._mesh_gate is not None:
            from nexcoder.agent.core.tools.base import DENY
            self._mesh_gate.resolve("cancel-all", DENY)
        return json.dumps({"success": True})

    @Slot(result=str)
    def mesh_list(self) -> str:
        """Past mesh runs for the panel's history list."""
        try:
            if not self._current_project_path:
                return json.dumps({"success": True, "runs": []})
            from nexcoder.agent.mesh.orchestrator import list_mesh_runs
            return json.dumps({
                "success": True,
                "runs": list_mesh_runs(self._current_project_path)})
        except Exception as e:
            return slot_error_response(e)

    # ── Engine settings / permissions / memory (settings surface) ────

    @Slot(result=str)
    def agent_get_engine_settings(self) -> str:
        """Current v2 engine configuration, for the settings page."""
        try:
            from nexcoder.agent.core.backend_config import load_backend_config
            config = load_backend_config()
            return json.dumps({"success": True, "settings": {
                "base_url": config.base_url,
                "model": config.model,
                "adapter": config.adapter,
                "context_window": config.context_window,
                "max_output_tokens": config.reserve_output,
                "temperature": config.temperature,
                "full_auto": bool(getattr(self, "_agent_v2_full_auto", False)),
                "autonomy": str(getattr(self, "_agent_v2_autonomy", "ask")),
                "api_key_set": bool(config.api_key),
            }})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_update_engine_settings(self, settings_json: str) -> str:
        """Apply engine settings (context window, adapter, full auto).

        Settings land in process env vars, which every v2 run reads at
        start — no restart needed. The UI persists them and re-applies
        on launch.
        """
        try:
            data = json.loads(settings_json) if settings_json else {}
            if not isinstance(data, dict):
                data = {}
            context_window = data.get("context_window")
            if context_window:
                os.environ["NEXA_CONTEXT_WINDOW"] = str(
                    max(2048, int(context_window)))
            adapter = data.get("adapter")
            if adapter in ("xml", "native"):
                os.environ["NEXCODER_ADAPTER"] = adapter
            if "full_auto" in data:
                self._agent_v2_full_auto = bool(data.get("full_auto"))
            autonomy = data.get("autonomy")
            if autonomy:
                from nexcoder.agent.core.command_policy import AUTONOMY_LEVELS
                if autonomy in AUTONOMY_LEVELS:
                    self._agent_v2_autonomy = autonomy
            max_output = data.get("max_output_tokens")
            if max_output:
                os.environ["NEXCODER_RESERVE_OUTPUT"] = str(
                    max(1024, int(max_output)))
            if "temperature" in data:
                os.environ["NEXCODER_TEMPERATURE"] = str(
                    min(2.0, max(0.0, float(data.get("temperature") or 0.2))))
            if "max_turns" in data:
                os.environ["NEXCODER_MAX_TURNS"] = str(
                    max(0, int(data.get("max_turns") or 0)))
            if "disabled_tools" in data:
                tools = data.get("disabled_tools") or []
                if isinstance(tools, list):
                    os.environ["NEXCODER_DISABLED_TOOLS"] = ",".join(
                        str(t) for t in tools)
            if "memory_enabled" in data:
                os.environ["NEXCODER_MEMORY"] = (
                    "1" if data.get("memory_enabled") else "0")
            for key, env in (("cmd_build", "NEXCODER_CMD_BUILD"),
                             ("cmd_test", "NEXCODER_CMD_TEST"),
                             ("cmd_lint", "NEXCODER_CMD_LINT")):
                if key in data:
                    os.environ[env] = str(data.get(key) or "")
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def agent_permissions_list(self) -> str:
        """Commands the user allowed with "always" for this project."""
        try:
            if not self._current_project_path:
                return json.dumps({"success": True, "commands": []})
            path = (Path(self._current_project_path) / ".nexcoder"
                    / "permissions.json")
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                commands = [str(c) for c in data.get("allowed_commands", [])]
            except (OSError, json.JSONDecodeError, ValueError):
                commands = []
            return json.dumps({"success": True, "commands": sorted(commands)})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_permissions_remove(self, command: str) -> str:
        """Revoke a previously always-allowed command."""
        try:
            root = self._require_project_path()
            path = Path(root) / ".nexcoder" / "permissions.json"
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                commands = [str(c) for c in data.get("allowed_commands", [])]
            except (OSError, json.JSONDecodeError, ValueError):
                commands = []
            remaining = [c for c in commands if c != command]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"allowed_commands": sorted(set(remaining))},
                           indent=2),
                encoding="utf-8")
            return json.dumps({"success": True, "commands": sorted(remaining)})
        except Exception as e:
            return slot_error_response(e)

    # ── LSP (language intelligence) ──────────────────────────────────

    def _lsp(self):
        """Lazily construct the manager and point it at the project."""
        if self._lsp_manager is None:
            from concurrent.futures import ThreadPoolExecutor
            from nexcoder.lsp.manager import LspManager
            self._lsp_manager = LspManager(
                on_diagnostics=lambda path, diagnostics:
                    self._lsp_hub.diagnostics.emit(json.dumps(
                        {"path": path, "diagnostics": diagnostics},
                        ensure_ascii=False, default=str)))
            self._lsp_pool = ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="lsp")
        if self._current_project_path:
            self._lsp_manager.set_project(self._current_project_path)
        return self._lsp_manager

    @Slot(str)
    def _relay_lsp_response(self, payload: str) -> None:
        self.lsp_response.emit(payload)

    @Slot(str)
    def _relay_lsp_diagnostics(self, payload: str) -> None:
        self.lsp_diagnostics.emit(payload)

    @Slot(str, str, str, result=str)
    def lsp_did_open(self, path: str, language: str, text: str) -> str:
        try:
            manager = self._lsp()
            self._lsp_pool.submit(manager.did_open, path, language, text)
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def lsp_did_change(self, path: str, text: str) -> str:
        try:
            manager = self._lsp()
            self._lsp_pool.submit(manager.did_change, path, text)
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def lsp_did_close(self, path: str) -> str:
        try:
            manager = self._lsp()
            self._lsp_pool.submit(manager.did_close, path)
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, str, int, int, str, result=str)
    def lsp_request(self, request_id: str, kind: str, path: str,
                    line: int, character: int, extra: str = "") -> str:
        """Async LSP query; the result arrives on the lsp_response signal."""
        try:
            manager = self._lsp()
        except Exception as e:
            return slot_error_response(e)

        def work() -> None:
            payload: dict = {"id": request_id, "kind": kind}
            try:
                if kind == "completion":
                    payload["result"] = manager.completion(path, line, character)
                elif kind == "hover":
                    payload["result"] = manager.hover(path, line, character)
                elif kind == "definition":
                    payload["result"] = manager.definition(path, line, character)
                elif kind == "references":
                    payload["result"] = manager.references(path, line, character)
                elif kind == "rename":
                    payload["result"] = self._lsp_apply_rename(
                        manager, path, line, character, extra)
                else:
                    payload["error"] = f"Unknown LSP request kind: {kind}"
            except Exception as exc:  # never leave the UI promise hanging
                payload["error"] = str(exc)
            self._lsp_hub.response.emit(
                json.dumps(payload, ensure_ascii=False, default=str))

        self._lsp_pool.submit(work)
        return json.dumps({"success": True})

    def _lsp_apply_rename(self, manager, path: str, line: int,
                          character: int, new_name: str) -> dict:
        """Apply a rename atomically on disk; UI reloads changed files."""
        from nexcoder.lsp.manager import apply_text_edits
        edits_by_path = manager.rename(path, line, character, new_name)
        if not edits_by_path:
            return {"changed_files": []}
        root = os.path.abspath(self._require_project_path())
        changed: list[str] = []
        for target, edits in edits_by_path.items():
            absolute = os.path.abspath(target)
            if os.path.commonpath([root, absolute]) != root:
                continue  # never let a server edit outside the project
            with open(absolute, "r", encoding="utf-8", errors="replace") as fh:
                original = fh.read()
            updated = apply_text_edits(original, edits)
            if updated != original:
                with open(absolute, "w", encoding="utf-8", newline="") as fh:
                    fh.write(updated)
                changed.append(absolute)
        return {"changed_files": changed}

    @Slot(result=str)
    def agent_get_active_rules(self) -> str:
        """The rendered project rules the agent sees (settings viewer)."""
        try:
            if not self._current_project_path:
                return json.dumps({"success": True, "rules": ""})
            from nexcoder.agent.core.rules import load_project_rules
            return json.dumps({
                "success": True,
                "rules": load_project_rules(self._current_project_path)})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def test_model_connection(self) -> str:
        """Probe the configured AI backend (settings page health check)."""
        try:
            from nexcoder.agent.model_connector import ModelConnector
            return json.dumps({"success": True,
                               **ModelConnector().test_connection()})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def lsp_status(self) -> str:
        try:
            return json.dumps({"success": True,
                               "servers": self._lsp().status()})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def agent_memory_get(self) -> str:
        """The project memory file the agent injects into every run."""
        try:
            if not self._current_project_path:
                return json.dumps({"success": True, "content": ""})
            from nexcoder.agent.core.memory import load_project_memory
            return json.dumps({
                "success": True,
                "content": load_project_memory(self._current_project_path)})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_memory_save(self, content: str) -> str:
        """Replace the project memory (edit/clear from the settings UI)."""
        try:
            root = self._require_project_path()
            path = Path(root) / ".nexcoder" / "MEMORY.md"
            text = (content or "").strip()
            if text:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text + "\n", encoding="utf-8")
            elif path.exists():
                path.write_text("", encoding="utf-8")
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def agent_revert_run(self, checkpoint_id: str) -> str:
        from nexcoder.services.checkpoint import CheckpointManager
        try:
            manager = CheckpointManager(self._require_project_path())
            restored = manager.restore(checkpoint_id)
            tree = self._fs.get_file_tree(self._current_project_path)
            self.file_tree_updated.emit(json.dumps(tree))
            return json.dumps({"success": True, **restored})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def agent_revert_file(self, checkpoint_id: str, path: str) -> str:
        from nexcoder.services.checkpoint import CheckpointManager
        try:
            manager = CheckpointManager(self._require_project_path())
            restored = manager.restore(checkpoint_id, files=[path])
            return json.dumps({"success": True, **restored})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, str, result=str)
    def agent_rewind_to_prompt(self, session_id: str, target_json: str) -> str:
        """Restore agent edits from a prompt onward and discard that branch.

        Checkpoints are restored newest-first. This ordering matters when two
        later runs touched the same file: each restore walks the file back one
        state until the selected prompt's pre-run version is reached.
        """
        try:
            busy = self._engine_busy()
            if busy:
                return slot_error_response(
                    RuntimeError(busy), code="agent_busy",
                    category="user_recoverable", retryable=True)
            root = self._require_project_path()
            target = json.loads(target_json) if target_json else {}
            if not isinstance(target, dict):
                raise ValueError("Invalid prompt rewind target")
            prompt_id = str(target.get("client_prompt_id") or "").strip()
            expected_content = str(target.get("content") or "")
            ordinal = target.get("user_ordinal")

            store = self._session_store(os.path.abspath(root))
            _meta, messages = store.load_session(session_id)
            target_index = -1
            if prompt_id:
                for index, message in enumerate(messages):
                    if (message.role == "user"
                            and str(message.metadata.get(
                                "client_prompt_id") or "") == prompt_id):
                        target_index = index
                        break
            if target_index < 0 and isinstance(ordinal, int) and ordinal >= 0:
                user_indexes = [
                    index for index, message in enumerate(messages)
                    if message.role == "user"
                ]
                if ordinal < len(user_indexes):
                    candidate = user_indexes[ordinal]
                    if (not expected_content
                            or messages[candidate].content == expected_content):
                        target_index = candidate
            if target_index < 0:
                raise LookupError("The selected prompt is no longer in this session")
            selected = messages[target_index]
            if str(selected.metadata.get("mode") or "") == "steer":
                raise ValueError(
                    "A prompt injected into an active run cannot be rewound "
                    "independently; rewind the prompt that started that run")

            checkpoint_ids: list[str] = []
            for message in messages[target_index + 1:]:
                if message.role != "assistant":
                    continue
                checkpoint_id = str(
                    message.metadata.get("checkpoint_id") or "").strip()
                if checkpoint_id and checkpoint_id not in checkpoint_ids:
                    checkpoint_ids.append(checkpoint_id)

            from nexcoder.services.checkpoint import CheckpointManager
            manager = CheckpointManager(root)
            available = {
                str(item.get("id")) for item in manager.list_checkpoints()
            }
            missing = [value for value in checkpoint_ids if value not in available]
            if missing:
                return slot_error_response(
                    FileNotFoundError(
                        "Required rollback checkpoint is no longer available"),
                    code="checkpoint_expired",
                    category="user_recoverable",
                    details={"missing_checkpoint_ids": missing})

            restored_files: list[str] = []
            for checkpoint_id in reversed(checkpoint_ids):
                result = manager.restore(checkpoint_id)
                for path in result.get("restored") or []:
                    if path not in restored_files:
                        restored_files.append(path)

            store.truncate_messages(session_id, target_index)
            tree = self._fs.get_file_tree(self._current_project_path)
            self.file_tree_updated.emit(json.dumps(tree))
            return json.dumps({
                "success": True,
                "session_id": session_id,
                "kept_messages": target_index,
                "removed_messages": len(messages) - target_index,
                "reverted_checkpoints": list(reversed(checkpoint_ids)),
                "restored": restored_files,
            })
        except (LookupError, ValueError) as exc:
            return slot_error_response(
                exc, code="prompt_rewind_invalid",
                category="user_recoverable")
        except Exception as exc:
            return slot_error_response(exc)

    @Slot(str, result=str)
    def agent_scan(self, context_json: str = "") -> str:
        """Codebase scan — structured overview (v2 engine)."""
        return self.agent_run_v2(
            "Scan the project and create a codebase map.", "", "scan")

    @Slot(str, str, result=str)
    def agent_debug(self, prompt: str, context_json: str = "") -> str:
        """AI Debug mode — reproduce, root-cause, fix (v2 engine)."""
        return self.agent_run_v2(prompt, "", "debug",
                                 self._legacy_context(context_json))

    @Slot(str, str, result=str)
    def agent_review(self, prompt: str, context_json: str = "") -> str:
        """AI Review mode — read-only code audit (v2 engine)."""
        return self.agent_run_v2(prompt, "", "review",
                                 self._legacy_context(context_json))

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

    @Slot(str, str, result=str)
    def update_ai_settings(self, endpoint: str, model: str) -> str:
        """Point the engine at a different backend/model.

        Env vars are the single source of truth — every v2 run reads
        them at start via ``load_backend_config``.
        """
        try:
            if endpoint:
                os.environ["NEXA_API_URL"] = endpoint
            if model:
                os.environ["NEXA_MODEL"] = model
            return json.dumps({"success": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def get_skills(self) -> str:
        """Return list of available agent skills with metadata, grouped by category."""
        try:
            from nexcoder.agent.skills_registry import get_skills_grouped
            return json.dumps({"success": True, **get_skills_grouped(self._current_project_path)})
        except Exception as e:
            return slot_error_response(e)

    @Slot(str, result=str)
    def get_skill_body(self, skill_id: str) -> str:
        """Return the SKILL.md body content for a specific skill id."""
        try:
            from nexcoder.agent.skills_registry import get_skill_body
            record = get_skill_body(skill_id, self._current_project_path)
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

    @Slot(result=str)
    def web_auth_start(self) -> str:
        """Start web-based NexCoder login and wait for a localhost callback."""
        try:
            callback_url, state = self._start_web_auth_callback_server()
            web_origin = os.getenv("NEXCODER_WEB_URL", "https://nexcoder.trynexa-ai.com").rstrip("/")
            next_path = "/desktop-auth/complete?" + urlencode({
                "state": state,
                "return_to": callback_url,
            })
            login_url = f"{web_origin}/login?" + urlencode({"next": next_path})
            opened = webbrowser.open(login_url, new=2)
            return json.dumps({
                "success": True,
                "url": login_url,
                "callback_url": callback_url,
                "opened": bool(opened),
            })
        except Exception as e:
            return slot_error_response(e)

    def _start_web_auth_callback_server(self) -> tuple[str, str]:
        """Create a one-shot 127.0.0.1 callback server for web auth."""
        if self._web_auth_server:
            try:
                self._web_auth_server.shutdown()
                self._web_auth_server.server_close()
            except Exception:
                logger.debug("Failed to close previous web auth server", exc_info=True)
            self._web_auth_server = None

        state = secrets.token_urlsafe(32)
        bridge = self

        class AuthCallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                parsed = urlparse(self.path)
                if parsed.path != "/auth/callback":
                    self.send_error(404)
                    return
                params = parse_qs(parsed.query, keep_blank_values=True)
                received_state = params.get("state", [""])[0]
                user_payload = params.get("user", [""])[0]
                if received_state != bridge._web_auth_state:
                    self._send_html(400, "NexCoder login failed", "The login callback state did not match.")
                    bridge.web_auth_completed.emit(json.dumps({
                        "success": False,
                        "error": "Login callback state did not match.",
                    }))
                    return

                try:
                    padded = user_payload + "=" * (-len(user_payload) % 4)
                    user = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
                    if not isinstance(user, dict):
                        raise ValueError("Login payload was not an object")
                    session = user.pop("session", None)
                    if not isinstance(session, dict):
                        raise ValueError("Login payload did not include a desktop session")
                    bridge._write_web_auth_session(session)
                    bridge.web_auth_completed.emit(json.dumps({
                        "success": True,
                        "user": user,
                        "session": bridge._session_status_payload(),
                    }))
                    self._send_html(200, "NexCoder login complete", "You can return to NexCoder.")
                except Exception as exc:
                    self._send_html(400, "NexCoder login failed", "The login payload could not be read.")
                    bridge.web_auth_completed.emit(json.dumps({
                        "success": False,
                        "error": str(exc),
                    }))
                finally:
                    threading.Thread(target=bridge._stop_web_auth_server, daemon=True).start()

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_html(self, status: int, title: str, message: str) -> None:
                body = (
                    "<!doctype html><html><head><meta charset='utf-8'>"
                    f"<title>{title}</title>"
                    "<style>body{font-family:system-ui;margin:0;display:grid;place-items:center;"
                    "min-height:100vh;background:#0f0f16;color:#f4f4f5}"
                    "main{max-width:440px;padding:28px;border:1px solid #2a2a38;border-radius:16px;"
                    "background:#171722}p{color:#a1a1aa}</style></head>"
                    f"<body><main><h1>{title}</h1><p>{message}</p></main></body></html>"
                ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), AuthCallbackHandler)
        self._web_auth_server = server
        self._web_auth_state = state
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        return f"http://127.0.0.1:{port}/auth/callback", state

    def _stop_web_auth_server(self) -> None:
        server = self._web_auth_server
        self._web_auth_server = None
        self._web_auth_state = None
        if server:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                logger.debug("Failed to stop web auth server", exc_info=True)

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
            worker = self._agent_v2_worker
            if worker is None or not worker.isRunning():
                return json.dumps({"success": True, "cancelled": False})
            self.agent_cancel_v2()
            return json.dumps({"success": True, "cancelled": True})
        except Exception as e:
            return slot_error_response(e)

    @Slot(result=str)
    def agent_is_active(self) -> str:
        """True while a run is in progress. UI uses this to gate the cancel button."""
        try:
            worker = self._agent_v2_worker
            active = worker is not None and worker.isRunning()
            return json.dumps({"success": True, "active": active})
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
            store = self._session_store(os.path.abspath(root))
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
            store = self._session_store(os.path.abspath(root))
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
            store = self._session_store(os.path.abspath(root))
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
            store = self._session_store(os.path.abspath(root))
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
            store = self._session_store(os.path.abspath(root))
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
            if self._redactor is None:
                from nexcoder.agent.redaction import SecretRedactor
                self._redactor = SecretRedactor()
            result = self._redactor.redact(text or "")
            return json.dumps({
                "success": True,
                "text": result.text,
                "count": result.count,
                "labels": sorted(set(result.labels)),
            })
        except Exception as e:
            return slot_error_response(e)
