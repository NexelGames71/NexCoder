"""TerminalHandler — PTY management for integrated terminal sessions."""

import os
import re
import sys
import uuid
import logging
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# Dangerous commands that should be blocked
BLOCKED_COMMAND_PATTERNS = [
    r"\bformat\b",
    r"\bdiskpart\b",
    r"rm\s+-rf\s+/(?:\s|$|\*)",
    r"del\s+/s\s+/q\s+[a-z]:\\",
    r"rd\s+/s\s+/q\s+[a-z]:\\",
    r":\(\)\{.*\|.*&\}",
]


class TerminalHandler(QObject):
    """Manages PTY terminal sessions, relaying I/O to xterm.js via signals."""

    output_received = Signal(str, str)   # session_id, data
    process_exited = Signal(str, int)    # session_id, exit_code

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, Any] = {}
        self._readers: dict[str, threading.Thread] = {}
        self._command_buffers: dict[str, str] = {}

    def spawn(self, cwd: str) -> str:
        """Spawn a new PTY session. Returns session_id."""
        session_id = str(uuid.uuid4())[:8]

        if sys.platform == "win32":
            self._spawn_windows(session_id, cwd)
        else:
            self._spawn_unix(session_id, cwd)

        return session_id

    def _spawn_windows(self, session_id: str, cwd: str) -> None:
        """Spawn a Windows PTY using pywinpty."""
        try:
            from winpty import PtyProcess
        except ImportError:
            # Fallback: try pywinpty
            try:
                import winpty
                PtyProcess = winpty.PtyProcess
            except ImportError:
                # Ultimate fallback: subprocess
                self._spawn_subprocess(session_id, cwd)
                return

        shell = os.environ.get("COMSPEC", "powershell.exe")
        if "powershell" not in shell.lower():
            shell = "powershell.exe"

        try:
            proc = PtyProcess.spawn(shell, cwd=cwd)
            self._sessions[session_id] = {
                "process": proc,
                "type": "winpty",
                "cwd": cwd,
            }
            self._command_buffers[session_id] = ""

            # Start reader thread
            reader = threading.Thread(
                target=self._read_winpty, args=(session_id, proc), daemon=True
            )
            self._readers[session_id] = reader
            reader.start()

        except Exception as e:
            logger.error(f"Failed to spawn winpty: {e}")
            self._spawn_subprocess(session_id, cwd)

    def _spawn_subprocess(self, session_id: str, cwd: str) -> None:
        """Fallback: spawn terminal via subprocess (no full PTY)."""
        import subprocess

        shell = "powershell.exe" if sys.platform == "win32" else "/bin/bash"
        try:
            proc = subprocess.Popen(
                [shell],
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self._sessions[session_id] = {
                "process": proc,
                "type": "subprocess",
                "cwd": cwd,
            }
            self._command_buffers[session_id] = ""

            reader = threading.Thread(
                target=self._read_subprocess, args=(session_id, proc), daemon=True
            )
            self._readers[session_id] = reader
            reader.start()

        except Exception as e:
            logger.error(f"Failed to spawn subprocess terminal: {e}")
            raise

    def _spawn_unix(self, session_id: str, cwd: str) -> None:
        """Spawn a Unix PTY."""
        import pty
        import subprocess

        shell = os.environ.get("SHELL", "/bin/bash")
        master_fd, slave_fd = pty.openpty()

        proc = subprocess.Popen(
            [shell],
            cwd=cwd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
        )

        os.close(slave_fd)

        self._sessions[session_id] = {
            "process": proc,
            "master_fd": master_fd,
            "type": "unix_pty",
            "cwd": cwd,
        }
        self._command_buffers[session_id] = ""

        reader = threading.Thread(
            target=self._read_unix_pty, args=(session_id, master_fd, proc), daemon=True
        )
        self._readers[session_id] = reader
        reader.start()

    # ── I/O ───────────────────────────────────────────────────────────

    def write(self, session_id: str, data: str) -> None:
        """Write data to a terminal session."""
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"Terminal session not found: {session_id}")
            return

        if self._should_block_input(session_id, data):
            self.output_received.emit(
                session_id,
                "\r\n[NexCoder] Blocked potentially destructive terminal command.\r\n",
            )
            return

        session_type = session["type"]
        proc = session["process"]

        try:
            if session_type == "winpty":
                proc.write(data)
            elif session_type == "subprocess":
                if proc.stdin:
                    proc.stdin.write(data.encode("utf-8"))
                    proc.stdin.flush()
            elif session_type == "unix_pty":
                os.write(session["master_fd"], data.encode("utf-8"))
        except Exception as e:
            logger.error(f"Terminal write error ({session_id}): {e}")

    def _should_block_input(self, session_id: str, data: str) -> bool:
        """Track typed input and block known destructive commands on submit."""
        if "\x03" in data:
            self._command_buffers[session_id] = ""
            return False

        buffer = self._command_buffers.get(session_id, "")
        blocked = False
        for char in data:
            if char in ("\b", "\x7f"):
                buffer = buffer[:-1]
            elif char in ("\r", "\n"):
                command = buffer.strip().lower()
                if command and self._is_blocked_command(command):
                    blocked = True
                buffer = ""
            elif char.isprintable() or char == "\t":
                buffer += char

        self._command_buffers[session_id] = buffer[-4096:]
        return blocked

    @staticmethod
    def _is_blocked_command(command: str) -> bool:
        return any(re.search(pattern, command, re.IGNORECASE) for pattern in BLOCKED_COMMAND_PATTERNS)

    def resize(self, session_id: str, cols: int, rows: int) -> None:
        """Resize a terminal session."""
        session = self._sessions.get(session_id)
        if not session:
            return

        try:
            if session["type"] == "winpty":
                session["process"].setwinsize(rows, cols)
            elif session["type"] == "unix_pty":
                import fcntl
                import struct
                import termios
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(session["master_fd"], termios.TIOCSWINSZ, winsize)
        except Exception as e:
            logger.debug(f"Terminal resize error ({session_id}): {e}")

    def kill(self, session_id: str) -> None:
        """Kill a terminal session."""
        session = self._sessions.pop(session_id, None)
        if not session:
            return

        try:
            proc = session["process"]
            if session["type"] == "winpty":
                proc.close()
            elif session["type"] == "subprocess":
                proc.terminate()
                proc.wait(timeout=3)
            elif session["type"] == "unix_pty":
                os.close(session["master_fd"])
                proc.terminate()
                proc.wait(timeout=3)
        except Exception as e:
            logger.debug(f"Terminal kill error ({session_id}): {e}")

        self._readers.pop(session_id, None)
        self._command_buffers.pop(session_id, None)

    # ── Reader Threads ────────────────────────────────────────────────

    def _read_winpty(self, session_id: str, proc: Any) -> None:
        """Read output from a winpty process."""
        try:
            while session_id in self._sessions:
                try:
                    data = proc.read(4096)
                    if data:
                        self.output_received.emit(session_id, data)
                    else:
                        break
                except EOFError:
                    break
                except Exception:
                    break
        finally:
            exit_code = proc.exitstatus if hasattr(proc, "exitstatus") else -1
            self.process_exited.emit(session_id, exit_code or 0)
            self._sessions.pop(session_id, None)
            self._command_buffers.pop(session_id, None)

    def _read_subprocess(self, session_id: str, proc: Any) -> None:
        """Read output from a subprocess."""
        try:
            while session_id in self._sessions:
                data = proc.stdout.read(4096)
                if data:
                    self.output_received.emit(session_id, data.decode("utf-8", errors="replace"))
                else:
                    break
        finally:
            exit_code = proc.wait()
            self.process_exited.emit(session_id, exit_code)
            self._sessions.pop(session_id, None)
            self._command_buffers.pop(session_id, None)

    def _read_unix_pty(self, session_id: str, master_fd: int, proc: Any) -> None:
        """Read output from a Unix PTY."""
        try:
            while session_id in self._sessions:
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        self.output_received.emit(session_id, data.decode("utf-8", errors="replace"))
                    else:
                        break
                except OSError:
                    break
        finally:
            exit_code = proc.wait()
            self.process_exited.emit(session_id, exit_code)
            self._sessions.pop(session_id, None)
            self._command_buffers.pop(session_id, None)

    def kill_all(self) -> None:
        """Kill all terminal sessions (for cleanup on app exit)."""
        for session_id in list(self._sessions.keys()):
            self.kill(session_id)
