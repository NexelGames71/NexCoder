"""Hermes-inspired coding-agent runtime for NexCoder.

This module adds a more production-like agent loop that:
- parses tool calls from LLM output,
- performs repository-aware file inspection and edits,
- runs verification commands,
- streams progress updates back to the frontend.
"""

from __future__ import annotations

import json
import logging
import os
import posixpath
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from nexcoder.agent.context_builder import ContextBuilder
from nexcoder.agent.context.token_builder import TokenAwareContextBuilder
from nexcoder.agent.executor import AgentExecutor
from nexcoder.agent.file_structure_planner import FileMove, plan_file_moves
from nexcoder.agent.final_answer import (
    FINAL_ANSWER_CLOSE,
    FINAL_ANSWER_OPEN,
    extract_final_answer_object,
    synthesize_from_observations,
)
from nexcoder.agent.intent_router import (
    Intent,
    TaskType,
    allows_direct_reply,
    classify_prompt,
    classify_task_type,
    requires_file_changes,
    task_type_requires_final_answer,
)
from nexcoder.agent.model_connector import ModelConnector
from nexcoder.agent.mode_profiles import READ_TOOLS
from nexcoder.agent.patch_generator import PatchGenerator
from nexcoder.agent.path_filters import should_skip_dir
from nexcoder.agent.permission_policy import PermissionPolicy
from nexcoder.agent.safety import SafetyChecker
from nexcoder.agent.skills_registry import get_skill_body, get_skill
from nexcoder.agent.tool_call_parser import (
    TOOL_CALL_PATTERN,
    ParsedToolCall,
    ToolCallParseError,
    parse_tool_calls,
    strip_tool_calls,
)
from nexcoder.agent.tool_registry import ToolRegistry
from nexcoder.agent.task_plan import TaskPlanTracker
from nexcoder.services.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".toml", ".txt", ".css", ".html"}
REQUESTED_FILE_PATTERN = re.compile(
    r"(?<![\w./-])([A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)*\."
    r"(?:py|ts|tsx|js|jsx|mjs|cjs|html|css|scss|md|json|toml|yaml|yml|txt))"
    r"(?=$|[\s,;:!?()\[\]{}'\"]|\.(?:\s|$))",
    re.IGNORECASE,
)


def _strip_tool_call_xml(text: str) -> str:
    """Return ``text`` with any ``<tool_call ...>...</tool_call>`` blocks removed.

    The user should never see raw tool-call XML in the chat pane; the
    loop parses the XML, dispatches the tool, and streams the model's
    prose to the UI. Any prose that appears *before*, *after*, or
    *between* tool calls is preserved.
    """
    if not text:
        return text
    return strip_tool_calls(text)


