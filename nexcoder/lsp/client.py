"""Minimal, dependency-free LSP client: JSON-RPC 2.0 over stdio.

One instance == one language-server process. Thread model:
- caller threads issue ``request``/``notify`` (writes are locked);
- a reader thread parses Content-Length framed messages and either
  resolves a pending request, invokes the notification callback, or
  answers server->client requests with a benign default so servers
  like Pyright never hang waiting on us.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10.0


class LspError(RuntimeError):
    pass


class LspClient:
    def __init__(self, command: list[str], root: Path,
                 on_notification: Callable[[str, dict], None] | None = None,
                 initialization_options: dict | None = None) -> None:
        self._command = command
        self._root = Path(root)
        self._on_notification = on_notification
        self._init_options = initialization_options
        self._proc: subprocess.Popen | None = None
        self._next_id = 0
        self._pending: dict[int, dict[str, Any]] = {}
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self.initialized = False

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        creation = 0
        if os.name == "nt":
            creation = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        self._proc = subprocess.Popen(
            self._command,
            cwd=str(self._root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=creation,
        )
        self._reader = threading.Thread(
            target=self._read_loop, daemon=True,
            name=f"lsp-reader-{self._command[0]}")
        self._reader.start()
        result = self.request("initialize", {
            "processId": os.getpid(),
            "rootUri": self._root.as_uri(),
            "workspaceFolders": [{
                "uri": self._root.as_uri(), "name": self._root.name}],
            "initializationOptions": self._init_options or {},
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": False},
                    "completion": {"completionItem": {
                        "snippetSupport": False,
                        "documentationFormat": ["plaintext", "markdown"]}},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "definition": {}, "references": {}, "rename": {},
                    "publishDiagnostics": {"relatedInformation": False},
                },
                "workspace": {"configuration": False,
                              "workspaceFolders": True},
            },
        }, timeout=30.0)
        self.notify("initialized", {})
        self.initialized = True
        logger.info("LSP server ready: %s (%s)", self._command[0],
                    (result or {}).get("serverInfo", {}).get("name", "?"))

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def shutdown(self) -> None:
        try:
            if self.alive():
                try:
                    self.request("shutdown", None, timeout=3.0)
                    self.notify("exit", None)
                except Exception:
                    pass
                if self._proc is not None:
                    try:
                        self._proc.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
        finally:
            self.initialized = False

    # ── JSON-RPC ─────────────────────────────────────────────────────

    def request(self, method: str, params: Any,
                timeout: float = REQUEST_TIMEOUT) -> Any:
        if self._proc is None or not self.alive():
            raise LspError(f"Language server not running ({method})")
        with self._state_lock:
            self._next_id += 1
            request_id = self._next_id
            entry: dict[str, Any] = {"event": threading.Event()}
            self._pending[request_id] = entry
        self._send({"jsonrpc": "2.0", "id": request_id,
                    "method": method, "params": params})
        if not entry["event"].wait(timeout):
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise LspError(f"LSP request timed out: {method}")
        if "error" in entry:
            raise LspError(str(entry["error"].get("message") or entry["error"]))
        return entry.get("result")

    def notify(self, method: str, params: Any) -> None:
        if self._proc is None or not self.alive():
            return
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        frame = b"Content-Length: %d\r\n\r\n%b" % (len(body), body)
        with self._write_lock:
            assert self._proc is not None and self._proc.stdin is not None
            try:
                self._proc.stdin.write(frame)
                self._proc.stdin.flush()
            except (OSError, ValueError) as exc:
                raise LspError(f"Language server pipe closed: {exc}") from exc

    # ── Reader thread ────────────────────────────────────────────────

    def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        stream = self._proc.stdout
        try:
            while True:
                headers: dict[str, str] = {}
                while True:
                    line = stream.readline()
                    if not line:
                        return  # server exited
                    line = line.strip()
                    if not line:
                        break
                    if b":" in line:
                        key, _, value = line.partition(b":")
                        headers[key.decode("ascii").lower()] = (
                            value.decode("ascii").strip())
                length = int(headers.get("content-length", "0"))
                if length <= 0:
                    continue
                body = stream.read(length)
                if not body:
                    return
                try:
                    message = json.loads(body.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    continue
                self._dispatch(message)
        except Exception:
            logger.debug("LSP reader stopped", exc_info=True)
        finally:
            # Unblock every caller still waiting on a response.
            with self._state_lock:
                for entry in self._pending.values():
                    entry["error"] = {"message": "language server exited"}
                    entry["event"].set()
                self._pending.clear()

    def _dispatch(self, message: dict[str, Any]) -> None:
        msg_id = message.get("id")
        method = message.get("method")
        if method is None and msg_id is not None:
            # Response to one of our requests.
            with self._state_lock:
                entry = self._pending.pop(int(msg_id), None)
            if entry is not None:
                if "error" in message:
                    entry["error"] = message["error"] or {}
                else:
                    entry["result"] = message.get("result")
                entry["event"].set()
            return
        if method is not None and msg_id is not None:
            # Server->client request: answer with a benign default so
            # the server never blocks on us.
            defaults: dict[str, Any] = {
                "workspace/configuration":
                    [None] * len((message.get("params") or {})
                                 .get("items", []) or [None]),
                "window/workDoneProgress/create": None,
                "client/registerCapability": None,
                "client/unregisterCapability": None,
                "workspace/applyEdit": {"applied": False},
            }
            self._send({"jsonrpc": "2.0", "id": msg_id,
                        "result": defaults.get(method)})
            return
        if method is not None and self._on_notification is not None:
            try:
                self._on_notification(method, message.get("params") or {})
            except Exception:
                logger.debug("LSP notification handler failed", exc_info=True)
