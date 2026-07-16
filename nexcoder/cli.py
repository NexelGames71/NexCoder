"""NexCoder command-line agent.

This module exposes the same Hermes agent loop used by the desktop app,
but renders progress as terminal output so agent behavior is easy to
inspect without the React panel.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from nexcoder.agent.errors import AgentContractError, AgentError, envelope_from_exception
from nexcoder.agent.hermes_runtime import HermesAgentLoop
from nexcoder.agent.mode_profiles import get_profile
from nexcoder.agent.patch_generator import PatchGenerator
from nexcoder.services.checkpoint import CheckpointManager


def configure_stdio() -> None:
    """Use UTF-8 for CLI output when the host console allows it."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

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

    def event(self, kind: str, payload: dict[str, Any]) -> None:
        if self.jsonl:
            print(json.dumps({"event": kind, **payload}, ensure_ascii=False), flush=True)

    def header(self, prompt: str, project_root: Path, mode: str) -> None:
        if self.jsonl:
            self.event("start", {"prompt": prompt, "project_root": str(project_root), "mode": mode})
            return
        print("NexCoder CLI")
        print(f"Project: {project_root}")
        print(f"Mode: {mode}")
        print(f"Task: {prompt}")
        print()

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
        choices=["agent", "ask", "edit", "debug", "review", "scan"],
        default="agent",
        help="Agent mode/profile to use.",
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
        "--engine",
        choices=["v1", "v2"],
        default=os.getenv("NEXCODER_ENGINE", "v2"),
        help="Agent engine: v1 (legacy Hermes loop) or v2 (agentic core).",
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
    from nexcoder.agent.core.loop import AgentLoop
    from nexcoder.agent.core.permissions import AllowlistGate, FullAutoGate
    from nexcoder.agent.core.profiles import build_belt_for, get_v2_profile
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

    if args.auto:
        gate = FullAutoGate()
    elif args.jsonl:
        gate = AllowlistGate(DenyGate(), project_root)  # unattended: never hang
    else:
        gate = AllowlistGate(ConsolePermissionGate(), project_root)

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
        extra_system=(render_repo_map(repo_map) + "\n\n"
                      + render_skills_catalog(str(project_root))),
        session_store=SessionStore(project_root),
    )
    result = loop.run(task, preload_skill=skill_id)
    print(f"\n--- {result['status']} in {result['turns']} turn(s); "
          f"{len(result['mutated_files'])} file(s) changed ---")
    if result["final_text"]:
        print(result["final_text"])
    return 0 if result["success"] else 1


def run_cli(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    prompt = read_prompt(args.prompt)
    project_root = resolve_project(args.project)

    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(project_root / ".env", override=False)

    renderer = ConsoleRenderer(verbose=args.verbose, jsonl=args.jsonl)
    renderer.header(prompt, project_root, args.mode)

    if args.engine == "v2":
        try:
            return run_v2(args, prompt, project_root, renderer)
        except Exception as exc:
            renderer.error(exc)
            return 1

    context: dict[str, Any] = {
        "project_path": str(project_root),
        "projectPath": str(project_root),
        "mode": args.mode,
    }
    if args.active_file:
        context["currentFile"] = args.active_file
        context["current_file"] = args.active_file

    try:
        profile = get_profile(args.mode)
        context["_mode_profile"] = profile
        context["task_type"] = profile.task_type

        result = HermesAgentLoop(project_root).run(
            prompt,
            context,
            {
                "on_status": renderer.status,
                "on_timeline": renderer.timeline_item,
                "on_chunk": renderer.chunk,
                "on_diff": renderer.diff,
            },
        )
        renderer.result(result)

        if args.apply and renderer.diffs:
            applied = safe_apply_diffs(project_root, renderer.diffs)
            if args.jsonl:
                renderer.event("apply", {"files": [str(path) for path in applied]})
            else:
                print()
                if applied:
                    print("Applied files")
                    for path in applied:
                        print(f"  {path.relative_to(project_root).as_posix()}")
                else:
                    print("No applicable full-file patch payloads were produced.")

        return 0 if result.get("success") else 1
    except (AgentError, Exception) as exc:
        renderer.error(exc)
        return 1


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()