def _observation_records(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert the loop's observation log into the shape expected by
    :func:`synthesize_from_observations`.

    The loop records each tool call as
    ``{"tool": str, "args": dict, "observation": <JSON string>}``. The
    final-answer helper expects ``{"tool", "args", "result": dict}``,
    so this function parses the observation string and normalises
    the result envelope.
    """
    records: list[dict[str, Any]] = []
    for item in observations or []:
        tool = item.get("tool") or ""
        args = item.get("args") or {}
        observation_raw = item.get("observation") or ""
        result: dict[str, Any] = {"success": False, "error": "Observation could not be parsed"}
        if isinstance(observation_raw, str) and observation_raw:
            try:
                parsed = json.loads(observation_raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                # The executor wraps tool results as
                # ``{"tool", "args", "result": {...}}``. Pull the inner
                # ``result`` when present, otherwise use the parsed
                # dict as-is.
                inner = parsed.get("result")
                if isinstance(inner, dict):
                    result = inner
                else:
                    result = parsed
            else:
                # Plain text observation â€” treat as a successful result
                # so the synthesis pass can use it.
                result = {"success": True, "content": observation_raw}
        elif isinstance(observation_raw, dict):
            result = observation_raw
        records.append({"tool": tool, "args": args, "result": result})
    return records


def _response_has_final_answer(text: str) -> bool:
    """True when *text* already contains a final-answer block we can use."""
    if not text:
        return False
    return FINAL_ANSWER_OPEN in text and FINAL_ANSWER_CLOSE in text


class HermesAgentLoop:
    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root).resolve() if project_root else None
        self._model = ModelConnector()
        # The token-aware builder is the production default â€” it fits
        # the model's window, ranks related files by keyword overlap,
        # and caps per-block size. Callers can replace
        # ``self._context_builder`` with a legacy
        # :class:`ContextBuilder` if they want the old behaviour.
        self._context_builder: Any = TokenAwareContextBuilder()
        self._patch_gen = PatchGenerator(str(project_root) if project_root else None)
        self._safety = SafetyChecker()

    def extract_tool_calls(self, response: str) -> list[dict[str, Any]]:
        return [{"name": call.tool, "args": call.args} for call in parse_tool_calls(response)]

    def extract_patch_output(self, response: str) -> list[dict[str, Any]]:
        """Extract patch objects from a response that contains diff output."""
        return self._patch_gen.parse_response(response)

    def should_retry_with_tool_prompt(self, response: str) -> bool:
        """Decide whether the model should be asked again with a stricter tool-only prompt."""
        if self.extract_tool_calls(response):
            return False
        if self.extract_patch_output(response):
            return False
        return True

    def retry_tool_call_message(self) -> str:
        return (
            "Your previous response did not include explicit tool call XML or diff output. "
            "Respond only with one or more <tool_call name=\"...\">...</tool_call> blocks or with diff output in ```diff blocks. "
            "Do not include any explanatory prose outside those constructs."
        )

    def prefill_first_tool_call(self) -> str:
        """Assistant-turn prefix that forces the model to continue a tool call.

        Used on retry attempts so the model physically cannot start with
        prose â€” it must continue from a ``<tool_call>`` block. The model is
        then expected to emit a closing ``</tool_call>`` and any following
        tool calls or final output.
        """
        return '<tool_call name="list_directory">{"path":"."}</tool_call>'

    def tool_args_or_error(self, response_text: str) -> tuple[list[ParsedToolCall], str | None]:
        """Extract tool calls or return a parse error message.

        Unlike :meth:`extract_tool_calls` this method never raises â€” it
        returns a human-readable error string that the runner can feed back
        to the model on the next turn. The loop calls this to keep the
        turn-flow resilient to malformed XML.
        """
        try:
            return parse_tool_calls(response_text), None
        except ToolCallParseError as exc:
            return [], str(exc)

    def tool_contract_message(
        self,
        prompt: str,
        intent: Intent = "write",
        task_type: TaskType | None = None,
    ) -> str:
        task_type = task_type or ("read" if intent == "read" else "implement")
        if task_type in {"question", "scan", "review"}:
            guidance = (
                "You are answering a question about the codebase. "
                "Use read_file, search_grep, or list_directory when you need facts from the project. "
                "For simple questions you can answer from the provided context without tools. "
                "When you have enough information, provide a concise final summary."
            )
            tool_rule = (
                "5. You may answer directly if the project context already contains the answer. "
                "Otherwise inspect files before summarizing."
            )
            if task_type == "scan":
                guidance = (
                    "You are producing a project overview. "
                    "Use list_directory first, then read_file on the key source/config/docs files "
                    "(README.md, package.json, pyproject.toml, main entry points). "
                    "Do NOT make changes â€” only inspect and summarize."
                )
            elif task_type == "review":
                guidance = (
                    "You are producing a code review. "
                    "Read the relevant files, search for call sites, and produce a structured review."
                )
            # All read-only task types must end with a final_answer object
            # inside the FINAL_ANSWER tags. The system already enforces
            # this contract, but echoing it here makes the model produce
            # a usable object on the first try.
            tool_rule = (
                f"{tool_rule}\n"
                f"6. After you have enough information, respond with a final_answer object "
                f"inside {FINAL_ANSWER_OPEN}...{FINAL_ANSWER_CLOSE} tags. "
                f"Use the shape: "
                f'{{"type":"final_answer","title":"...","summary":"...","evidence":["..."],'
                f'"files_used":["..."],"next_steps":["..."]}}. '
                f"Do not emit any tool calls inside the tags."
            )
        else:
            guidance = (
                "You are operating in AGENT mode. Plan the work, use tools to inspect and modify the project, "
                "then verify changes when possible."
            )
            tool_rule = (
                "5. For create/edit/build/reorganization tasks you MUST call write_file, create_directory, or move_path before finishing. "
                "Do not mark the task complete with prose alone.\n"
                "6. Complete the entire requested task in this run. If multiple files are requested, "
                "stage every file before the final response; do not stop after the first write and do not ask the user to say continue.\n"
                "7. Batch independent tool calls in one response when possible. Before finishing, compare the staged files "
                "against every explicit requirement and correct incomplete or placeholder work.\n"
                "8. For file organization, inspect the current tree, choose conventional purpose-based folders, create them with "
                "create_directory, move existing or staged files with move_path, then update imports, links, scripts, and documentation "
                "with write_file. Do not duplicate a file to simulate a move."
            )

        return (
            f"Task: {prompt}\n\n"
            f"{guidance}\n\n"
            "Available tools:\n"
            "- <tool_call name=\"list_directory\">{\"path\":\".\"}</tool_call>\n"
            "- <tool_call name=\"read_file\">{\"path\":\"relative/path.ext\"}</tool_call>\n"
            "- <tool_call name=\"search_grep\">{\"query\":\"text or regex\",\"path\":\".\"}</tool_call>\n"
            "- <tool_call name=\"write_file\">{\"path\":\"relative/path.ext\",\"content\":\"full file content\"}</tool_call>\n"
            "- <tool_call name=\"create_directory\">{\"path\":\"relative/folder\"}</tool_call>\n"
            "- <tool_call name=\"move_path\">{\"source\":\"old/path.ext\",\"destination\":\"new/path.ext\"}</tool_call>\n"
            "- <tool_call name=\"run_command\">{\"command\":\"npm.cmd run build\"}</tool_call>\n"
            "- <tool_call name=\"load_skill\">{\"id\":\"test-driven-development\"}</tool_call>\n\n"
            "Rules:\n"
            "1. For scan/overview tasks, list the project, read key source/config/docs files, then provide a concise final summary.\n"
            "2. For edit/build/fix/reorganization tasks, inspect relevant files before staging writes or structural operations. All write_file, create_directory, and move_path calls prepare review changes; do not run verification until the user accepts them.\n"
            "3. Never fabricate file contents. If you need information, call read_file or search_grep.\n"
            "4. When a relevant skill exists (e.g. test-driven-development for test work, security-and-hardening for auth code), call load_skill with its id and follow the guidance it returns.\n"
            f"{tool_rule}"
        )

    def extract_requested_files(self, prompt: str) -> list[str]:
        """Extract explicit source/config/doc deliverables from a task."""
        matches = [
            match.group(1).replace("\\", "/")
            for match in REQUESTED_FILE_PATTERN.finditer(prompt or "")
        ]
        folder_match = re.search(
            r"(?:new\s+)?(?:folder|directory)\s+(?:named|called)\s*:?\s*`?([A-Za-z0-9_.-]+)`?",
            prompt or "",
            re.IGNORECASE,
        )
        inside_match = re.search(
            r"inside\s+(?:that|the)\s+(?:folder|directory).*?"
            r"create\s+(?:these|the following)\s+files\s*:(.*?)"
            r"(?=\n\s*(?:website\s+requirements|requirements|agent\s+behavior|final\s+response)\s*:|\Z)",
            prompt or "",
            re.IGNORECASE | re.DOTALL,
        )
        inside_files = {
            match.group(1).replace("\\", "/").lower()
            for match in REQUESTED_FILE_PATTERN.finditer(inside_match.group(1) if inside_match else "")
        }

        requested: list[str] = []
        seen: set[str] = set()
        for path in matches:
            normalized = path
            if folder_match and inside_files and path.lower() in inside_files and "/" not in path:
                normalized = f"{folder_match.group(1)}/{path}"
            key = normalized.lower()
            if key not in seen:
                requested.append(normalized)
                seen.add(key)
        return requested

    @staticmethod
    def missing_requested_files(requested: list[str], modified_files: set[str]) -> list[str]:
        staged = {path.replace("\\", "/").lower() for path in modified_files}
        return [path for path in requested if path.lower() not in staged]

    @staticmethod
    def frontend_quality_guidance(prompt: str) -> str:
        lower = (prompt or "").lower()
        if not any(token in lower for token in ("website", "web page", "landing page", "html", "css", "frontend", "ui")):
            return ""
        return (
            "Frontend quality bar: implement a coherent visual system rather than browser-default styling. "
            "Use purposeful typography, spacing, color, responsive behavior, accessible controls, realistic copy, "
            "and every requested interaction. Avoid placeholder cards, placeholder descriptions, and unfinished sections."
        )

    def recover_fenced_write_calls(
        self,
        response: str,
        requested_files: list[str],
        modified_files: set[str],
    ) -> list[ParsedToolCall]:
        """Convert unambiguous fenced code into staged writes.

        Smaller local models often produce a correct `````html`` block but
        omit XML tool syntax. When the task explicitly requested one matching
        file, preserving that work is safer and more useful than retrying the
        same response until the contract budget is exhausted.
        """
        language_extensions = {
            "html": {".html", ".htm"},
            "css": {".css"},
            "scss": {".scss"},
            "javascript": {".js", ".mjs", ".cjs"},
            "js": {".js", ".mjs", ".cjs"},
            "typescript": {".ts", ".tsx"},
            "ts": {".ts", ".tsx"},
            "markdown": {".md"},
            "md": {".md"},
            "json": {".json"},
            "python": {".py"},
            "py": {".py"},
        }
        staged = {path.replace("\\", "/").lower() for path in modified_files}
        remaining = [path for path in requested_files if path.lower() not in staged]
        candidate_pool = remaining or requested_files
        blocks = re.findall(r"```([A-Za-z0-9_+-]*)\s*\n([\s\S]*?)```", response or "")
        recovered: list[ParsedToolCall] = []
        claimed: set[str] = set()

        for language, content in blocks:
            extensions = language_extensions.get(language.strip().lower())
            if not extensions:
                continue
            candidates = [
                path for path in candidate_pool
                if Path(path).suffix.lower() in extensions and path.lower() not in claimed
            ]
            if len(candidates) != 1 or not content.strip():
                continue
            target = candidates[0]
            args = {"path": target, "content": content.rstrip() + "\n"}
            recovered.append(ParsedToolCall(
                type="tool_call",
                tool="write_file",
                args=args,
                raw=f"recovered fenced {language} output",
            ))
            claimed.add(target.lower())
        return recovered

    @staticmethod
    def single_file_generation_message(path: str) -> str:
        extension = Path(path).suffix.lower()
        language = {
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".js": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".md": "markdown",
            ".json": "json",
            ".py": "python",
        }.get(extension, "text")
        return (
            f"Generate the complete contents of {path} now. Respond with exactly one fenced {language} code block. "
            "Do not include XML, prose, headings, or any other file. The runtime will stage that block as the requested file."
        )

    @staticmethod
    def recover_plain_requested_file(response: str, path: str) -> ParsedToolCall | None:
        """Recover plain content from an isolated single-file generation turn."""
        content = (response or "").strip()
        if not content or "<tool_call" in content:
            return None
        if content.startswith("```"):
            lines = content.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            content = "\n".join(lines).strip()
        if not content:
            return None

        extension = Path(path).suffix.lower()
        signatures = {
            ".md": lambda value: value.lstrip().startswith("#"),
            ".html": lambda value: "<!doctype" in value.lower() or "<html" in value.lower(),
            ".css": lambda value: "{" in value and "}" in value,
            ".scss": lambda value: "{" in value and "}" in value,
            ".js": lambda value: any(token in value for token in ("document.", "addEventListener", "function ", "const ", "let ")),
            ".mjs": lambda value: any(token in value for token in ("document.", "addEventListener", "function ", "const ", "let ")),
            ".cjs": lambda value: any(token in value for token in ("module.exports", "require(", "function ", "const ")),
            ".ts": lambda value: any(token in value for token in ("interface ", "type ", "function ", "const ", "let ")),
            ".tsx": lambda value: any(token in value for token in ("function ", "const ", "return (", "React")),
            ".py": lambda value: any(token in value for token in ("def ", "class ", "import ", "from ")),
            ".txt": lambda value: len(value) >= 20,
        }
        validator = signatures.get(extension)
        if validator is None or not validator(content):
            return None
        return ParsedToolCall(
            type="tool_call",
            tool="write_file",
            args={"path": path, "content": content.rstrip() + "\n"},
            raw="recovered isolated plain file output",
        )

    def recover_requested_file(
        self,
        *,
        prompt: str,
        path: str,
        tool_registry: ToolRegistry,
        executor: AgentExecutor,
        modified_files: set[str],
        on_status: Callable[[str, str], None],
        correction: str = "",
    ) -> bool:
        """Generate one explicit deliverable in a small, isolated model turn.

        The main conversation can become long or drift after several tool
        observations. An explicit file requested by the user is a completion
        contract, so a fresh turn is more reliable than silently returning a
        partial patchset when the regular turn budget is exhausted.
        """
        staged_context_parts: list[str] = []
        context_budget = 18000
        for staged_path, content in tool_registry.pending_contents.items():
            if staged_path.lower() == path.lower() or context_budget <= 0:
                continue
            excerpt = content[: min(6000, context_budget)]
            staged_context_parts.append(f"--- {staged_path} ---\n{excerpt}")
            context_budget -= len(excerpt)

        staged_context = "\n\n".join(staged_context_parts)
        request = (
            f"Original task:\n{prompt}\n\n"
            f"Create or revise only {path}. It must be complete, production-quality, and consistent "
            "with every requirement in the original task."
        )
        if correction:
            request += (
                "\n\nThe previous version was rejected. Rebuild the file so this issue is completely removed:\n"
                f"{correction}\n"
                "Do not repeat the rejected wording or structure. Placeholder names and filler text such as "
                "'Product 1', 'Description of Product', and 'Lorem ipsum' are forbidden. Use specific, realistic "
                "product names and useful customer-facing copy instead. The output will be rejected again if the "
                "issue remains."
            )
        if staged_context:
            request += f"\n\nAlready staged related files:\n{staged_context}"
        request += "\n\n" + self.single_file_generation_message(path)

        on_status("recovering", f"Completing required file: {path}")
        for generation_attempt in range(2):
            attempt_request = request
            if generation_attempt:
                on_status("retrying", f"Retrying required file with a strict format: {path}")
                attempt_request += (
                    "\n\nYour previous output could not be parsed. Return the file content only. "
                    "Do not mention the task, do not emit XML, and close the code fence."
                )
            response_text = self._stream_model_turn(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a focused coding agent completing one required project file. "
                            "Follow the requested output format exactly and do not discuss the work."
                        ),
                    },
                    {"role": "user", "content": attempt_request},
                ],
                mode="agent",
                max_tokens=3072,
                retries=1,
                on_status=on_status,
            )

            calls, parse_error = self.tool_args_or_error(response_text)
            if parse_error:
                calls = []
            eligible = [
                call for call in calls
                if call.tool == "write_file"
                and str(call.args.get("path", "")).replace("\\", "/").lower() == path.lower()
            ]
            if not eligible:
                eligible = self.recover_fenced_write_calls(response_text, [path], modified_files)
            if not eligible:
                plain_call = self.recover_plain_requested_file(response_text, path)
                eligible = [plain_call] if plain_call else []
            if not eligible:
                continue

            executor.execute(eligible[0])
            return path.lower() in {
                changed.replace("\\", "/").lower() for changed in modified_files
            }
        return False

    @staticmethod
    def frontend_quality_findings(prompt: str, pending_contents: dict[str, str]) -> list[str]:
        lower_prompt = (prompt or "").lower()
        if not any(token in lower_prompt for token in ("website", "web page", "landing page", "html", "css", "frontend", "ui")):
            return []

        combined = "\n".join(pending_contents.values())
        lower_combined = combined.lower()
        css = "\n".join(
            content for path, content in pending_contents.items()
            if Path(path).suffix.lower() in {".css", ".scss"}
        ).lower()
        javascript = "\n".join(
            content for path, content in pending_contents.items()
            if Path(path).suffix.lower() in {".js", ".mjs", ".cjs", ".ts"}
        ).lower()
        findings: list[str] = []

        if "responsive" in lower_prompt and "@media" not in css:
            findings.append("Responsive behavior was requested, but the stylesheet has no media query.")
        if "dark" in lower_prompt:
            light_defaults = ("#f4f4f4", "#ffffff", "background-color: white", "background: white")
            dark_tokens = ("#0", "#1", "#2", "rgb(0", "rgb(1", "background: black", "background-color: black")
            if any(token in css for token in light_defaults) and not any(token in css for token in dark_tokens):
                findings.append("A dark visual system was requested, but the primary stylesheet still uses a light default background.")
        if any(token in lower_prompt for token in ("theme toggle", "menu toggle", "interaction", "javascript-powered")):
            if "addeventlistener" not in javascript:
                findings.append("The requested JavaScript interaction is missing an event listener implementation.")
            toggled_classes = re.findall(
                r"classlist\.toggle\(\s*['\"]([^'\"]+)['\"]",
                javascript,
            )
            missing_selectors = [name for name in toggled_classes if f".{name}" not in css]
            if missing_selectors:
                findings.append(
                    "The stylesheet is missing the state class used by the theme interaction: "
                    + ", ".join(f".{name}" for name in missing_selectors)
                    + "."
                )
        placeholders = ("description of product", "description of game", "lorem ipsum", "product 1", "game 1")
        if any(token in lower_combined for token in placeholders):
            findings.append("The staged UI still contains placeholder product or game copy.")
        return findings

    @staticmethod
    def quality_revision_target(findings: list[str], requested_files: list[str]) -> str | None:
        first = findings[0].lower() if findings else ""
        if any(token in first for token in ("stylesheet", "responsive", "dark visual", "state class")):
            extensions = {".css", ".scss"}
        elif any(token in first for token in ("javascript", "event listener", "interaction")):
            extensions = {".js", ".mjs", ".cjs", ".ts"}
        else:
            extensions = {".html", ".htm"}
        return next((path for path in requested_files if Path(path).suffix.lower() in extensions), None)

    def synthesis_followup_message(self, task_type: TaskType) -> str:
        """User-turn message that asks the model to emit a final_answer.

        The loop appends this message after the last tool observation
        so the model gets one more turn to produce a structured
        ``final_answer`` before we fall back to deterministic synthesis.
        """
        if task_type == "scan":
            return (
                "You have inspected the project. Now respond with ONLY a final_answer object "
                f"inside {FINAL_ANSWER_OPEN}...{FINAL_ANSWER_CLOSE} tags. Use the shape: "
                '{"type":"final_answer","title":"Project Summary","summary":"...","evidence":["..."],'
                '"files_used":["..."],"next_steps":["..."]}. '
                "Do NOT call any more tools. Do NOT include any prose outside the tags."
            )
        return (
            "You have enough information to answer. Respond with ONLY a final_answer object "
            f"inside {FINAL_ANSWER_OPEN}...{FINAL_ANSWER_CLOSE} tags. Use the shape: "
            '{"type":"final_answer","title":"...","summary":"...","evidence":["..."],'
            '"files_used":["..."],"next_steps":["..."]}. '
            "Do NOT call any more tools. Do NOT include any prose outside the tags."
        )

    def detect_verification_command(self, manifest: str, changed_files: list[str]) -> str:
        manifest_path = Path(manifest) if manifest else None
        has_package_json = bool(manifest_path and manifest_path.name == "package.json" and manifest_path.exists())
        frontend_files = [path for path in changed_files if path.endswith((".ts", ".tsx", ".js", ".jsx"))]
        static_files = [path for path in changed_files if path.endswith((".html", ".css"))]

        if has_package_json and frontend_files:
            return "npm run build"
        if any(path.endswith(".py") for path in changed_files):
            return "python -m pytest"
        if static_files:
            quoted = " ".join(json.dumps(path) for path in static_files[:8])
            return (
                "python -c \"from pathlib import Path; import sys; "
                "missing=[p for p in sys.argv[1:] if not Path(p).is_file()]; "
                "print('verified files: ' + ', '.join(sys.argv[1:])); "
                "raise SystemExit(1 if missing else 0)\" "
                + quoted
            )
        return "python -c \"print('no verification command inferred')\""

    def is_scan_task(self, prompt: str) -> bool:
        prompt_lower = prompt.lower()
        return any(
            phrase in prompt_lower
            for phrase in (
                "scan through",
                "scan the project",
                "scan codebase",
                "scan through the project",
                "project overview",
                "understand the project",
            )
        )

    def _append_history(self, messages: list[dict[str, str]], history: list[dict[str, str]], limit: int = 8) -> None:
        """Append recent conversation turns before the current task."""
        if not history:
            return
        for item in history[-limit:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

    def _direct_chat_response(
        self,
        prompt: str,
        context: dict[str, Any],
        callbacks: dict[str, Callable],
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Answer trivial prompts without entering the tool loop."""
        on_chunk = callbacks.get("on_chunk", lambda chunk: None)
        on_status = callbacks.get("on_status", lambda status, message: None)
        on_status("thinking", "Replying...")

        messages: list[dict[str, str]] = [{
            "role": "system",
            "content": (
                "You are NexCoder AI, a helpful coding assistant inside an IDE. "
                "Reply naturally and concisely. Do not use tools for greetings or meta questions."
            ),
        }]
        self._append_history(messages, history or [])
        messages.append({"role": "user", "content": prompt})

        chunks: list[str] = []
        for chunk in self._model.chat_completion(
            messages,
            mode="ask",
            stream=True,
            include_system_prompt=False,
        ):
            chunks.append(chunk)
            on_chunk(chunk)

        response = "".join(chunks).strip()
        return {
            "success": True,
            "response": response or "Hello! How can I help with your code?",
            "mode": "chat",
            "patches": 0,
            "checkpoint_id": None,
        }

    def _stream_model_turn(
        self,
        messages: list[dict[str, str]],
        *,
        mode: str = "agent",
        max_tokens: int = 3072,
        retries: int = 2,
        on_status: Callable[[str, str], None] | None = None,
    ) -> str:
        """Return one complete model turn, retrying interrupted streams.

        The local OpenAI-compatible server can occasionally close a
        streaming response before the final SSE marker. Agent mode must
        treat that as a transport problem, not as model prose that failed
        the tool-call contract.
        """
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                chunks = []
                for chunk in self._model.chat_completion(
                    messages,
                    mode=mode,
                    stream=True,
                    max_tokens=max_tokens,
                    raise_on_error=True,
                ):
                    chunks.append(chunk)
                return "".join(chunks)
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    raise
                if on_status:
                    on_status(
                        "retrying",
                        f"Model stream interrupted; retrying request ({attempt + 1}/{retries})",
                    )
        if last_error:
            raise last_error
        return ""

    def run(self, prompt: str, context: dict[str, Any], callbacks: dict[str, Callable]) -> dict[str, Any]:
        project_root = context.get("project_path") or context.get("projectPath") or self.project_root
        if not project_root:
            raise ValueError("No active project root found in context")

        project_root = Path(project_root).resolve()
        self.project_root = project_root
        self._patch_gen = PatchGenerator(str(project_root))

        on_chunk = callbacks.get("on_chunk", lambda chunk: None)
        on_status = callbacks.get("on_status", lambda status, message: None)
        on_diff = callbacks.get("on_diff", lambda diff: None)
        on_timeline = callbacks.get("on_timeline", lambda item: None)
        on_plan = callbacks.get("on_plan", lambda plan: None)

        checkpoint_mgr = CheckpointManager(str(project_root))
        checkpoint_id = None
        modified_files: set[str] = set()
        executed_any_tool = False
        executed_write_tool = False
        # Per-call observation log the synthesis pass uses to build a
        # final_answer object when the model never produces one. Each
        # entry is ``{"tool": str, "args": dict, "result": dict}``.
        observations: list[dict[str, Any]] = []
        # Cooperative cancellation. The token may be missing when the loop
        # is invoked outside the runtime (e.g. unit tests). In that case
        # ``get_token`` returns ``None`` and the loop runs without any
        # cancellation checks â€” preserving the historical contract.
        from nexcoder.agent.cancellation import get_token as _get_token
        from nexcoder.agent.errors import AgentCancelledError

        cancellation_token = _get_token(context)
        tool_registry = ToolRegistry(
            project_root,
            on_diff=on_diff,
            modified_files=modified_files,
            cancellation_token=cancellation_token,
            defer_diffs=True,
            pending_patches=list(context.get("pending_changes") or []),
        )
        executor = AgentExecutor(
            tool_registry,
            on_timeline=on_timeline,
            permission_policy=PermissionPolicy.for_access_mode(
                context.get("access_mode") or context.get("accessMode")
            ),
            cancellation_token=cancellation_token,
        )

        profile = context.get("_mode_profile")
        mode_name = getattr(profile, "name", None) or context.get("mode") or "agent"
        intent: Intent = classify_prompt(prompt, mode_name)
        # Generic Agent mode must follow the current prompt, not its broad
        # write-capable profile default. Otherwise a question such as "what
        # is the stack?" can inherit ``implement`` and stage an unrelated
        # file. Explicit task types remain authoritative for dedicated modes
        # and structured entry points such as scan.
        classified_task_type = classify_task_type(prompt, mode_name)
        explicit_task_type = context.get("task_type")
        if mode_name == "agent" and explicit_task_type in {None, "implement"}:
            task_type = classified_task_type
        else:
            task_type = (
                explicit_task_type
                or classified_task_type
                or getattr(profile, "task_type", None)
                or "question"
            )
        history = context.get("conversation_history") or context.get("history") or []

        if allows_direct_reply(intent):
            return self._direct_chat_response(prompt, context, callbacks, history)

        if self.is_scan_task(prompt) or task_type == "scan" or intent == "scan":
            return self._run_scan_task(
                prompt=prompt,
                project_root=project_root,
                on_chunk=on_chunk,
                on_status=on_status,
            )

        task_plan = TaskPlanTracker(
            project_root,
            prompt=prompt,
            task_type=task_type,
            session_id=context.get("session_id") or context.get("sessionId"),
            on_update=on_plan,
        )
        executor.on_event = task_plan.tool_event

        on_status("planning", "Planning the coding task and collecting context...")
        context_text = self._context_builder.build(context, str(project_root))

        # Optional mode profile â€” wired in by AgenticRunner. When omitted
        # (legacy callers) we fall back to the historical permissive policy.
        profile = context.get("_mode_profile")
        if profile is not None:
            max_turns = int(getattr(profile, "max_turns", 8))
            max_retries = int(getattr(profile, "max_retries", 3))
            allowed_tools = set(getattr(profile, "allowed_tools", ()))
            system_prompt = getattr(profile, "system_prompt", None) or (
                "You are NexCoder Hermes, an autonomous coding agent. "
                "You inspect files, make edits, run checks, and report concise results. "
                "In agent mode, your intermediate responses must be XML tool calls only. "
                "Do not produce markdown explanations until after tool results have been provided."
            )
            extra = getattr(profile, "extra_instructions", "")
        else:
            max_turns = 8
            max_retries = 3
            allowed_tools = set()
            system_prompt = (
                "You are NexCoder Hermes, an autonomous coding agent. "
                "You inspect files, make edits, run checks, and report concise results. "
                "In agent mode, your intermediate responses must be XML tool calls only. "
                "Do not produce markdown explanations until after tool results have been provided."
            )
            extra = ""

        configured_max_turns = context.get("max_tool_iterations") or context.get("maxToolIterations")
        if configured_max_turns is not None:
            try:
                max_turns = max(1, min(40, int(configured_max_turns)))
            except (TypeError, ValueError):
                pass

        if task_type in {"question", "scan", "review"}:
            allowed_tools = set(READ_TOOLS)
            extra = (
                f"{extra}\nThis is a read-only {task_type} task. Inspect the "
                "project as needed, then return a grounded final answer. Do "
                "not create, edit, move, or delete files and do not run commands."
            ).strip()

        pending_changes = list(context.get("pending_changes") or [])
        structure_moves = self._stage_file_structure(
            prompt=prompt,
            project_root=project_root,
            pending_changes=pending_changes,
            tool_registry=tool_registry,
            executor=executor,
            observations=observations,
            on_status=on_status,
        )
        structure_only = bool(structure_moves) and self._structure_only_request(prompt)
        if structure_moves:
            executed_any_tool = True
            executed_write_tool = True
        if structure_only:
            # The deterministic planner has completed the requested layout
            # operation. Avoid asking a small model to reinterpret the same
            # task and replace true moves with duplicate write_file patches.
            max_turns = 0

        contract = self.tool_contract_message(prompt, intent=intent, task_type=task_type)
        quality_guidance = self.frontend_quality_guidance(prompt)
        if quality_guidance:
            contract = f"{contract}\n\n{quality_guidance}"
        if extra:
            contract = f"{contract}\n\n{extra}"

        # When the user pre-selected a skill from the UI, hint it to the
        # model so the model can either call load_skill with that id or
        # override it with a better choice. We never inject the body
        # automatically â€” the model invokes load_skill as a tool so the
        # token budget stays bounded by what the model actually needs.
        active_skill = (context.get("activeSkill") or context.get("active_skill") or "").strip()
        if active_skill:
            try:
                from nexcoder.agent.skills_registry import get_skill
                meta = get_skill(active_skill)
            except Exception:
                meta = None
            if meta:
                contract = (
                    f"{contract}\n\n"
                    f"User pre-selected skill: {meta['id']!r} "
                    f"({meta.get('label', meta['id'])}). "
                    f"Call <tool_call name=\"load_skill\">{{\n  \"id\": \"{meta['id']}\"\n}}</tool_call> "
                    f"if the skill applies to this task. If a different skill is a better fit, load that one instead."
                )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Project context:\n\n{context_text}"},
        ]
        self._append_history(messages, history, limit=8)
        messages.append({"role": "user", "content": contract})

        final_response = ""
        last_response = ""
        contract_violations = 0
        requested_files = (
            self.extract_requested_files(prompt)
            if task_type == "implement" and not structure_only
            else []
        )
        quality_review_requested = False
        quality_revision_attempts = 0
        # Imported here to keep the module-level import block at the top
        # untouched; the dependency graph is one-way.
        from nexcoder.agent.errors import AgentContractError

        for turn in range(1, max_turns + 1):
            # Cooperative cancellation: bail before the next model call if
            # the user asked to stop. This is the primary safety point â€” a
            # click during turn N lets turn N finish (one extra response
            # cycle) but never starts turn N+1.
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()

            on_status("planning", f"Choosing next tool action ({turn}/{max_turns})")
            response_text = self._stream_model_turn(
                messages,
                mode="agent",
                max_tokens=3072,
                on_status=on_status,
            )

            if cancellation_token is not None and cancellation_token.is_cancelled():
                raise AgentCancelledError(cancellation_token.reason)
            last_response = response_text

            # Use the non-raising parser so a malformed tool call becomes a
            # recoverable retry instead of crashing the whole turn.
            recovered_fenced_output = False
            tool_calls, parse_error = self.tool_args_or_error(response_text)
            patches = self.extract_patch_output(response_text)

            if not parse_error and not tool_calls and not patches and task_type == "implement":
                tool_calls = self.recover_fenced_write_calls(
                    response_text,
                    requested_files,
                    modified_files,
                )
                if tool_calls:
                    recovered_fenced_output = True
                    on_status(
                        "parsed",
                        f"Recovered {len(tool_calls)} file write(s) from fenced code output",
                    )

            if parse_error:
                contract_violations += 1
                on_status("retrying", f"Tool call parse error: {parse_error}")
                if contract_violations > max_retries:
                    raise AgentContractError(
                        mode="agent", attempts=turn, last_response=response_text
                    )
                # Append assistant content with tool-call XML stripped so
                # the frontend never receives raw <tool_call> blocks.
                stripped = _strip_tool_call_xml(response_text)
                messages.append({"role": "assistant", "content": stripped})
                messages.append({
                    "role": "user",
                    "content": f"Your tool call was rejected: {parse_error}. "
                    "Re-emit it with valid JSON arguments.",
                })
                continue

            if not tool_calls and patches:
                # Full-file fenced output is common with smaller local models.
                # Route it through write_file so it participates in the same
                # staged-content, duplicate-call, and completion machinery as
                # an XML tool call. Legacy free-form diffs remain supported for
                # tasks that did not name explicit deliverables.
                if task_type == "implement" and requested_files:
                    tool_calls = [
                        ParsedToolCall(
                            type="tool_call",
                            tool="write_file",
                            args={"path": patch["file"], "content": patch["content"]},
                            raw="recovered named fenced file output",
                        )
                        for patch in patches
                        if patch.get("file") in requested_files and "content" in patch
                    ]
                    recovered_fenced_output = bool(tool_calls)
                    if not tool_calls:
                        remaining_files = self.missing_requested_files(
                            requested_files,
                            modified_files,
                        )
                        if not remaining_files:
                            break
                        messages.append({"role": "assistant", "content": ""})
                        messages.append({
                            "role": "user",
                            "content": (
                                "The diff output did not satisfy the explicit file contract. "
                                + self.single_file_generation_message(
                                    remaining_files[0]
                                )
                            ),
                        })
                        continue
                else:
                    on_status("parsed", "Detected patch output without explicit tool calls.")
                    for patch in patches:
                        patch.setdefault("action", "modify")
                        patch.setdefault("language", "diff")
                        on_diff(patch)
                    break

            if not tool_calls:
                # No tools and no diff: either the model is done, or it
                # drifted into prose before satisfying the task contract.
                if task_type_requires_final_answer(task_type) and _response_has_final_answer(response_text):
                    final_response = _strip_tool_call_xml(response_text).strip()
                    if final_response:
                        on_chunk(final_response)
                    break

                missing_files = self.missing_requested_files(requested_files, modified_files)
                if task_type == "implement" and modified_files and missing_files:
                    on_status(
                        "planning",
                        f"Completing remaining deliverables ({len(missing_files)} file(s))",
                    )
                    messages.append({"role": "assistant", "content": _strip_tool_call_xml(response_text)})
                    messages.append({
                        "role": "user",
                        "content": self.single_file_generation_message(missing_files[0]),
                    })
                    continue

                quality_findings = self.frontend_quality_findings(
                    prompt,
                    tool_registry.pending_contents,
                )
                if task_type == "implement" and modified_files and quality_findings and quality_revision_attempts < 3:
                    quality_revision_attempts += 1
                    quality_review_requested = True
                    target = self.quality_revision_target(quality_findings, requested_files)
                    on_status(
                        "reviewing",
                        f"Correcting quality issue ({quality_revision_attempts}/3)",
                    )
                    messages.append({"role": "assistant", "content": _strip_tool_call_xml(response_text)})
                    revision_request = (
                        "The staged implementation does not yet meet the task quality bar:\n- "
                        + "\n- ".join(quality_findings)
                        + "\nCorrect the first issue now."
                    )
                    if target:
                        revision_request += "\n" + self.single_file_generation_message(target)
                    else:
                        revision_request += " Use write_file to stage the corrected full file."
                    messages.append({"role": "user", "content": revision_request})
                    continue

                if task_type == "implement" and modified_files and not quality_review_requested:
                    quality_review_requested = True
                    on_status("reviewing", "Reviewing staged changes against the task requirements...")
                    messages.append({"role": "assistant", "content": _strip_tool_call_xml(response_text)})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Perform a final quality check against the original task. Read staged files if needed. "
                            "If anything is missing, generic, placeholder-quality, inconsistent, or broken, correct it with write_file now. "
                            "When all requirements are satisfied, provide a concise final summary and stop."
                        ),
                    })
                    continue

                can_finish_with_prose = executed_any_tool and (
                    task_type != "implement" or bool(modified_files) or executed_write_tool
                )
                if can_finish_with_prose:
                    if task_type != "implement":
                        final_response = _strip_tool_call_xml(response_text).strip()
                        if final_response:
                            on_chunk(final_response)
                    break

                contract_violations += 1
                on_status(
                    "retrying",
                    f"Response did not include a tool call (attempt {contract_violations}/{max_retries})",
                )

                if contract_violations > max_retries:
                    raise AgentContractError(
                        mode="agent", attempts=turn, last_response=response_text
                    )

                messages.append({"role": "assistant", "content": _strip_tool_call_xml(response_text)})
                if task_type == "implement" and executed_any_tool:
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have already inspected the project. The task requires a file change. "
                            "Respond with exactly one write_file tool call containing the complete target file content. "
                            "Use this exact XML shape and valid JSON: "
                            '<tool_call name="write_file">{"path":"index.html","content":"FULL FILE CONTENT"}</tool_call>. '
                            "Do not use markdown fences, prose, or an empty XML block."
                        ),
                    })
                elif contract_violations >= 2:
                    # Force the model to continue a tool call instead of
                    # generating prose. After this prefill the only way to
                    # produce a valid response is to close the open
                    # tool_call block and emit a follow-up action.
                    messages.append({
                        "role": "assistant",
                        "content": self.prefill_first_tool_call(),
                    })
                    messages.append({
                        "role": "user",
                        "content": "Continue from the tool call above and complete the task.",
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": self.retry_tool_call_message(),
                    })
                continue

            # Small local models often use intuitive aliases such as
            # ``mkdir`` or ``move_file``. Normalize them before the mode
            # policy check so equivalent safe operations share one contract.
            tool_calls = [
                ParsedToolCall(
                    type=call.type,
                    tool=ToolRegistry.canonical_tool_name(call.tool),
                    args=call.args,
                    raw=call.raw,
                )
                for call in tool_calls
            ]

            # We have tool calls. Enforce the mode's allow-list.
            if allowed_tools:
                blocked = [c for c in tool_calls if c.tool not in allowed_tools]
                if blocked:
                    blocked_names = sorted({c.tool for c in blocked})
                    contract_violations += 1
                    on_status(
                        "retrying",
                        f"Tools not allowed in this mode: {', '.join(blocked_names)}",
                    )
                    if contract_violations > max_retries:
                        raise AgentContractError(
                            mode="agent", attempts=turn, last_response=response_text
                        )
                    stripped = _strip_tool_call_xml(response_text)
                    messages.append({"role": "assistant", "content": stripped})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Tools {blocked_names} are not available in this mode. "
                            f"Use only: {sorted(allowed_tools)}. Re-emit your call."
                        ),
                    })
                    continue

            visible_prose = (
                ""
                if recovered_fenced_output or task_type == "implement"
                else _strip_tool_call_xml(response_text).strip()
            )
            if visible_prose:
                on_chunk(visible_prose)

            tool_results: list[str] = []
            for tool_call in tool_calls:
                executed_any_tool = True
                _item, observation = executor.execute(tool_call)
                if tool_call.tool in {"write_file", "create_directory", "move_path"}:
                    executed_write_tool = True
                tool_results.append(observation)
                # Record the call so the post-loop synthesis can build a
                # final_answer object from the actual tool activity even
                # when the model never produces one.
                observations.append(
                    {
                        "tool": tool_call.tool,
                        "args": tool_call.args,
                        "observation": observation,
                    }
                )

            # Once every explicit deliverable is staged, another model turn
            # adds latency but no new evidence. The deterministic post-loop
            # quality gate below still checks and repairs weak output before
            # the patchset is exposed for review.
            if (
                task_type == "implement"
                and requested_files
                and modified_files
                and not self.missing_requested_files(requested_files, modified_files)
            ):
                on_status("reviewing", "Checking staged deliverables against the task requirements...")
                break

            # Append assistant reply with any tool-call XML removed so the
            # history remains clean and the UI won't display raw XML blocks.
            messages.append({
                "role": "assistant",
                "content": "" if recovered_fenced_output else _strip_tool_call_xml(response_text),
            })
            messages.append({
                "role": "user",
                "content": (
                    "Tool results:\n"
                    f"{chr(10).join(tool_results)}\n\n"
                    + (
                        "Staged files: " + ", ".join(sorted(modified_files)) + ".\n"
                        if modified_files else ""
                    )
                    + (
                        "Explicit files still required: "
                        + ", ".join(self.missing_requested_files(requested_files, modified_files))
                        + ".\n"
                        if self.missing_requested_files(requested_files, modified_files) else ""
                    )
                    +
                    "Continue with the next required tool call. If the task is complete, provide a concise final summary. "
                    "Do not repeat raw tool XML in the final summary."
                ),
            })

        # For read-only task types the loop's normal tool-then-prose
        # pattern can leave us with tool observations but no
        # ``final_answer`` object. Give the model one extra turn that
        # *forbids* tool calls and asks for the final answer object â€”
        # this is cheaper than asking the user to repeat the question
        # and reliably produces a structured card.
        if (
            task_type_requires_final_answer(task_type)
            and not _response_has_final_answer(last_response)
        ):
            on_status("synthesizing", "Generating final answer...")
            messages.append({
                "role": "user",
                "content": self.synthesis_followup_message(task_type),
            })
            try:
                synthesis_text = self._stream_model_turn(
                    messages,
                    mode="agent",
                    max_tokens=2000,
                    retries=1,
                    on_status=on_status,
                )
            except (StopIteration, RuntimeError) as exc:
                # The model client may stop iterating after the loop
                # ends (e.g. test mocks that only return a fixed number
                # of responses). Treat the absence of a synthesis turn
                # as a deterministic-synthesis signal rather than a
                # fatal error.
                logger.debug("Synthesis turn did not produce a response: %s", exc)
                synthesis_text = ""
            if synthesis_text:
                last_response = synthesis_text
                # The synthesis turn is prose-only; surface it so the
                # chat pane reflects the model output even if extraction
                # later falls back to the deterministic path.
                cleaned_synthesis = _strip_tool_call_xml(synthesis_text).strip()
                if cleaned_synthesis:
                    on_chunk("\n\n" + cleaned_synthesis)
                    if not final_response.strip():
                        final_response = cleaned_synthesis

        # A turn budget is a safety cap, not permission to claim partial work
        # is complete. Finish every explicitly requested file in isolated turns
        # before producing the review patchset.
        remaining_quality_findings: list[str] = []
        if task_type == "implement":
            missing_after_loop = self.missing_requested_files(requested_files, modified_files)
            for missing_path in missing_after_loop:
                try:
                    self.recover_requested_file(
                        prompt=prompt,
                        path=missing_path,
                        tool_registry=tool_registry,
                        executor=executor,
                        modified_files=modified_files,
                        on_status=on_status,
                    )
                except Exception as exc:
                    logger.warning("Could not recover required file %s: %s", missing_path, exc)

            post_loop_findings = self.frontend_quality_findings(
                prompt,
                tool_registry.pending_contents,
            )
            post_loop_repairs = 0
            while post_loop_findings and post_loop_repairs < 3:
                target = self.quality_revision_target(post_loop_findings, requested_files)
                if not target:
                    break
                post_loop_repairs += 1
                try:
                    repaired = self.recover_requested_file(
                        prompt=prompt,
                        path=target,
                        tool_registry=tool_registry,
                        executor=executor,
                        modified_files=modified_files,
                        on_status=on_status,
                        correction=post_loop_findings[0],
                    )
                except Exception as exc:
                    logger.warning("Could not repair required file %s: %s", target, exc)
                    repaired = False
                if not repaired:
                    break
                post_loop_findings = self.frontend_quality_findings(
                    prompt,
                    tool_registry.pending_contents,
                )
            remaining_quality_findings = post_loop_findings
            if remaining_quality_findings:
                on_status("blocked", "Quality review still has unresolved findings")

        pending_patches = tool_registry.flush_pending_diffs()
        changed_targets = [
            str(patch.get("file"))
            for patch in pending_patches
            if patch.get("file")
        ]
        pending_count = len(pending_patches)
        missing_files = self.missing_requested_files(requested_files, modified_files)

        if pending_patches:
            on_status("awaiting_approval", f"Prepared {pending_count} change(s) for review")

        if task_type == "implement" and modified_files:
            if missing_files:
                final_response = (
                    f"The agent prepared {pending_count} change(s), but did not complete "
                    f"the required files: {', '.join(missing_files)}."
                )
            elif remaining_quality_findings:
                final_response = (
                    f"The agent prepared {pending_count} change(s), but quality review did not pass: "
                    + "; ".join(remaining_quality_findings)
                )
            else:
                final_response = (
                    f"Prepared {pending_count} change(s) for review: "
                    + ", ".join(changed_targets)
                    + "\n\nReview and accept the patch to write these changes to disk."
                )
            on_chunk(final_response)
        # For read-only task types (question / scan / review) the loop MUST
        # produce a structured final_answer. We try the model first; if it
        # emitted one in <final_answer>...</final_answer> tags we parse
        # and normalise it. If the model only produced prose we still
        # build a final_answer envelope. If we have tool observations but
        # no model summary we fall back to a deterministic synthesis.
        final_answer: dict[str, Any] | None = None
        if task_type_requires_final_answer(task_type):
            final_answer = self._build_final_answer(
                task_type=task_type,
                prompt=prompt,
                model_response=final_response or last_response,
                observations=observations,
            )
            # Stream the prose summary back to the chat pane so the user
            # sees the model answer in addition to the structured card.
            summary_text = (final_answer.get("summary") or "").strip()
            if summary_text and summary_text != final_response:
                on_chunk("\n\n" + summary_text)
            # The model-facing ``response`` becomes the prose summary so
            # downstream code that reads ``result["response"]`` keeps
            # working.
            if summary_text:
                final_response = summary_text

        result = {
            "success": not bool(missing_files or remaining_quality_findings),
            "response": final_response or "Task completed.",
            "mode": "agent",
            "patches": len(pending_patches),
            "patchset": pending_patches,
            "incomplete": bool(missing_files),
            "missing_files": missing_files,
            "quality_findings": remaining_quality_findings,
            "checkpoint_id": checkpoint_id,
            "task_type": task_type,
            "final_answer": final_answer,
        }
        result["plan"] = task_plan.finish(result)
        return result

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Final-answer synthesis
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _build_final_answer(
        self,
        *,
        task_type: TaskType,
        prompt: str,
        model_response: str,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a structured final_answer object for read-only task types.

        Resolution order:

        1. If the model emitted a parseable ``<final_answer>...</final_answer>``
           block (or JSON inside one), use it. Falls back to wrapping any
           prose inside the tags.
        2. If the loop collected at least one successful tool observation
           we synthesise a final-answer from the files we read.
        3. Otherwise we wrap whatever the model said so the UI still
           renders a card.
        """
        title = "Project Summary" if task_type == "scan" else "Answer"
        model_object = extract_final_answer_object(model_response or "")
        if (model_object.get("summary") or "").strip() or (model_object.get("evidence") or []):
            # The model produced something usable â€” keep its content but
            # normalise the title to match the task type.
            model_object["title"] = title
            return model_object

        # No usable model answer â†’ synthesise from observations.
        synthesised = synthesize_from_observations(
            prompt=prompt,
            observations=_observation_records(observations),
            title=title,
        )
        if synthesised.get("summary") or synthesised.get("evidence"):
            return synthesised

        # Last resort: wrap the raw model response.
        return {
            "type": "final_answer",
            "title": title,
            "summary": (model_response or "").strip()
            or "I did not have enough information to answer that.",
            "evidence": [],
            "files_used": [],
            "next_steps": [],
        }

    def _run_scan_task(
        self,
        *,
        prompt: str,
        project_root: Path,
        on_chunk: Callable[[str], None],
        on_status: Callable[[str, str], None],
    ) -> dict[str, Any]:
        """Run the deterministic project scan and wrap it as final_answer.

        The scan is non-LLM (it walks the filesystem), so the
        final_answer object is built directly from the scan output
        rather than from a model response. The model is still asked
        once for an opinionated summary; if the request is
        unauthenticated or fails we fall back to the scan text.
        """
        final_response = self._agentic_project_scan(project_root, on_status)
        return {
            "success": not bool(missing_files),
            # Scan output is rendered from the structured final_answer
            # card. Returning it as chat prose as well duplicates the
            # same report in the UI and CLI.
            "response": "",
            "mode": "scan",
            "patches": 0,
            "checkpoint_id": None,
            "task_type": "scan",
            "final_answer": {
                "type": "final_answer",
                "title": "Project Summary",
                "summary": final_response,
                "evidence": [],
                "files_used": [],
                "next_steps": [
                    "Run `Scan codebase` to refresh the project map",
                    "Use Ask mode to ask targeted questions about the result",
                ],
            },
        }

    def _tool_status_message(self, name: str, args: dict[str, Any]) -> str:
        if name == "read_file":
            return f"Reading {args.get('path', '')}..."
        if name == "list_directory":
            return f"Listing {args.get('path') or '.'}..."
        if name == "search_grep":
            return f"Searching for {args.get('query', '')}..."
        if name == "write_file":
            return f"Editing {args.get('path', '')}..."
        if name == "run_command":
            return f"Running {args.get('command', '')}..."
        if name == "load_skill":
            return f"Loading skill {args.get('id', '')}..."
        return f"Executing {name}..."

    def _agentic_project_scan(
        self,
        project_root: Path,
        on_status: Callable[[str, str], None],
    ) -> str:
        on_status("scanning", "Listing project files...")
        files = self._safe_list_project_files(project_root, limit=120)

        directories: list[str] = []
        seen_dirs: set[str] = set()
        for rel in files:
            parent = str(Path(rel).parent)
            if parent != "." and parent not in seen_dirs:
                seen_dirs.add(parent)
                directories.append(parent)

        key_names = {
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "README.md",
            "build.py",
            "main.py",
            "app.py",
            "server.py",
        }
        key_files = [rel for rel in files if Path(rel).name in key_names][:12] or files[:8]

        snippets: list[str] = []
        for rel in key_files:
            on_status("scanning", f"Reading {rel}...")
            full_path = self._resolve_project_path(project_root, rel)
            if not full_path or not full_path.is_file():
                continue
            try:
                text = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            first_lines = [line.strip() for line in text.splitlines() if line.strip()][:5]
            snippets.append(f"- {rel}: {' | '.join(first_lines)[:280]}")

        lines = [
            "Project scan complete.",
            "",
            "Structure:",
        ]
        if directories:
            for directory in directories[:20]:
                lines.append(f"- {directory}/")
        else:
            lines.append("- Root-only project structure")

        lines.extend(["", "Key files inspected:"])
        lines.extend(snippets or ["- No readable source/config files found."])

        lines.extend([
            "",
            "Agent-readiness notes:",
            f"- Found {len(files)} readable source/config/doc file(s).",
            "- Agent mode now hides intermediate model chatter and only reports tool-backed work.",
            "- For edit tasks, the agent will inspect files, write changes, and run a verification command when it can infer one.",
        ])
        return "\n".join(lines)

    def _safe_list_project_files(self, project_root: Path, limit: int = 80) -> list[str]:
        files: list[str] = []
        for root, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [name for name in dirnames if not should_skip_dir(name)]
            for filename in filenames:
                full = Path(root) / filename
                if full.suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                try:
                    files.append(str(full.relative_to(project_root)))
                except ValueError:
                    continue
                if len(files) >= limit:
                    return files
        return files

    def _resolve_project_path(self, project_root: Path, target: str) -> Path | None:
        try:
            full_path = (project_root / target).resolve()
            common = os.path.commonpath([str(project_root), str(full_path)])
        except (OSError, ValueError):
            return None
        if common != str(project_root):
            return None
        return full_path

    def _read_file(self, args: dict[str, Any], project_root: Path) -> str:
        target = args.get("path", "")
        full_path = self._resolve_project_path(project_root, target)
        if full_path is None:
            return json.dumps({"success": False, "error": "Access denied"})
        if not full_path.exists():
            return json.dumps({"success": False, "error": f"File not found: {target}"})
        try:
            return json.dumps({"success": True, "content": full_path.read_text(encoding="utf-8", errors="replace")})
        except Exception as exc:
            return json.dumps({"success": False, "error": str(exc)})

    def _write_file(
        self,
        args: dict[str, Any],
        project_root: Path,
        modified_files: set[str],
        checkpoint_mgr: CheckpointManager,
        checkpoint_id: str | None,
        on_diff: Callable[[dict[str, Any]], None],
    ) -> str:
        target = args.get("path", "")
        content = args.get("content", "")
        full_path = self._resolve_project_path(project_root, target)
        if full_path is None:
            return json.dumps({"success": False, "error": "Access denied"})
        if self._safety.is_sensitive_file(target):
            return json.dumps({"success": False, "error": "Sensitive file write blocked"})

        # Read original before writing so diff generation is correct
        original = full_path.read_text(encoding="utf-8", errors="replace") if full_path.exists() else ""

        if full_path.exists() and target not in modified_files:
            checkpoint_id = checkpoint_mgr.create([str(full_path)], f"Hermes agent edit: {target}")

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        modified_files.add(target)

        modified = full_path.read_text(encoding="utf-8", errors="replace")
        diff = self._patch_gen.generate_diff(original, modified, target)
        patch = {"file": target, "action": "modify", "diff": diff, "diff_display": diff, "checkpoint_id": checkpoint_id}
        on_diff(patch)
        return json.dumps({"success": True, "message": f"Wrote {target}"})

    def _search_grep(self, args: dict[str, Any], project_root: Path) -> str:
        query = args.get("query", "")
        search_dir = args.get("path", "")
        target = self._resolve_project_path(project_root, search_dir) if search_dir else project_root
        if target is None:
            return json.dumps({"success": False, "error": "Access denied"})
        if not target.exists():
            return json.dumps({"success": False, "error": "Search directory not found"})
        results: list[dict[str, Any]] = []
        for path in target.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".md"}:
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if query.lower() in content.lower():
                    results.append({"file": str(path.relative_to(project_root)), "content": content[:200]})
        return json.dumps({"success": True, "results": results[:20]})

    def _list_directory(self, args: dict[str, Any], project_root: Path) -> str:
        target = args.get("path", "")
        root = self._resolve_project_path(project_root, target) if target else project_root
        if root is None:
            return json.dumps({"success": False, "error": "Access denied"})
        if not root.exists():
            return json.dumps({"success": False, "error": "Directory not found"})
        entries = []
        for child in sorted(root.iterdir()):
            entries.append({"name": child.name, "type": "directory" if child.is_dir() else "file"})
        return json.dumps({"success": True, "entries": entries})

    def _run_command(self, args: dict[str, Any], project_root: Path) -> str:
        command = args.get("command", "")
        if self._safety.is_command_blocked(command):
            return json.dumps({"success": False, "error": "Blocked dangerous command"})
        completed = subprocess.run(
            command,
            cwd=str(project_root),
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.dumps({
            "success": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
        })

    def _load_skill(self, args: dict[str, Any]) -> str:
        """Return the body of a skill's ``SKILL.md`` for the model to follow.

        This is a *read* tool â€” it never touches the filesystem or runs
        commands. The body can be large (multi-KB) so we cap it at
        ``MAX_SKILL_BODY_CHARS`` to keep the conversation window bounded.
        """
        skill_id = (args.get("id") or "").strip()
        if not skill_id:
            return json.dumps({
                "success": False,
                "error": "Missing required argument: id",
            })
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", skill_id):
            return json.dumps({
                "success": False,
                "error": "Invalid skill id (must be kebab-case, â‰¤ 64 chars)",
            })

        record = get_skill_body(skill_id)
        if record is None:
            return json.dumps({
                "success": False,
                "error": f"Unknown skill: {skill_id!r}. Use load_skill without args to see a list, or call read_file on nexcoder/agent/skills/{skill_id}/SKILL.md.",
            })

        body = record.get("body") or ""
        if len(body) > self.MAX_SKILL_BODY_CHARS:
            truncated = body[: self.MAX_SKILL_BODY_CHARS]
            body = truncated + "\n\n[Skill body truncated for context budget; full content in nexcoder/agent/skills/{}/SKILL.md]".format(skill_id)
        return json.dumps({
            "success": True,
            "skill": {
                "id": record["id"],
                "name": record["name"],
                "category": record["category"],
                "body": body,
            },
        })

    # Cap the body so a single skill can't blow the conversation budget.
    MAX_SKILL_BODY_CHARS = 12_000







    @staticmethod
    def _structure_only_request(prompt: str) -> bool:
        """Return true when file layout is the deliverable, not incidental work."""
        return not bool(re.search(
            r"\b(?:build|implement|redesign|restyle|debug|fix|add\s+(?:a|an|the)?\s*feature|"
            r"create\s+(?:a|an|the)?\s*(?:app|page|site|component|feature))\b",
            prompt or "",
            re.IGNORECASE,
        ))

    def _stage_file_structure(
        self,
        *,
        prompt: str,
        project_root: Path,
        pending_changes: list[dict[str, Any]],
        tool_registry: ToolRegistry,
        executor: AgentExecutor,
        observations: list[dict[str, Any]],
        on_status: Callable[[str, str], None],
    ) -> list[FileMove]:
        """Stage deterministic moves and reference rewrites for structure tasks."""
        moves = plan_file_moves(prompt, project_root, pending_changes)
        if not moves:
            return []

        def run_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
            _item, observation = executor.execute(ParsedToolCall(
                type="tool_call",
                tool=tool,
                args=args,
                raw="",
            ))
            try:
                record = json.loads(observation)
            except json.JSONDecodeError:
                record = {"tool": tool, "args": args, "result": {"success": False}}
            observations.append(record)
            return dict(record.get("result") or {})

        on_status("planning", f"Preparing file structure plan ({len(moves)} move(s))")
        parent_directories = sorted({
            str(Path(move.destination).parent).replace("\\", "/")
            for move in moves
            if str(Path(move.destination).parent) not in {"", "."}
        })
        for directory in parent_directories:
            result = run_tool("create_directory", {"path": directory})
            if not result.get("success") and result.get("error_code") != "path_conflict":
                on_status("blocked", f"Could not prepare folder: {directory}")
                return []

        completed_moves: list[FileMove] = []
        for move in moves:
            result = run_tool("move_path", {
                "source": move.source,
                "destination": move.destination,
            })
            if not result.get("success"):
                on_status("blocked", f"Could not move {move.source} to {move.destination}")
                continue
            completed_moves.append(move)

        # Update references against the virtual post-move filesystem. This
        # includes files staged by an earlier chat turn, so organization works
        # before the user accepts the original flat-file patchset.
        reference_files = tool_registry.virtual_text_files()
        known_paths = set(reference_files)

        def rebase_reference(ref: str, source: str, destination: str) -> str:
            if not ref or ref.startswith(("#", "/", "http:", "https:", "data:", "mailto:", "javascript:")):
                return ref
            match = re.match(r"(?P<path>[^?#]+)(?P<suffix>[?#].*)?$", ref)
            if not match:
                return ref
            ref_path = match.group("path")
            source_parent = posixpath.dirname(source) or "."
            target = posixpath.normpath(posixpath.join(source_parent, ref_path))
            if target not in known_paths:
                return ref
            destination_parent = posixpath.dirname(destination) or "."
            rebased = posixpath.relpath(target, start=destination_parent)
            if ref_path.startswith("./") and not rebased.startswith("."):
                rebased = f"./{rebased}"
            return f"{rebased}{match.group('suffix') or ''}"

        # A moved file changes the base directory used by its own relative
        # links. Rebase common HTML, CSS and JavaScript references before
        # updating references to the moved file from the rest of the project.
        for move in completed_moves:
            destination = move.destination.replace("\\", "/")
            content = reference_files.get(destination)
            if content is None:
                continue
            original_content = content

            def replace_quoted(match: re.Match[str]) -> str:
                return (
                    f"{match.group('prefix')}"
                    f"{rebase_reference(match.group('ref'), move.source, destination)}"
                    f"{match.group('suffix')}"
                )

            patterns = (
                re.compile(r"(?P<prefix>\b(?:href|src)\s*=\s*['\"])(?P<ref>[^'\"]+)(?P<suffix>['\"])", re.IGNORECASE),
                re.compile(r"(?P<prefix>\bfrom\s+['\"])(?P<ref>[^'\"]+)(?P<suffix>['\"])", re.IGNORECASE),
                re.compile(r"(?P<prefix>\bimport\s*['\"])(?P<ref>[^'\"]+)(?P<suffix>['\"])", re.IGNORECASE),
            )
            for pattern in patterns:
                content = pattern.sub(replace_quoted, content)
            reference_files[destination] = content
            if content != original_content:
                run_tool("write_file", {"path": destination, "content": content})

        for path, content in reference_files.items():
            updated = content
            parent = str(Path(path).parent).replace("\\", "/")
            parent = "." if parent in {"", "."} else parent
            for move in completed_moves:
                source = move.source.replace("\\", "/")
                destination = move.destination.replace("\\", "/")
                relative_destination = posixpath.relpath(destination, start=parent)
                replacements = {source: relative_destination}
                if source.startswith("./"):
                    replacements[source[2:]] = relative_destination
                else:
                    replacements[f"./{source}"] = (
                        relative_destination
                        if relative_destination.startswith(".")
                        else f"./{relative_destination}"
                    )
                if "/" not in source:
                    replacements[Path(source).name] = relative_destination
                for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
                    updated = updated.replace(old, new)
            if updated != content:
                run_tool("write_file", {"path": path, "content": updated})

        on_status("planning", f"Prepared {len(completed_moves)} structural move(s) for review")
        return completed_moves
