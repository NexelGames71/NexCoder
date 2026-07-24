"""Production PTY management for NexCoder's integrated terminal."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from collections import deque
from typing import Any

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

MAX_BACKLOG_CHARS = 1_000_000
DEFAULT_COLS = 120
DEFAULT_ROWS = 30

# Destructive commands that must not be executed from the embedded terminal.
BLOCKED_COMMAND_PATTERNS = [
    r"\bformat\b",
    r"\bdiskpart\b",
    r"rm\s+-rf\s+/(?:\s|$|\*)",
    r"del\s+/s\s+/q\s+[a-z]:\\",
    r"rd\s+/s\s+/q\s+[a-z]:\\",
    r":\(\)\{.*\|.*&\}",
]


class TerminalHandler(QObject):
    """Own terminal processes and relay recoverable output to the web UI.

    Output is assigned a monotonically increasing sequence number and retained
    in a bounded backlog. The sequence/backlog pair prevents output from being
    lost when the React panel is hidden, remounted, or still creating xterm.
    """

    output_received = Signal(str, str, int)  # session_id, data, sequence
    process_exited = Signal(str, int)  # session_id, exit_code

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._readers: dict[str, threading.Thread] = {}
        self._command_buffers: dict[str, str] = {}
        self._lock = threading.RLock()

    def spawn(
        self,
        cwd: str,
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ) -> str:
        """Spawn a terminal and return its stable session identifier."""
        working_dir = os.path.abspath(cwd or os.getcwd())
        if not os.path.isdir(working_dir):
            raise NotADirectoryError(f"Terminal working directory does not exist: {working_dir}")

        session_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._sessions[session_id] = {
                "process": None,
                "type": "starting",
                "cwd": working_dir,
                "shell": "",
                "status": "starting",
                "exit_code": None,
                "closing": False,
                "sequence": 0,
                "output_chunks": deque(),
                "output_chars": 0,
            }
            self._command_buffers[session_id] = ""

        try:
            if sys.platform == "win32":
                self._spawn_windows(session_id, working_dir, cols, rows)
            else:
                self._spawn_unix(session_id, working_dir, cols, rows)
        except Exception:
            with self._lock:
                self._sessions.pop(session_id, None)
                self._command_buffers.pop(session_id, None)
            raise

        return session_id

    def snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Return metadata and buffered output needed to reattach xterm."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            return {
                "sessionId": session_id,
                "cwd": session["cwd"],
                "shell": session["shell"],
                "status": session["status"],
                "exitCode": session["exit_code"],
                "sequence": session["sequence"],
                "chunks": [
                    {"sequence": sequence, "data": data}
                    for sequence, data in session["output_chunks"]
                ],
            }

    def _spawn_windows(
        self,
        session_id: str,
        cwd: str,
        cols: int,
        rows: int,
    ) -> None:
        """Spawn PowerShell through pywinpty's packaged-compatible backend."""
        try:
            from winpty import PtyProcess
        except ImportError:
            self._spawn_subprocess(session_id, cwd)
            return

        shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
        if not shell:
            shell = os.environ.get("COMSPEC", "cmd.exe")
        command = self._windows_shell_command(shell)

        try:
            proc = PtyProcess.spawn(
                command,
                cwd=cwd,
                dimensions=(self._safe_rows(rows), self._safe_cols(cols)),
                backend=self._windows_pty_backend(),
            )
        except Exception as exc:
            logger.warning("Windows PTY startup failed; using pipe fallback: %s", exc)
            self._spawn_subprocess(session_id, cwd, shell)
            return

        self._register_process(session_id, proc, "winpty", shell)
        self._start_reader(session_id, self._read_winpty, proc)

    @staticmethod
    def _windows_pty_backend() -> int | None:
        """Select the PTY backend that is reliable in each host environment.

        ConPTY is the pywinpty default and remains preferable during normal
        development. In a windowed PyInstaller executable it can stall during
        startup before the shell is attached, whereas the legacy WinPTY agent
        has a stable, fully interactive lifecycle. The spec explicitly ships
        that agent for frozen builds.
        """
        if not getattr(sys, "frozen", False):
            return None
        from winpty import Backend

        return Backend.WinPTY

    @staticmethod
    def _windows_shell_command(shell: str) -> list[str]:
        """Return a stable interactive command for a windowless IDE host."""
        executable = os.path.abspath(shell)
        name = os.path.basename(executable).lower()
        if name in {"powershell.exe", "pwsh.exe"}:
            # IDE terminals must not inherit profiles that can replace the
            # prompt, call exit, or send control events during startup.
            return [executable, "-NoLogo", "-NoProfile", "-NoExit"]
        if name in {"cmd.exe", "cmd"}:
            return [executable, "/Q"]
        return [executable]

    def _spawn_subprocess(
        self,
        session_id: str,
        cwd: str,
        shell: str | None = None,
    ) -> None:
        """Use a bidirectional pipe only when a native PTY is unavailable."""
        resolved_shell = shell or (
            shutil.which("powershell.exe") if sys.platform == "win32" else None
        ) or os.environ.get("SHELL", "/bin/bash")
        args = [resolved_shell]
        if sys.platform == "win32" and "powershell" in resolved_shell.lower():
            args.extend(["-NoLogo", "-NoProfile", "-NoExit"])

        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ),
        )
        self._register_process(session_id, proc, "subprocess", resolved_shell)
        self._start_reader(session_id, self._read_subprocess, proc)

    def _spawn_unix(
        self,
        session_id: str,
        cwd: str,
        cols: int,
        rows: int,
    ) -> None:
        """Spawn the user's shell through a POSIX PTY."""
        import pty

        shell = os.environ.get("SHELL", "/bin/bash")
        master_fd, slave_fd = pty.openpty()
        try:
            proc = subprocess.Popen(
                [shell],
                cwd=cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
            )
        finally:
            os.close(slave_fd)

        with self._lock:
            self._sessions[session_id]["master_fd"] = master_fd
        self._register_process(session_id, proc, "unix_pty", shell)
        self.resize(session_id, cols, rows)
        self._start_reader(session_id, self._read_unix_pty, master_fd, proc)

    def _register_process(
        self,
        session_id: str,
        proc: Any,
        session_type: str,
        shell: str,
    ) -> None:
        with self._lock:
            session = self._sessions[session_id]
            session.update({
                "process": proc,
                "type": session_type,
                "shell": os.path.basename(shell),
                "status": "running",
            })

    def _start_reader(self, session_id: str, target: Any, *args: Any) -> None:
        reader = threading.Thread(
            target=target,
            args=(session_id, *args),
            name=f"terminal-reader-{session_id}",
            daemon=True,
        )
        with self._lock:
            self._readers[session_id] = reader
        reader.start()

    def _publish_output(self, session_id: str, data: str) -> None:
        if not data:
            return
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            session["sequence"] += 1
            sequence = session["sequence"]
            chunks: deque[tuple[int, str]] = session["output_chunks"]
            chunks.append((sequence, data))
            session["output_chars"] += len(data)
            while session["output_chars"] > MAX_BACKLOG_CHARS and len(chunks) > 1:
                _, removed = chunks.popleft()
                session["output_chars"] -= len(removed)
        self.output_received.emit(session_id, data, sequence)

    # -- I/O -----------------------------------------------------------------

    def write(self, session_id: str, data: str) -> bool:
        """Write input to a running terminal. Return whether it was accepted."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session["status"] != "running":
                return False

        if self._should_block_input(session_id, data):
            self._publish_output(
                session_id,
                "\r\n\x1b[31m[NexCoder] Blocked a potentially destructive command.\x1b[0m\r\n",
            )
            return False

        proc = session["process"]
        try:
            if session["type"] == "winpty":
                proc.write(data)
            elif session["type"] == "subprocess":
                if not proc.stdin:
                    return False
                proc.stdin.write(data.encode("utf-8"))
                proc.stdin.flush()
            elif session["type"] == "unix_pty":
                os.write(session["master_fd"], data.encode("utf-8"))
            else:
                return False
            return True
        except Exception as exc:
            logger.warning("Terminal write failed for %s: %s", session_id, exc)
            return False

    def _should_block_input(self, session_id: str, data: str) -> bool:
        if "\x03" in data:
            with self._lock:
                self._command_buffers[session_id] = ""
            return False

        with self._lock:
            buffer = self._command_buffers.get(session_id, "")
            blocked = False
            for char in data:
                if char in ("\b", "\x7f"):
                    buffer = buffer[:-1]
                elif char in ("\r", "\n"):
                    command = buffer.strip().lower()
                    blocked = blocked or bool(command and self._is_blocked_command(command))
                    buffer = ""
                elif char.isprintable() or char == "\t":
                    buffer += char
            self._command_buffers[session_id] = buffer[-4096:]
            return blocked

    @staticmethod
    def _is_blocked_command(command: str) -> bool:
        return any(
            re.search(pattern, command, re.IGNORECASE)
            for pattern in BLOCKED_COMMAND_PATTERNS
        )

    def resize(self, session_id: str, cols: int, rows: int) -> bool:
        """Resize a live PTY, ignoring unusable hidden-panel dimensions."""
        safe_cols = self._safe_cols(cols)
        safe_rows = self._safe_rows(rows)
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session["status"] != "running":
                return False

        try:
            if session["type"] == "winpty":
                session["process"].setwinsize(safe_rows, safe_cols)
            elif session["type"] == "unix_pty":
                import fcntl
                import struct
                import termios

                winsize = struct.pack("HHHH", safe_rows, safe_cols, 0, 0)
                fcntl.ioctl(session["master_fd"], termios.TIOCSWINSZ, winsize)
            return True
        except Exception as exc:
            logger.debug("Terminal resize failed for %s: %s", session_id, exc)
            return False

    @staticmethod
    def _safe_cols(cols: int) -> int:
        return max(20, min(500, int(cols or DEFAULT_COLS)))

    @staticmethod
    def _safe_rows(rows: int) -> int:
        return max(5, min(200, int(rows or DEFAULT_ROWS)))

    def kill(self, session_id: str) -> bool:
        """Detach and stop a terminal session without blocking the Qt thread."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return False
            session["status"] = "closing"
            session["closing"] = True
            self._readers.pop(session_id, None)
            self._command_buffers.pop(session_id, None)

        # QWebChannel slots execute on the UI thread. pywinpty.close() can
        # wait several seconds for the hidden console host, so cleanup must
        # happen off-thread or folder switches visibly freeze and leave the
        # old terminal in an interrupted state.
        closer = threading.Thread(
            target=self._terminate_process,
            args=(session,),
            name=f"terminal-closer-{session_id}",
            daemon=True,
        )
        closer.start()
        return True

    def _terminate_process(self, session: dict[str, Any]) -> None:
        """Close one detached terminal process and all of its PTY resources."""
        proc = session.get("process")
        try:
            if proc is not None and session["type"] == "winpty":
                # Ensure the hidden ConPTY/conhost process cannot survive a
                # terminal close or project switch.
                proc.close(force=True)
            elif proc is not None and session["type"] == "subprocess":
                proc.terminate()
                proc.wait(timeout=3)
            elif proc is not None and session["type"] == "unix_pty":
                os.close(session["master_fd"])
                proc.terminate()
                proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception as exc:
            logger.debug("Terminal close failed for %s: %s", session.get("cwd"), exc)

    # -- Reader threads -------------------------------------------------------

    def _read_winpty(self, session_id: str, proc: Any) -> None:
        try:
            while self._is_readable(session_id):
                try:
                    data = proc.read(4096)
                except (EOFError, OSError):
                    break
                if not data:
                    break
                self._publish_output(session_id, data)
        except Exception as exc:
            logger.debug("ConPTY reader stopped for %s: %s", session_id, exc)
        finally:
            exit_code = self._exit_code(proc)
            # A detached session is being closed by _terminate_process. Only
            # unexpected shell exits are finalized and reported here.
            with self._lock:
                session_attached = session_id in self._sessions
            if session_attached:
                try:
                    if not getattr(proc, "closed", False):
                        proc.close(force=True)
                        exit_code = self._exit_code(proc)
                except Exception as exc:
                    logger.debug("ConPTY cleanup failed for %s: %s", session_id, exc)
            self._finalize(session_id, exit_code)

    def _read_subprocess(self, session_id: str, proc: Any) -> None:
        try:
            if not proc.stdout:
                return
            fd = proc.stdout.fileno()
            while self._is_readable(session_id):
                data = os.read(fd, 4096)
                if not data:
                    break
                self._publish_output(session_id, data.decode("utf-8", errors="replace"))
        except (EOFError, OSError):
            pass
        finally:
            try:
                code = proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                code = -1
            self._finalize(session_id, code)

    def _read_unix_pty(self, session_id: str, master_fd: int, proc: Any) -> None:
        try:
            while self._is_readable(session_id):
                data = os.read(master_fd, 4096)
                if not data:
                    break
                self._publish_output(session_id, data.decode("utf-8", errors="replace"))
        except OSError:
            pass
        finally:
            self._finalize(session_id, self._exit_code(proc))

    def _is_readable(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            return bool(session and session["status"] in {"running", "closing"})

    @staticmethod
    def _exit_code(proc: Any) -> int:
        if proc is None:
            return -1
        try:
            status = getattr(proc, "exitstatus", None)
            if status is not None:
                return int(status)
            polled = proc.poll()
            return int(polled) if polled is not None else -1
        except Exception:
            return -1

    def _finalize(self, session_id: str, exit_code: int, *, notify: bool = True) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session["status"] == "exited":
                return
            intentional_close = bool(session.get("closing"))
            session["status"] = "exited"
            session["exit_code"] = exit_code
            session["closing"] = False
            self._readers.pop(session_id, None)
            self._command_buffers.pop(session_id, None)
        if notify and not intentional_close:
            self.process_exited.emit(session_id, exit_code)

    def kill_all(self) -> None:
        """Stop all terminal processes during application shutdown."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._readers.clear()
            self._command_buffers.clear()
        # Shutdown is the one place cleanup must finish before returning;
        # otherwise conhost processes can outlive NexCoder itself.
        for session in sessions:
            session["status"] = "closing"
            session["closing"] = True
            self._terminate_process(session)
