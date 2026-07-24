"""NexCoder command-line agent.

This module exposes the same v2 agentic engine used by the desktop app,
but renders progress as terminal output so agent behavior is easy to
inspect without the React panel.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

from nexcoder.agent.errors import AgentContractError, AgentError, envelope_from_exception
from nexcoder.agent.patch_generator import PatchGenerator
from nexcoder.services.checkpoint import CheckpointManager

try:  # dist metadata when installed; static fallback otherwise
    from importlib.metadata import version as _pkg_version
    APP_VERSION = _pkg_version("nexcoder")
except Exception:
    APP_VERSION = "0.1.0"


def _enable_windows_ansi() -> None:
    """Turn on virtual-terminal processing so ANSI colors render on Windows."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def configure_stdio() -> None:
    """Use UTF-8 for CLI output when the host console allows it."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _enable_windows_ansi()


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _visible_len(text: str) -> int:
    """Length of a string ignoring ANSI SGR escapes (for box alignment)."""
    return len(_ANSI_RE.sub("", text))


def _supports_color(stream: Any) -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


class _Palette:
    """Zero-dependency truecolor SGR helpers; a no-op when color is disabled."""

    def __init__(self, enabled: bool) -> None:
        self.on = enabled

    def _rgb(self, r: int, g: int, b: int, text: str, bold: bool = False) -> str:
        if not self.on:
            return text
        weight = "1;" if bold else ""
        return f"\x1b[{weight}38;2;{r};{g};{b}m{text}\x1b[0m"

    def dim(self, s: str, bold: bool = False) -> str:    return self._rgb(110, 116, 130, s, bold)
    def dim2(self, s: str, bold: bool = False) -> str:   return self._rgb(150, 157, 175, s, bold)
    def light(self, s: str, bold: bool = False) -> str:  return self._rgb(200, 208, 225, s, bold)
    def white(self, s: str, bold: bool = True) -> str:   return self._rgb(232, 236, 255, s, bold)
    def cyan(self, s: str, bold: bool = False) -> str:   return self._rgb(45, 190, 255, s, bold)
    def violet(self, s: str, bold: bool = False) -> str: return self._rgb(167, 139, 250, s, bold)
    def green(self, s: str, bold: bool = False) -> str:  return self._rgb(74, 222, 128, s, bold)
    def hashc(self, s: str, bold: bool = False) -> str:  return self._rgb(150, 135, 220, s, bold)
    def faint(self, s: str, bold: bool = False) -> str:  return self._rgb(80, 84, 100, s, bold)


def _rounded_box(rows: list[str], pal: _Palette, width: int) -> list[str]:
    """Render rows inside a rounded box padded to `width` visible columns."""
    inner = width + 2  # one space of padding on each side
    bar = pal.faint("│")
    out = [pal.faint("╭" + "─" * inner + "╮")]
    for row in rows:
        gap = max(0, width - _visible_len(row))
        out.append(f"{bar} {row}{' ' * gap} {bar}")
    out.append(pal.faint("╰" + "─" * inner + "╯"))
    return out


def _compact_path(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return path.as_posix()


def _git_branch(root: Path) -> str | None:
    try:
        head = (root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if head.startswith("ref:"):
        return head.rsplit("/", 1)[-1] or None
    return head[:7] if head else None  # detached HEAD -> short sha

STATUS_LABELS = {
    "pending": "PENDING",
    "running": "RUNNING",
    "completed": "DONE",
    "failed": "FAILED",
    "skipped": "SKIPPED",
    "blocked": "BLOCKED",
    "approval_required": "APPROVAL",
    "cancelled": "CANCELLED",
}


class ConsoleRenderer:
    """Render agent callbacks in a Claude/Hermes-style terminal timeline."""

    def __init__(self, *, verbose: bool = False, jsonl: bool = False) -> None:
        self.verbose = verbose
        self.jsonl = jsonl
        self._started_at = time.monotonic()
        self._last_chunk = ""
        self._printed_text = ""
        self.diffs: list[dict[str, Any]] = []
        self.timeline: list[dict[str, Any]] = []
        self._pal = _Palette((not jsonl) and _supports_color(sys.stdout))

    def event(self, kind: str, payload: dict[str, Any]) -> None:
        if self.jsonl:
            print(json.dumps({"event": kind, **payload}, ensure_ascii=False), flush=True)

    def header(
        self,
        prompt: str,
        project_root: Path,
        mode: str,
        *,
        model: str = "default",
        approval: str = "ask",
        host: str = "localhost",
        branch: str | None = None,
        session_id: str | None = None,
    ) -> None:
        if self.jsonl:
            self.event("start", {"prompt": prompt, "project_root": str(project_root), "mode": mode})
            return

        P = self._pal
        session_id = session_id or uuid.uuid4().hex
        cpath = _compact_path(project_root)
        cols = shutil.get_terminal_size((100, 24)).columns

        out: list[str] = [""]
        # working directory + branch
        wd = P.dim(cpath) + (f"  {P.green(branch)}" if branch else "")
        out.append(wd)
        # command echo, Codex-style prompt
        out.append(
            P.dim2("nexa ") + P.cyan(")") + " "
            + P.violet("nexcoder", bold=True) + P.light(f" --mode {mode}")
        )
        out.append("")

        # version banner
        version_row = (
            f"{P.cyan('●')} {P.white('NexCoder')}"
            f"{P.dim2('  (private beta)')}   {P.cyan('v' + APP_VERSION)}"
        )
        # session panel
        def kv(key: str, value: str) -> str:
            return f"{P.faint('└─')} {P.dim(f'{key:<9}')} {value}"

        session_rows = [
            f"{P.white(host)}  {P.dim('session:')} {P.hashc(session_id)}",
            kv("project:", P.light(cpath)),
            kv("model:", P.light(model)),
            kv("mode:", P.green(mode)),
            kv("approval:", P.cyan(approval)),
        ]

        content_width = max(
            [_visible_len(version_row)] + [_visible_len(r) for r in session_rows]
        )
        width = max(44, min(content_width, cols - 6))

        out += _rounded_box([version_row], P, width)
        out.append("")
        out += _rounded_box(session_rows, P, width)
        out.append("")

        # the task, in an input-style box
        max_task = width - 2
        task = prompt if len(prompt) <= max_task else prompt[: max_task - 1] + "…"
        out += _rounded_box([f"{P.cyan('»')} {P.light(task)}"], P, width)
        out.append("")

        hints = {
            "ask": "ctrl-c to cancel  ·  you'll be asked before each command",
            "risky-only": "ctrl-c to cancel  ·  risky commands need approval",
            "full-auto": "ctrl-c to cancel  ·  full auto — risky commands denied",
            "read-only": "ctrl-c to cancel  ·  read-only — no files will change",
        }
        out.append("  " + P.dim(hints.get(approval, "ctrl-c to cancel")))
        out.append("")

        print("\n".join(out), flush=True)

    def status(self, status: str, message: str) -> None:
        self.event("status", {"status": status, "message": message})
        if self.jsonl:
            return
        if status in {"planning", "retrying", "parsed", "synthesizing", "awaiting_approval"}:
            label = status.upper().replace("_", " ")
            print(f"[{label}] {message}", flush=True)
        elif self.verbose:
            print(f"[{status.upper()}] {message}", flush=True)

    def timeline_item(self, item: dict[str, Any]) -> None:
        self.timeline.append(dict(item))
        self.event("timeline", {"item": item})
        if self.jsonl:
            return

        status = str(item.get("status") or "")
        label = STATUS_LABELS.get(status, status.upper() or "STEP")
        title = item.get("label") or item.get("tool") or "Step"
        target = item.get("target")
        result = item.get("result_summary")
        error = item.get("error")

        line = f"[{label}] {title}"
        if target:
            line += f": {target}"
        print(line, flush=True)
        if result and status != "running":
            print(f"  {result}", flush=True)
        if error:
            print(f"  Error: {error}", flush=True)

    def chunk(self, chunk: str) -> None:
        self.event("chunk", {"content": chunk})
        if self.jsonl:
            return
        if chunk:
            if not self._last_chunk:
                print()
            print(chunk, end="", flush=True)
            self._last_chunk = chunk
            self._printed_text += chunk

    def diff(self, diff: dict[str, Any]) -> None:
        self.diffs.append(dict(diff))
        self.event("diff", {"diff": diff})
        if self.jsonl:
            return

        file_name = diff.get("file") or "(unknown file)"
        action = diff.get("action") or "modify"
        print()
        print(f"[PATCH READY] {action}: {file_name}", flush=True)
        diff_text = diff.get("diff_display") or diff.get("diff") or ""
        if diff_text:
            print(indent_block(diff_text.rstrip(), prefix="  "), flush=True)

    def result(self, result: dict[str, Any]) -> None:
        elapsed = time.monotonic() - self._started_at
        self.event("result", {"result": result, "elapsed_seconds": round(elapsed, 3)})
        if self.jsonl:
            return

        if self._last_chunk and not self._last_chunk.endswith("\n"):
            print()
        print()
        print("Result")
        print(f"  Success: {bool(result.get('success'))}")
        print(f"  Mode: {result.get('mode', 'agent')}")
        print(f"  Task type: {result.get('task_type', 'unknown')}")
        completed = len([item for item in self.timeline if item.get("status") == "completed"])
        print(f"  Completed tool steps: {completed}")
        print(f"  Patches: {len(self.diffs)}")
        print(f"  Elapsed: {elapsed:.1f}s")

        final_answer = result.get("final_answer")
        if isinstance(final_answer, dict) and final_answer.get("summary"):
            summary = str(final_answer["summary"]).strip()
            if normalize_text(summary) != normalize_text(self._printed_text):
                print()
                print(final_answer.get("title") or "Final Answer")
                print(indent_block(summary, prefix="  "))

    def error(self, exc: BaseException) -> None:
        envelope = envelope_from_exception(exc)
        self.event("error", {"error": envelope})
        if self.jsonl:
            return
        print()
        print("Agent failed")
        print(f"  Code: {envelope.get('code', 'internal_error')}")
        print(f"  Message: {envelope.get('message', str(exc))}")
        if isinstance(exc, AgentContractError) and exc.last_response:
            print()
            print("Last model response")
            print(indent_block(exc.last_response.strip(), prefix="  "))


def indent_block(text: str, *, prefix: str) -> str:
    return "\n".join(prefix + line if line else prefix.rstrip() for line in text.splitlines())


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="nexcoder-cli",
        description="Run NexCoder agent mode from the terminal.",
    )
    parser.add_argument("prompt", nargs="*", help="Task prompt. If omitted, stdin is used.")
    parser.add_argument(
        "--project",
        "--cwd",
        dest="project",
        default=".",
        help="Project root for tool execution. Defaults to current directory.",
    )
    parser.add_argument(
        "--mode",
        choices=["agent", "plan", "ask", "edit", "debug", "review",
                 "scan", "terminal"],
        default="agent",
        help="Agent mode/profile to use.",
    )
    parser.add_argument(
        "--autonomy",
        choices=["read_only", "ask", "risky_only", "full_auto"],
        default="ask",
        help="Command autonomy: read_only (inspect only), ask (prompt for "
             "every command), risky_only (prompt only for risky commands), "
             "full_auto (never prompt; risky commands denied).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply prepared full-file patches after the run succeeds.",
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Emit machine-readable JSON lines instead of formatted text.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show extra nonessential status updates.",
    )
    parser.add_argument(
        "--active-file",
        default=None,
        help="Optional active file path to include in task context.",
    )
    parser.add_argument(
        "--adapter",
        choices=["xml", "native"],
        default=None,
        help="Tool-call transport for v2. Defaults to NEXCODER_ADAPTER env (xml).",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Full auto (v2): skip command permission prompts.",
    )
    parser.add_argument(
        "--skill",
        default=None,
        help="Preload a skill by id for the v2 run (same as a /skill prompt prefix).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start interactive CLI prompt mode instead of reading a one-shot prompt.",
    )
    return parser.parse_args(argv)


def read_prompt(parts: list[str]) -> str:
    prompt = " ".join(parts).strip()
    if prompt:
        return prompt
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("No prompt provided. Pass a prompt argument or pipe one on stdin.")


def resolve_project(path: str) -> Path:
    project_root = Path(path).expanduser().resolve()
    if not project_root.exists():
        raise SystemExit(f"Project root does not exist: {project_root}")
    if not project_root.is_dir():
        raise SystemExit(f"Project root is not a directory: {project_root}")
    return project_root


def safe_apply_diffs(project_root: Path, diffs: list[dict[str, Any]]) -> list[Path]:
    """Apply a reviewed patchset atomically after project-boundary checks."""
    validated: list[dict[str, Any]] = []
    for diff in diffs:
        target = str(diff.get("file") or "")
        if not target:
            continue
        path = (project_root / target).resolve()
        try:
            common = os.path.commonpath([str(project_root), str(path)])
        except (OSError, ValueError):
            continue
        if common != str(project_root):
            continue

        source = str(diff.get("source") or "")
        if diff.get("action") == "move":
            if not source:
                continue
            source_path = (project_root / source).resolve()
            try:
                source_common = os.path.commonpath([str(project_root), str(source_path)])
            except (OSError, ValueError):
                continue
            if source_common != str(project_root):
                continue
        validated.append(dict(diff))

    if not validated:
        return []

    checkpoint_paths: list[str] = []
    for patch in validated:
        for candidate in (patch.get("file"), patch.get("source")):
            if candidate:
                absolute = str((project_root / str(candidate)).resolve())
                if absolute not in checkpoint_paths:
                    checkpoint_paths.append(absolute)

    checkpoints = CheckpointManager(str(project_root))
    checkpoint_id = checkpoints.create(checkpoint_paths, label="cli-agent-patchset")
    try:
        PatchGenerator(str(project_root)).apply_patchset(validated)
        for patch in validated:
            target = (project_root / str(patch["file"])).resolve()
            action = patch.get("action", "modify")
            if action == "mkdir":
                if not target.is_dir():
                    raise IOError(f"Directory was not created: {patch['file']}")
                continue
            if action in {"delete", "rmdir"}:
                if target.exists():
                    raise IOError(f"Path was not removed: {patch['file']}")
                continue
            if action == "move":
                source = (project_root / str(patch.get("source") or "")).resolve()
                if source.exists():
                    raise IOError(f"Move source still exists: {patch.get('source')}")
            if not target.is_file():
                raise IOError(f"File was not written: {patch['file']}")
            expected = patch.get("content")
            if isinstance(expected, str) and target.read_text(encoding="utf-8", errors="replace") != expected:
                raise IOError(f"File content verification failed: {patch['file']}")
    except Exception:
        checkpoints.restore(checkpoint_id, checkpoint_paths)
        raise

    applied = [
        (project_root / str(patch["file"])).resolve()
        for patch in validated
        if patch.get("action") not in {"mkdir", "rmdir", "delete"}
    ]
    return applied


def run_v2(args: argparse.Namespace, prompt: str, project_root: Path,
           renderer: ConsoleRenderer) -> int:
    """Run the v2 agentic core engine (direct edits, permission-gated commands)."""
    from nexcoder.agent.core.backend_config import load_backend_config
    from nexcoder.agent.core.command_policy import AutonomyGate
    from nexcoder.agent.core.loop import AgentLoop
    from nexcoder.agent.core.permissions import AllowlistGate
    from nexcoder.agent.core.profiles import build_belt_for, get_v2_profile
    from nexcoder.agent.core.project_commands import (
        detect_project_commands, render_project_commands,
    )
    from nexcoder.agent.core.rules import load_project_rules
    from nexcoder.agent.core.repo_map import build_repo_map, render_repo_map, save_repo_map
    from nexcoder.agent.core.session_store import SessionStore
    from nexcoder.agent.core.skills_catalog import render_skills_catalog
    from nexcoder.agent.core.slash import parse_slash_command
    from nexcoder.agent.core.tools.base import ALLOW, ALLOW_ALWAYS, DENY
    from nexcoder.agent.core.transport import get_adapter
    from nexcoder.agent.model_connector import AgentModelClient, ModelConnector
    from nexcoder.agent.skills_registry import get_skills

    config = load_backend_config()
    adapter_name = args.adapter or config.adapter

    known_ids = {s["id"] for s in get_skills(str(project_root))}
    skill_id, task = parse_slash_command(prompt, known_ids)
    if args.skill:
        skill_id, task = args.skill, prompt
    if args.active_file:
        from nexcoder.agent.core.editor_context import render_editor_context
        task += render_editor_context(
            {"active_file": args.active_file}, project_root)

    class ConsolePermissionGate:
        def request(self, *, tool: str, detail: str) -> str:
            print(f"\n[permission] {tool}: {detail}")
            answer = input("Allow? [y]es / [a]lways / [n]o: ").strip().lower()
            if answer in {"a", "always"}:
                return ALLOW_ALWAYS
            if answer in {"y", "yes"}:
                return ALLOW
            return DENY

    class DenyGate:
        def request(self, *, tool: str, detail: str) -> str:
            return DENY

    autonomy = "full_auto" if args.auto else args.autonomy
    if args.jsonl and autonomy == "ask":
        inner = DenyGate()  # unattended: never hang on a prompt
    else:
        inner = ConsolePermissionGate()
    gate = AllowlistGate(AutonomyGate(inner, autonomy), project_root)

    repo_map = build_repo_map(project_root)
    save_repo_map(project_root, repo_map)

    def emit(event) -> None:
        if args.jsonl:
            renderer.event(event.type, event.payload)
            return
        if event.type == "text_delta":
            print(event.payload.get("text", ""), end="", flush=True)
        elif event.type == "tool_started":
            print(f"\n> {event.payload['tool']} "
                  f"{json.dumps(event.payload.get('args', {}))[:160]}")
        elif event.type == "tool_result":
            marker = "ok" if event.payload.get("success") else "FAIL"
            print(f"  [{marker}] {event.payload.get('summary', '')}")
        elif event.type == "command_output":
            print(f"  | {event.payload.get('line', '')}")
        elif event.type == "todo_updated":
            for todo in event.payload.get("todos", []):
                mark = {"pending": " ", "in_progress": ">", "completed": "x"}[todo["status"]]
                print(f"  [{mark}] {todo['content']}")

    profile = get_v2_profile(getattr(args, "mode", "agent") or "agent")
    extra_sections = [render_repo_map(repo_map),
                      render_skills_catalog(str(project_root))]
    rules = load_project_rules(project_root)
    if rules:
        extra_sections.append(rules)
    commands = render_project_commands(detect_project_commands(project_root))
    if commands:
        extra_sections.append(commands)
    loop = AgentLoop(
        project_root=project_root,
        model=AgentModelClient(ModelConnector()),
        adapter=get_adapter(adapter_name),
        belt=build_belt_for(profile),
        system_prompt=profile.system_prompt,
        trajectory_mode=profile.name,
        emit=emit,
        permission_gate=gate,
        max_turns=profile.max_turns,
        context_window=config.context_window,
        reserve_output=config.reserve_output,
        extra_system="\n\n".join(extra_sections),
        session_store=SessionStore(project_root),
    )
    result = loop.run(task, preload_skill=skill_id)
    print(f"\n--- {result['status']} in {result['turns']} turn(s); "
          f"{len(result['mutated_files'])} file(s) changed ---")
    if result["final_text"]:
        print(result["final_text"])
    return 0 if result["success"] else 1


def run_cli_interactive(args: argparse.Namespace, project_root: Path,
                         renderer: ConsoleRenderer) -> int:
    print("NexCoder CLI interactive mode.")
    print("Type a prompt and press Enter. Type 'quit' or 'exit' to stop.")

    while True:
        try:
            prompt = input("nexcoder> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

        if not prompt:
            continue
        if prompt.lower() in {"quit", "exit"}:
            return 0

        approval = "full-auto" if args.auto else {
            "read_only": "read-only",
            "ask": "ask",
            "risky_only": "risky-only",
            "full_auto": "full-auto",
        }.get(args.autonomy, args.autonomy)
        host = urlparse(os.getenv("NEXA_API_URL", "https://integrate.api.nvidia.com/v1")).hostname
        if host in {"127.0.0.1", "0.0.0.0", None}:
            host = "localhost"

        renderer.header(
            prompt,
            project_root,
            args.mode,
            model=os.getenv("NEXA_MODEL", "default"),
            approval=approval,
            host=host,
            branch=_git_branch(project_root),
        )

        try:
            run_v2(args, prompt, project_root, renderer)
        except Exception as exc:
            renderer.error(exc)

    return 0


def run_cli(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    project_root = resolve_project(args.project)

    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(project_root / ".env", override=False)

    renderer = ConsoleRenderer(verbose=args.verbose, jsonl=args.jsonl)

    if args.interactive or (not args.prompt and sys.stdin.isatty()):
        return run_cli_interactive(args, project_root, renderer)

    prompt = read_prompt(args.prompt)

    approval = "full-auto" if args.auto else {
        "read_only": "read-only",
        "ask": "ask",
        "risky_only": "risky-only",
        "full_auto": "full-auto",
    }.get(args.autonomy, args.autonomy)
    host = urlparse(os.getenv("NEXA_API_URL", "https://integrate.api.nvidia.com/v1")).hostname
    if host in {"127.0.0.1", "0.0.0.0", None}:
        host = "localhost"
    renderer.header(
        prompt,
        project_root,
        args.mode,
        model=os.getenv("NEXA_MODEL", "default"),
        approval=approval,
        host=host,
        branch=_git_branch(project_root),
    )

    try:
        return run_v2(args, prompt, project_root, renderer)
    except Exception as exc:
        renderer.error(exc)
        return 1


def main(argv: list[str] | None = None) -> None:
    raise SystemExit(run_cli(argv))


if __name__ == "__main__":
    main()

