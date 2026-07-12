"""run_command: permission-gated, blocklist-checked, streaming shell tool."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from typing import Any
import uuid

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ALLOW, ToolBelt, ToolContext, ToolSpec

DEFAULT_TIMEOUT = 180.0
TAIL_CHARS = 8000

_SINGLE_QUOTED = re.compile(r"'([^']*)'")


def windows_normalize_quotes(command: str) -> str:
    """cmd.exe has no single-quote semantics, but LLMs emit POSIX quoting.

    Convert paired single-quoted segments to double quotes in the
    unambiguous case: the command contains no double quotes and an even
    number of single quotes. Lone apostrophes (don't) are left alone.
    """
    if '"' in command or command.count("'") < 2 or command.count("'") % 2 != 0:
        return command
    return _SINGLE_QUOTED.sub(
        lambda match: '"' + match.group(1) + '"', command)


def run_command(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    command = str(args.get("command") or "").strip()
    if not command:
        return {"success": False, "error_code": "invalid_args", "error": "Missing command"}
    if os.name == "nt":
        command = windows_normalize_quotes(command)
    if ctx.safety.is_command_blocked(command):
        return {"success": False, "error_code": "tool_command_blocked",
                "error": "Blocked dangerous command"}

    request_id = f"perm_{uuid.uuid4().hex[:8]}"
    ctx.emit(AgentEvent("permission_request", {
        "id": request_id, "tool": "run_command", "command": command}))
    decision = ctx.permission_gate.request(tool="run_command", detail=command)
    ctx.emit(AgentEvent("permission_resolved", {
        "id": request_id, "decision": decision}))
    if decision != ALLOW:
        return {"success": False, "error_code": "permission_denied",
                "error": "User denied permission to run this command. "
                         "Ask for an alternative or continue without it."}

    timeout = float(args.get("timeout") or DEFAULT_TIMEOUT)
    try:
        proc = subprocess.Popen(
            command, cwd=str(ctx.project_root), shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"success": False, "error_code": "tool_command_failed", "error": str(exc)}

    chunks: dict[str, list[str]] = {"stdout": [], "stderr": []}

    def pump(stream, name: str) -> None:
        for line in iter(stream.readline, ""):
            chunks[name].append(line)
            ctx.emit(AgentEvent("command_output", {
                "stream": name, "line": line.rstrip("\r\n"), "command": command}))
        stream.close()

    threads = [threading.Thread(target=pump, args=(proc.stdout, "stdout"), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, "stderr"), daemon=True)]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout
    while proc.poll() is None:
        if time.monotonic() > deadline:
            proc.kill()
            for thread in threads:
                thread.join(timeout=2)
            return {"success": False, "error_code": "tool_timeout",
                    "error": f"Command exceeded {timeout:.0f}s timeout",
                    "stdout": "".join(chunks["stdout"])[-TAIL_CHARS:],
                    "stderr": "".join(chunks["stderr"])[-TAIL_CHARS:]}
        time.sleep(0.1)
    for thread in threads:
        thread.join(timeout=5)

    stdout = "".join(chunks["stdout"])
    stderr = "".join(chunks["stderr"])
    return {"success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout[-TAIL_CHARS:], "stderr": stderr[-TAIL_CHARS:],
            "message": f"Command exited with code {proc.returncode}"}


def register_shell_tool(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="run_command",
        description=("Run a shell command in the project root. Use for builds, "
                     "tests, and verification. Output is streamed and returned."),
        parameters={"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "number", "description": "Seconds, default 180"}},
            "required": ["command"]},
        handler=run_command, mutating=True))
