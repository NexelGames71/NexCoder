"""AgentMode — multi-step autonomous coding mode with XML tool calling."""

import os
import re
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable

from nexcoder.agent.model_connector import ModelConnector
from nexcoder.agent.context_builder import ContextBuilder
from nexcoder.agent.patch_generator import PatchGenerator
from nexcoder.agent.safety import SafetyChecker
from nexcoder.agent.hermes_runtime import HermesAgentLoop
from nexcoder.agent.intent_router import classify_task_type
from nexcoder.agent.mode_profiles import AGENT_PROFILE
from nexcoder.services.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)

# XML Pattern to detect tool calls: <tool_call name="tool_name">JSON_ARGS</tool_call>
TOOL_CALL_PATTERN = re.compile(r'<tool_call\s+name="([^"]+)">([\s\S]*?)</tool_call>')


class AgentMode:
    """Autonomous multi-step agent mode.

    The agent uses a loop to execute tools, read files, edit code, and run commands.
    """

    def __init__(self) -> None:
        self._model = ModelConnector()
        self._context_builder = ContextBuilder()
        self._patch_gen = PatchGenerator()
        self._safety = SafetyChecker()
        self._hermes_loop = HermesAgentLoop()

    def execute(
        self,
        prompt: str,
        context: dict[str, Any],
        history: list[dict[str, str]],
        callbacks: dict[str, Callable],
    ) -> dict[str, Any]:
        """Execute agent mode in an autonomous loop."""
        on_chunk = callbacks.get("on_chunk", lambda x: None)
        on_status = callbacks.get("on_status", lambda s, m: None)
        on_diff = callbacks.get("on_diff", lambda d: None)

        project_root = context.get("projectPath") or context.get("project_path")
        if not project_root:
            raise ValueError("No active project root found in context")

        # Initialize checkpoint manager
        checkpoint_mgr = CheckpointManager(project_root)
        checkpoint_id = None
        checkpointed_files = set()
        modified_files = set()

        on_status("planning", "Analyzing task and reading files...")
        resolved_root = Path(project_root).resolve()
        if self._hermes_loop.project_root != resolved_root:
            self._hermes_loop = HermesAgentLoop(resolved_root)
        loop_context = dict(context)
        loop_context.setdefault("_mode_profile", AGENT_PROFILE)
        # Agent is a generic capability mode. Resolve the current prompt on
        # every turn so stale UI/session metadata cannot turn a question into
        # an implementation task.
        loop_context["task_type"] = classify_task_type(prompt, "agent")
        result = self._hermes_loop.run(prompt, loop_context, callbacks)

        if result.get("patches"):
            on_status("awaiting_approval", f"Prepared {result['patches']} file change(s) for review.")

        return result

    def _read_file(self, path: str, project_root: str) -> str:
        if not path:
            return json.dumps({"success": False, "error": "Missing path argument"})
        full_path = os.path.abspath(os.path.join(project_root, path))
        if not full_path.startswith(os.path.abspath(project_root)):
            return json.dumps({"success": False, "error": "Access denied: outside project root"})
        if not os.path.exists(full_path):
            return json.dumps({"success": False, "error": f"File not found: {path}"})
        if os.path.isdir(full_path):
            return json.dumps({"success": False, "error": f"Path is a directory: {path}"})
        try:
            with open(full_path, "rb") as f:
                chunk = f.read(1024)
                if b"\x00" in chunk:
                    return json.dumps({"success": False, "error": "Binary file reading blocked"})
            size = os.path.getsize(full_path)
            if size > 1024 * 1024:
                return json.dumps({"success": False, "error": "File size exceeds 1MB limit"})
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return json.dumps({"success": True, "content": content})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def _write_file(self, path: str, content: str, project_root: str) -> str:
        if not path:
            return json.dumps({"success": False, "error": "Missing path argument"})
        full_path = os.path.abspath(os.path.join(project_root, path))
        if not full_path.startswith(os.path.abspath(project_root)):
            return json.dumps({"success": False, "error": "Access denied: outside project root"})
        if self._safety.is_sensitive_file(path):
            return json.dumps({"success": False, "error": f"Security block: modifying sensitive file {path} not allowed in auto-mode."})
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return json.dumps({"success": True, "message": f"Successfully wrote file: {path}"})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def _search_grep(self, query: str, subpath: str, project_root: str) -> str:
        if not query:
            return json.dumps({"success": False, "error": "Missing query argument"})
        search_dir = os.path.abspath(os.path.join(project_root, subpath or ""))
        if not search_dir.startswith(os.path.abspath(project_root)):
            return json.dumps({"success": False, "error": "Access denied: outside project root"})
        results = []
        try:
            query_re = re.compile(query, re.IGNORECASE)
            for root, dirs, files in os.walk(search_dir):
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "venv", "__pycache__", ".nexcoder"}]
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, project_root)
                    if os.path.getsize(file_path) > 500 * 1024:
                        continue
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line_no, line in enumerate(f, 1):
                                if query_re.search(line):
                                    results.append({
                                        "file": rel_path,
                                        "line": line_no,
                                        "content": line.strip()
                                    })
                                    if len(results) >= 50:
                                        break
                    except Exception:
                        pass
                    if len(results) >= 50:
                        break
                if len(results) >= 50:
                    break
            return json.dumps({"success": True, "results": results})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def _list_directory(self, subpath: str, project_root: str) -> str:
        target_dir = os.path.abspath(os.path.join(project_root, subpath or ""))
        if not target_dir.startswith(os.path.abspath(project_root)):
            return json.dumps({"success": False, "error": "Access denied: outside project root"})
        if not os.path.exists(target_dir):
            return json.dumps({"success": False, "error": f"Directory not found: {subpath}"})
        if not os.path.isdir(target_dir):
            return json.dumps({"success": False, "error": f"Path is not a directory: {subpath}"})
        try:
            entries = []
            for name in os.listdir(target_dir):
                if name in {".git", "node_modules", "venv", "__pycache__", ".nexcoder"}:
                    continue
                full_path = os.path.join(target_dir, name)
                entries.append({
                    "name": name,
                    "type": "directory" if os.path.isdir(full_path) else "file",
                    "size": os.path.getsize(full_path) if os.path.isfile(full_path) else None
                })
            return json.dumps({"success": True, "entries": entries})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def _run_command(self, command: str, project_root: str) -> str:
        if not command:
            return json.dumps({"success": False, "error": "Missing command argument"})
        if self._safety.is_command_blocked(command):
            return json.dumps({"success": False, "error": "Blocked dangerous command"})
        try:
            result = subprocess.run(
                command,
                cwd=project_root,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )
            return json.dumps({
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            })
        except subprocess.TimeoutExpired:
            return json.dumps({"success": False, "error": "Command execution timed out (30s)"})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
