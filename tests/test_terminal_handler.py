"""Integrated terminal lifecycle and recovery tests."""

from __future__ import annotations

import os
import sys
import time

import pytest

from nexcoder.ipc.terminal import TerminalHandler


def wait_until(predicate, timeout: float = 6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def snapshot_text(handler: TerminalHandler, session_id: str) -> str:
    snapshot = handler.snapshot(session_id)
    if not snapshot:
        return ""
    return "".join(chunk["data"] for chunk in snapshot["chunks"])


@pytest.mark.skipif(sys.platform != "win32", reason="Validates the Windows ConPTY runtime")
def test_windows_terminal_streams_and_recovers_output(tmp_path):
    handler = TerminalHandler()
    emitted_sequences: list[int] = []
    handler.output_received.connect(
        lambda _sid, _data, sequence: emitted_sequences.append(sequence)
    )
    session_id = handler.spawn(str(tmp_path), cols=100, rows=24)

    try:
        assert wait_until(lambda: bool(snapshot_text(handler, session_id)))
        initial = handler.snapshot(session_id)
        assert initial is not None
        assert initial["status"] == "running"
        assert initial["cwd"] == os.path.abspath(tmp_path)
        assert initial["shell"].lower() in {"powershell.exe", "pwsh.exe", "cmd.exe"}

        assert handler.write(session_id, "Write-Output 'NEXCODER_PTY_OK'\r")
        assert wait_until(lambda: "NEXCODER_PTY_OK" in snapshot_text(handler, session_id))
        recovered = handler.snapshot(session_id)
        assert recovered is not None
        assert recovered["chunks"]
        sequences = [chunk["sequence"] for chunk in recovered["chunks"]]
        assert sequences == sorted(set(sequences))
        assert emitted_sequences == sorted(set(emitted_sequences))
        assert handler.resize(session_id, 132, 36)
    finally:
        assert handler.kill(session_id)

    assert handler.snapshot(session_id) is None
    assert not handler.kill(session_id)


@pytest.mark.skipif(sys.platform != "win32", reason="Validates Windows shell startup")
def test_windows_shell_is_profile_independent_and_interactive():
    command = TerminalHandler._windows_shell_command(
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    )
    assert command[1:] == ["-NoLogo", "-NoProfile", "-NoExit"]


@pytest.mark.skipif(sys.platform != "win32", reason="Validates frozen PTY selection")
def test_frozen_windows_build_uses_packaged_winpty_agent(monkeypatch):
    from winpty import Backend

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert TerminalHandler._windows_pty_backend() == Backend.WinPTY


@pytest.mark.skipif(sys.platform != "win32", reason="Validates source PTY selection")
def test_source_windows_build_uses_default_conpty(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert TerminalHandler._windows_pty_backend() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Validates Windows ConPTY cleanup")
def test_explicit_terminal_close_does_not_report_a_process_failure(tmp_path):
    handler = TerminalHandler()
    exits: list[tuple[str, int]] = []
    handler.process_exited.connect(lambda sid, code: exits.append((sid, code)))
    session_id = handler.spawn(str(tmp_path))
    process = handler._sessions[session_id]["process"]

    assert wait_until(lambda: bool(snapshot_text(handler, session_id)))
    assert handler.kill(session_id)

    assert exits == []
    assert handler.snapshot(session_id) is None
    assert wait_until(lambda: process.closed)


@pytest.mark.skipif(sys.platform != "win32", reason="Validates Windows ConPTY cleanup")
def test_shell_exit_is_reported_and_conpty_is_closed(tmp_path):
    handler = TerminalHandler()
    exits: list[tuple[str, int]] = []
    handler.process_exited.connect(lambda sid, code: exits.append((sid, code)))
    session_id = handler.spawn(str(tmp_path))
    process = handler._sessions[session_id]["process"]

    assert wait_until(lambda: "PS " in snapshot_text(handler, session_id))
    assert handler.write(session_id, "exit\r")
    assert wait_until(
        lambda: (handler.snapshot(session_id) or {}).get("status") == "exited"
    )

    assert process.closed
    assert handler.kill(session_id)


def test_invalid_terminal_working_directory_is_rejected(tmp_path):
    handler = TerminalHandler()
    with pytest.raises(NotADirectoryError):
        handler.spawn(str(tmp_path / "missing"))


@pytest.mark.parametrize(
    "command",
    [
        "diskpart",
        "format C:",
        "del /s /q c:\\",
        "rm -rf /",
    ],
)
def test_destructive_commands_are_classified(command):
    assert TerminalHandler._is_blocked_command(command)


@pytest.mark.parametrize("command", ["git status", "npm test", "Remove-Item README.md"])
def test_normal_development_commands_are_allowed(command):
    assert not TerminalHandler._is_blocked_command(command)
