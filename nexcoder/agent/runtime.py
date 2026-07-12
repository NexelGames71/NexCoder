"""AgentRuntime — orchestrator that dispatches to mode-specific handlers."""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal

from nexcoder.agent.cancellation import CancellationToken, get_token
from nexcoder.agent.errors import (
    AgentCancelledError,
    envelope_from_exception,
)
from nexcoder.agent.redaction import SecretRedactor

logger = logging.getLogger(__name__)


class AgentRuntime(QObject):
    """Main AI agent orchestrator. Manages conversation history and mode dispatch."""

    # Signals for streaming to the frontend
    stream_chunk = Signal(str)       # text chunk
    status_update = Signal(str)      # JSON status
    diff_ready = Signal(str)         # JSON diff for approval
    completed = Signal(str)          # JSON completion

    def __init__(self) -> None:
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent")
        self._conversation_history: list[dict[str, str]] = []
        self._pending_diffs: dict[str, dict] = {}
        self._hermes_loop = None
        self._memory_managers: dict[str, Any] = {}

        # Active cancellation token for the currently-running task (if any).
        # Set when ``run_mode`` / ``start_task`` is invoked, cleared when
        # the worker finishes. ``cancel_active_run`` flips the token so the
        # cooperative cancellation points downstream can observe it.
        self._active_token: Optional[CancellationToken] = None
        self._lock = __import__("threading").Lock()

        # Single redactor instance — regexes are precompiled so reuse
        # is essentially free. The redactor runs on every user prompt
        # and every streamed chunk before they reach the model / UI.
        self._redactor = SecretRedactor()

        # Lazy-import mode handlers
        self._modes: dict[str, Any] = {}

    # ── Cancellation ─────────────────────────────────────────────────

    def cancel_active_run(self, reason: str = "cancelled by user") -> bool:
        """Cancel the currently-running agent task, if any.

        Returns True if a token was found and cancelled. False if no
        run is active. Cooperative cancellation — the worker will
        notice at the next safe checkpoint (between turns, between tool
        calls, before long ops) and exit cleanly.
        """
        with self._lock:
            token = self._active_token
        if token is None:
            return False
        token.cancel(reason)
        logger.info("Agent run cancellation requested: %s", reason)
        return True

    def is_active(self) -> bool:
        """True while a run is in progress."""
        return self._active_token is not None

    def _get_mode(self, mode_name: str) -> Any:
        """Lazy-load and cache mode handler."""
        if mode_name not in self._modes:
            if mode_name == "ask":
                from nexcoder.agent.modes.ask import AskMode
                self._modes["ask"] = AskMode()
            elif mode_name == "edit":
                from nexcoder.agent.modes.edit import EditMode
                self._modes["edit"] = EditMode()
            elif mode_name == "agent":
                from nexcoder.agent.modes.agent_mode import AgentMode
                self._modes["agent"] = AgentMode()
            elif mode_name == "debug":
                from nexcoder.agent.modes.debug import DebugMode
                self._modes["debug"] = DebugMode()
            elif mode_name == "review":
                from nexcoder.agent.modes.review import ReviewMode
                self._modes["review"] = ReviewMode()
            else:
                raise ValueError(f"Unknown mode: {mode_name}")
        return self._modes[mode_name]

    def run_mode(self, mode_name: str, prompt: str, context: dict[str, Any]) -> None:
        """Run an AI mode in a background thread."""
        self._emit_status("running", f"Starting {mode_name} mode...")

        # Make sure the context always carries a token, even if the
        # caller didn't supply one. The runtime owns the token so it can
        # cancel mid-run; downstream layers read it via ``get_token``.
        token = get_token(context) or CancellationToken()
        context["_cancellation_token"] = token
        with self._lock:
            self._active_token = token

        # Submit to thread pool so we don't block the UI
        self._executor.submit(self._run_mode_async, mode_name, prompt, context)

    def start_task(self, mode: str, prompt: str, context: dict[str, Any]) -> None:
        """Start a structured agent task that may bypass normal chat completion."""
        self._emit_status("running", f"Starting {mode} task...")

        token = get_token(context) or CancellationToken()
        context["_cancellation_token"] = token
        with self._lock:
            self._active_token = token

        self._executor.submit(self._run_task_async, mode, prompt, context)

    def _run_task_async(self, mode: str, prompt: str, context: dict[str, Any]) -> None:
        try:
            if mode != "scan":
                self._run_mode_async(mode, prompt, context)
                return

            project_root = context.get("project_path") or context.get("projectPath")
            if not project_root:
                raise ValueError("No active project root found in context")

            from nexcoder.agent.codebase_scanner import CodebaseScanner

            scanner = CodebaseScanner()
            step_counter = 0
            scan_step_ids: dict[str, str] = {}
            scan_step_started: dict[str, str] = {}
            configured_scan_delay = context.get("scanStepDelayMs")
            if configured_scan_delay is None:
                configured_scan_delay = os.getenv("NEXCODER_SCAN_STEP_DELAY_MS", "90")
            scan_step_delay = max(
                0.0,
                min(float(configured_scan_delay) / 1000.0, 0.5),
            )

            def classify_scan_step(message: str) -> dict[str, Any]:
                normalized = message.strip()

                if normalized.startswith("Reading ") and normalized.endswith("..."):
                    target = normalized.removeprefix("Reading ").removesuffix("...")
                    return {
                        "key": f"read:{target}",
                        "type": "tool_call",
                        "tool": "read_file",
                        "label": "Read file",
                        "target": target,
                        "result_summary": f"Reading {target}...",
                    }

                if normalized.startswith("Read "):
                    target = normalized.removeprefix("Read ")
                    return {
                        "key": f"read:{target}",
                        "type": "tool_call",
                        "tool": "read_file",
                        "label": "Read file",
                        "target": target,
                        "result_summary": "File read successfully",
                    }

                static_steps = {
                    "Listing project tree": {
                        "key": "list_project_tree",
                        "tool": "list_project_tree",
                        "label": "List project tree",
                        "target": ".",
                    },
                    "Indexing readable files": {
                        "key": "index_readable_files",
                        "tool": "list_project_tree",
                        "label": "Index readable files",
                        "target": ".",
                    },
                    "Detecting project type": {
                        "key": "detect_project_type",
                        "tool": "detect_project",
                        "label": "Detect project type",
                        "target": ".",
                    },
                    "Checking project warnings": {
                        "key": "check_project_warnings",
                        "tool": "inspect_project",
                        "label": "Check project warnings",
                        "target": ".",
                    },
                    "Saving project map": {
                        "key": "save_project_map",
                        "tool": "save_project_map",
                        "label": "Save project map",
                        "target": ".nexcoder/project_map.json",
                    },
                    "Summarizing project": {
                        "key": "summarize_project",
                        "tool": "summarize_project",
                        "label": "Summarize project",
                        "target": ".",
                    },
                    "Created project map": {
                        "key": "save_project_map",
                        "tool": "save_project_map",
                        "label": "Save project map",
                        "target": ".nexcoder/project_map.json",
                        "result_summary": "Project map saved",
                    },
                    "Detected project type": {
                        "key": "detect_project_type",
                        "tool": "detect_project",
                        "label": "Detect project type",
                        "target": ".",
                        "result_summary": "Project type detected",
                    },
                    "Checked project warnings": {
                        "key": "check_project_warnings",
                        "tool": "inspect_project",
                        "label": "Check project warnings",
                        "target": ".",
                        "result_summary": "Project warnings checked",
                    },
                    "Summarized project": {
                        "key": "summarize_project",
                        "tool": "summarize_project",
                        "label": "Summarize project",
                        "target": ".",
                        "result_summary": "Project summary prepared",
                    },
                }

                for prefix, step in (
                    ("Listed ", {
                        "key": "list_project_tree",
                        "tool": "list_project_tree",
                        "label": "List project tree",
                        "target": ".",
                    }),
                    ("Indexed ", {
                        "key": "index_readable_files",
                        "tool": "list_project_tree",
                        "label": "Index readable files",
                        "target": ".",
                    }),
                ):
                    if normalized.startswith(prefix):
                        return {
                            "type": "tool_call",
                            "result_summary": normalized,
                            **step,
                        }

                if normalized in static_steps:
                    return {
                        "type": "tool_call",
                        "result_summary": normalized,
                        **static_steps[normalized],
                    }

                key = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_") or "scan_step"
                return {
                    "key": key,
                    "type": "system",
                    "tool": None,
                    "label": normalized,
                    "target": None,
                    "result_summary": normalized,
                }

            def on_scan_status(status: str, message: str) -> None:
                nonlocal step_counter
                if status not in {"running", "scanning", "complete"}:
                    return

                meta = classify_scan_step(message)
                key = meta["key"]
                if key not in scan_step_ids:
                    step_counter += 1
                    scan_step_ids[key] = f"scan_{step_counter:03d}"
                    scan_step_started[key] = datetime.now(timezone.utc).isoformat()

                completed = status == "complete"
                now = datetime.now(timezone.utc).isoformat()
                self._emit_timeline({
                    "id": scan_step_ids[key],
                    "type": meta["type"],
                    "tool": meta["tool"],
                    "label": meta["label"],
                    "target": meta["target"],
                    "status": "completed" if completed else "running",
                    "started_at": scan_step_started[key],
                    "completed_at": now if completed else None,
                    "result_summary": meta["result_summary"] if completed else message,
                    "error": None,
                })

                if not completed and scan_step_delay > 0:
                    time.sleep(scan_step_delay)

            result = scanner.run(
                project_root,
                on_status=on_scan_status,
            )

            memory = self.get_memory(project_root)
            memory.set("project_map", result.get("project_map", {}))

            self._conversation_history.append({"role": "user", "content": prompt})

            self._emit_status("complete", "Scan complete")
            # The scanner returns a detailed raw report for persistence
            # and project-map use. The visible UI should render the
            # structured final_answer card only, otherwise scan results
            # appear twice as prose plus card.
            project_map = result.get("project_map", {})
            detected = project_map.get("detected", {})
            overview = project_map.get("overview", {})
            stack = overview.get("stack") or []
            notes = overview.get("notes") or []
            about = overview.get("description") or "No project description was found."
            stack_text = ", ".join(stack) if stack else "not clearly detected"
            scan_summary = (
                f"About: {about}\n\n"
                f"Stack: {stack_text}. "
                f"Scanned {project_map.get('files_scanned', 0)} readable file(s).\n\n"
                "Important notes:\n"
                + "\n".join(f"- {note}" for note in notes[:5])
            )
            self._conversation_history.append({"role": "assistant", "content": scan_summary})
            payload = dict(result)
            payload["response"] = ""
            payload["raw_scan_report"] = result.get("response", "")
            payload.setdefault("task_type", "scan")
            payload.setdefault("final_answer", {
                "type": "final_answer",
                "title": overview.get("name") or "Project Summary",
                "summary": scan_summary,
                "evidence": [
                    f"Project: {overview.get('name') or 'Unknown'}",
                    f"Source directory: {detected.get('source_directory', 'Not found')}",
                    f"Tests: {detected.get('tests', 'Not found')}",
                    f"Documentation: {detected.get('documentation', 'Not found')}",
                ],
                "files_used": project_map.get("important_files", []),
                "next_steps": [
                    "Ask a focused question about this project",
                    "Run an edit task when you want changes made",
                ],
            })
            self.completed.emit(json.dumps(payload))
        except AgentCancelledError as e:
            logger.info("Agent %s task cancelled: %s", mode, e.reason)
            self._emit_status("cancelled", e.reason)
            self.completed.emit(json.dumps({
                "success": False,
                "error": str(e),
                "error_kind": "agent_cancelled",
                "cancelled": True,
                "cancel_reason": e.reason,
                "mode": mode,
            }))
        except Exception as e:
            logger.error(f"Agent {mode} task error: {e}", exc_info=True)
            envelope = envelope_from_exception(e)
            envelope["mode"] = mode
            self._emit_status("error", envelope["message"])
            self.completed.emit(json.dumps({"success": False, **envelope, "mode": mode}))
        finally:
            with self._lock:
                self._active_token = None

    def _run_mode_async(self, mode_name: str, prompt: str, context: dict[str, Any]) -> None:
        """Execute the mode handler (runs in background thread)."""
        from nexcoder.agent.session import AgentSessionStore, SessionMetadata

        token = get_token(context)
        # Session persistence. The runtime owns one store per project
        # so concurrent sessions from the same project are all durable.
        # A session id is carried via the context (set by the bridge
        # for explicit resume), or generated fresh for new runs.
        project_root = (
            context.get("project_path")
            or context.get("projectPath")
            or ""
        )
        store: Optional[AgentSessionStore] = None
        session_meta: Optional[SessionMetadata] = None
        stored_history: list[dict[str, str]] = []
        if project_root and os.path.isdir(project_root):
            try:
                store = AgentSessionStore(project_root)
                sid = context.get("session_id") or context.get("sessionId")
                if sid:
                    try:
                        session_meta, stored_messages = store.load_session(sid)
                        stored_history = [
                            {"role": message.role, "content": message.content}
                            for message in stored_messages
                            if message.role in {"user", "assistant"} and message.content
                        ]
                    except (FileNotFoundError, ValueError):
                        session_meta = None
                if session_meta is None:
                    session_meta = store.create_session(
                        title=prompt[:64],
                        mode=mode_name,
                        session_id=sid,
                    )
                context["session_id"] = session_meta.session_id
                context["_session_store"] = store
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not initialise session store: %s", exc)
                store = None
                session_meta = None

        try:
            # Cooperative cancellation: bail before doing anything if the
            # user already cancelled between submit and execute.
            if token is not None:
                token.raise_if_cancelled()

            mode = self._get_mode(mode_name)
            normalized_root = os.path.abspath(project_root) if project_root else ""
            context["pending_changes"] = [
                dict(patch)
                for patch in self._pending_diffs.values()
                if not patch.get("project_root")
                or os.path.abspath(str(patch.get("project_root"))) == normalized_root
            ]

            # Redact the user prompt before it touches the model, the
            # session log, or the in-memory history. We keep the original
            # prompt only in the cancellation status so the user can
            # still see what they asked; everything else uses the
            # sanitised version.
            redaction = self._redactor.redact(prompt)
            sanitised_prompt = redaction.text
            if redaction.count:
                logger.info(
                    "Redacted %d item(s) from user prompt: %s",
                    redaction.count,
                    ", ".join(sorted(set(redaction.labels))),
                )

            # Conversation context is session-scoped. A process-global history
            # leaks turns between projects and made every follow-up look like a
            # new task, so only the selected session's prior messages are sent.
            conversation_history = list(stored_history)
            if not conversation_history:
                supplied_history = context.get("conversation_history") or context.get("history") or []
                conversation_history = [
                    {"role": item.get("role", ""), "content": item.get("content", "")}
                    for item in supplied_history
                    if item.get("role") in {"user", "assistant"} and item.get("content")
                ]
            context["conversation_history"] = conversation_history
            if store is not None and session_meta is not None:
                try:
                    meta = {"mode": mode_name}
                    if redaction.count:
                        meta["redactions"] = redaction.count
                        meta["redaction_labels"] = sorted(set(redaction.labels))
                    store.append_message(
                        session_meta.session_id, "user", sanitised_prompt,
                        metadata=meta,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to persist user message: %s", exc)

            # Build callbacks for streaming. The on_chunk callback
            # also redacts so a model that echoes back a secret the
            # user pasted never reaches the chat UI.
            def _emit_chunk(chunk: str) -> None:
                cleaned = self._redactor.redact(chunk).text
                self.stream_chunk.emit(cleaned)

            callbacks = {
                "on_chunk": _emit_chunk,
                "on_status": lambda status, msg: self._emit_status(status, msg),
                "on_plan": lambda plan: self._emit_status(
                    "plan_update", json.dumps(plan, ensure_ascii=False)
                ),
                "on_diff": lambda diff: self._handle_diff({
                    **diff,
                    "project_root": project_root,
                }),
                "on_timeline": lambda item: self._emit_timeline(item),
            }

            result = self._try_answer_from_project_context(
                mode_name=mode_name,
                prompt=sanitised_prompt,
                project_root=project_root,
            )
            if result:
                _emit_chunk(result["response"])
            else:
                # Run the mode with the sanitised prompt
                result = mode.execute(sanitised_prompt, context, conversation_history, callbacks)

            # Add assistant response to history (sanitised)
            if result and result.get("response"):
                assistant_response = self._redactor.redact(result["response"]).text
                result = {**result, "response": assistant_response}
                self._conversation_history.append({
                    "role": "assistant",
                    "content": assistant_response,
                })
                conversation_history.extend([
                    {"role": "user", "content": sanitised_prompt},
                    {"role": "assistant", "content": assistant_response},
                ])
                self._conversation_history = conversation_history[-24:]
                if store is not None and session_meta is not None:
                    try:
                        meta_payload = {
                            "task_type": result.get("task_type"),
                            "patches": result.get("patches", 0),
                            "mode": mode_name,
                        }
                        # The structured card payload is useful to keep
                        # alongside the prose for resume-with-context.
                        if result.get("final_answer"):
                            meta_payload["final_answer"] = result["final_answer"]
                        if result.get("plan"):
                            meta_payload["plan"] = result["plan"]
                        store.append_message(
                            session_meta.session_id, "assistant",
                            assistant_response, metadata=meta_payload,
                        )
                        store.set_status(
                            session_meta.session_id,
                            "complete" if result.get("success", True) else "error",
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Failed to persist assistant message: %s", exc)

            if result and result.get("success", True):
                self._emit_status("complete", f"{mode_name.capitalize()} complete")
            else:
                missing = ", ".join((result or {}).get("missing_files") or [])
                detail = f" Missing required files: {missing}." if missing else ""
                self._emit_status("error", f"{mode_name.capitalize()} did not complete.{detail}")
            # ``result`` may carry a structured ``final_answer`` and
            # ``task_type`` produced by the loop or the agentic runner.
            # Both are surfaced through ``agent_complete`` so the UI can
            # render the structured card in addition to the chat stream.
            payload = dict(result or {"success": True})
            if session_meta is not None:
                payload["session_id"] = session_meta.session_id
            self.completed.emit(json.dumps(payload))

        except AgentCancelledError as e:
            logger.info("Agent %s cancelled: %s", mode_name, e.reason)
            self._emit_status("cancelled", e.reason)
            if store is not None and session_meta is not None:
                try:
                    store.append_message(
                        session_meta.session_id, "assistant",
                        f"[Cancelled: {e.reason}]",
                        metadata={"mode": mode_name, "cancelled": True},
                    )
                    store.set_status(session_meta.session_id, "cancelled")
                except Exception:  # noqa: BLE001
                    pass
            payload = {
                "success": False,
                "error": str(e),
                "error_kind": "agent_cancelled",
                "cancelled": True,
                "cancel_reason": e.reason,
                "mode": mode_name,
            }
            if session_meta is not None:
                payload["session_id"] = session_meta.session_id
            self.completed.emit(json.dumps(payload))
        except Exception as e:
            logger.error(f"Agent {mode_name} error: {e}", exc_info=True)
            self._emit_status("error", str(e))
            # Surface structured error info so the UI can render a clear
            # error banner instead of a generic failure. AgentContractError
            # gets a dedicated error_kind; everything else falls through
            # as an envelope so the UI can branch on category/retryable.
            envelope = envelope_from_exception(e)
            envelope["mode"] = mode_name
            if store is not None and session_meta is not None:
                try:
                    store.set_status(session_meta.session_id, "error")
                except Exception:  # noqa: BLE001
                    pass
                envelope["session_id"] = session_meta.session_id
            self.completed.emit(json.dumps({"success": False, **envelope}))
        finally:
            with self._lock:
                self._active_token = None

    def _try_answer_from_project_context(
        self,
        *,
        mode_name: str,
        prompt: str,
        project_root: str,
    ) -> dict[str, Any] | None:
        """Answer simple project-map questions without waiting on the model."""
        if mode_name != "ask" or not project_root or not os.path.isdir(project_root):
            return None

        lower = prompt.lower()
        if any(term in lower for term in ("model", "models", "llm", "qwen", "gemma")):
            response = self._answer_project_models(project_root)
        elif self._is_project_overview_question(lower):
            response = self._answer_project_overview(project_root)
        else:
            return None

        return {
            "success": True,
            "response": response,
            "mode": mode_name,
            "task_type": "question",
            "patches": 0,
            "final_answer": {
                "type": "final_answer",
                "title": "Answer",
                "summary": response,
                "evidence": [],
                "files_used": [],
                "next_steps": [],
            },
        }

    def _is_project_overview_question(self, lower_prompt: str) -> bool:
        overview_terms = (
            "what is this project",
            "what this project",
            "what the project",
            "project is about",
            "project about",
            "what does this project",
            "explain this project",
            "explain the project",
            "tell me about this project",
            "tell me about the project",
            "describe this project",
            "describe the project",
            "project summary",
        )
        return any(term in lower_prompt for term in overview_terms)

    def _answer_project_models(self, project_root: str) -> str:
        root = Path(project_root)
        model_dir = root / "models" / "coder" / "Qwen2.5-Coder-7B-Instruct-GGUF"
        qwen_gguf = model_dir / "qwen2.5-coder-7b-instruct-q6_k.gguf"
        selector = root / "nexcoder" / "ui" / "src" / "components" / "TopBar" / "ModelSelector.tsx"

        presets = [
            "Qwen2.5-Coder-7B-Instruct (Q6_K, recommended)",
            "Gemma4-12B v2 Agentic (GGUF)",
            "Qwen2.5-Coder-3B (Local)",
            "Nexa Fast (Local)",
            "Nexa Pro (Local)",
            "GPT-4o (Cloud Fallback)",
            "Claude 3.5 Sonnet",
        ]
        if selector.exists():
            try:
                text = selector.read_text(encoding="utf-8", errors="replace")
                names = re.findall(r"name:\s*'([^']+)'", text)
                if names:
                    presets = names
            except Exception:
                pass

        lines = [
            "NexCoder is currently wired to use a local Qwen coding model by default.",
            "",
            "Primary local model:",
            f"- Qwen2.5-Coder-7B-Instruct GGUF Q6_K at `{qwen_gguf.relative_to(root).as_posix()}`"
            if qwen_gguf.exists()
            else "- Qwen2.5-Coder-7B-Instruct GGUF Q6_K is configured, but the GGUF file was not found.",
            "",
            "Model server:",
            "- `models/server.py` provides an OpenAI-compatible `/v1/chat/completions` API.",
            "- `models/start_api.bat` launches it on `http://127.0.0.1:8001`.",
            "",
            "Selectable UI presets:",
            *[f"- {name}" for name in presets],
            "",
            "Important note:",
            "- Gemma4 is still listed as an available preset, but the default/recommended local model is Qwen2.5-Coder-7B GGUF.",
        ]
        return "\n".join(lines)

    def _answer_project_overview(self, project_root: str) -> str:
        project_map = self._load_project_map(project_root)
        overview = project_map.get("overview", {}) if project_map else {}
        detected = project_map.get("detected", {}) if project_map else {}
        root = Path(project_root)
        project_name = overview.get("name") or root.name or "this project"
        description = overview.get("description") or "NexCoder"
        stack = overview.get("stack") or []
        stack_text = ", ".join(stack) if stack else "Python desktop app with a React/TypeScript frontend"
        source_dir = detected.get("source_directory") or "nexcoder"
        tests_dir = detected.get("tests") or "Not found"
        entry_points = detected.get("entry_points") or []

        if not overview:
            return (
                "NexCoder is a local AI-first code editor for the Nexa ecosystem. "
                "It combines a PySide6 desktop shell, an embedded React/TypeScript "
                "Monaco editor, a terminal, project tools, and a Python agent runtime "
                "that can inspect files, build project context, propose edits, and run "
                "verification steps."
            )

        lines = [
            f"{description} is a local AI-first coding editor for the Nexa ecosystem. "
            "The important point is that it is meant to behave like an agentic IDE, not "
            "just a chat box next to a file tree.",
            "",
            "What it does:",
            "- Opens local projects in a desktop editor shell.",
            "- Shows a React/TypeScript Monaco editor inside Qt WebEngine.",
            "- Bridges the UI to Python services with QWebChannel.",
            "- Provides terminal, file explorer, git/diff, scan, ask, edit, and review workflows.",
            "- Runs local coding models through an OpenAI-compatible server instead of requiring a cloud API.",
            "",
            "How it is built:",
            "- Desktop shell: PySide6 and QWebEngineView.",
            "- Frontend: React, TypeScript, Monaco, Zustand, Vite, xterm.js, and Lucide icons.",
            "- Python bridge/services: filesystem, terminal, project scanning, patch review, sessions, and model calls.",
            "- Agent runtime: structured tools, timeline items, codebase scanning, and Hermes-inspired execution patterns.",
            f"- Detected stack: {stack_text}.",
            f"- Primary source directory: `{source_dir}`.",
            f"- Tests: `{tests_dir}`.",
            "",
            "Main areas to know:",
            "- `nexcoder/main.py` and `nexcoder/app.py` start the desktop application.",
            "- `nexcoder/bridge.py` is the Python-to-frontend bridge used by the UI.",
            "- `nexcoder/ui` contains the React editor interface.",
            "- `nexcoder/agent` contains the scan, ask, edit, tool execution, and agent runtime logic.",
            "- `models/server.py` runs the local OpenAI-compatible model API.",
            "- `build.py` and `nexcoder.spec` package the app into `dist/NexCoder` with PyInstaller.",
            "",
            "Important notes:",
            "- The current product direction is a Cursor-style local coding agent for Nexa, not a generic chatbot.",
            "- Scan results are saved into `.nexcoder/project_map.json` and reused for faster project questions.",
            "- The local model path is centered around Qwen2.5-Coder GGUF, with other presets available in the UI.",
            "- Because the app embeds Chromium through Qt WebEngine, packaged builds are expected to be much larger than a plain Python tool.",
            "- Edit tasks should inspect files, propose or apply patches, then run a verification command when the runtime can infer one.",
        ]
        if entry_points:
            lines.extend([
                "",
                "Detected entry points:",
                *[f"- `{entry}`" for entry in entry_points[:6]],
            ])
        return "\n".join(lines)

    def _load_project_map(self, project_root: str) -> dict[str, Any]:
        path = Path(project_root) / ".nexcoder" / "project_map.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _handle_diff(self, diff_data: dict) -> None:
        """Store a pending diff and notify the frontend."""
        supersedes = {
            str(path).replace("\\", "/")
            for path in diff_data.get("supersedes", [])
            if path
        }
        target = str(diff_data.get("file") or "").replace("\\", "/")
        project_root = os.path.abspath(str(diff_data.get("project_root") or ""))
        replaced_ids: list[str] = []
        for existing_id, existing in list(self._pending_diffs.items()):
            existing_root = os.path.abspath(str(existing.get("project_root") or ""))
            existing_target = str(existing.get("file") or "").replace("\\", "/")
            if project_root and existing_root and project_root != existing_root:
                continue
            if existing_target == target or existing_target in supersedes:
                self._pending_diffs.pop(existing_id, None)
                replaced_ids.append(existing_id)

        diff_id = str(uuid.uuid4())[:8]
        diff_data["id"] = diff_id
        if replaced_ids:
            diff_data["replaces_diff_ids"] = replaced_ids
        # If this diff includes multiple patches, tag as patchset
        if isinstance(diff_data.get("patches"), list) and len(diff_data.get("patches")) > 1:
            diff_data["type"] = "patchset"

        self._pending_diffs[diff_id] = diff_data
        self.diff_ready.emit(json.dumps(diff_data))

    def approve_diff(self, diff_id: str, project_root: str | None = None) -> None:
        """Approve and apply a pending diff."""
        if project_root:
            self.approve_patchset([diff_id], project_root)
            return
        diff = self._pending_diffs.pop(diff_id, None)
        if not diff:
            raise ValueError(f"Diff not found: {diff_id}")

        from nexcoder.agent.patch_generator import PatchGenerator
        from nexcoder.services.checkpoint import CheckpointManager

        patch_gen = PatchGenerator(project_root)

        # If patchset, apply atomically
        if diff.get("type") == "patchset" and isinstance(diff.get("patches"), list):
            # Create checkpoint for all files involved
            files = [p.get("file") for p in diff.get("patches", []) if p.get("file")]
            cp = CheckpointManager(project_root)
            checkpoint_id = cp.create([os.path.join(project_root, f) for f in files], label=f"diff-{diff_id}")
            try:
                patch_gen.apply_patchset(diff["patches"])
            except Exception as e:
                # On failure, attempt restore
                try:
                    cp.restore(checkpoint_id, [os.path.join(project_root, f) for f in files])
                except Exception:
                    logger.error("Failed to restore after failed patchset apply")
                raise
            return

        # Single-file patch object compatibility
        try:
            patch_gen.apply_patch(diff)
        except Exception as e:
            logger.error(f"Failed to apply diff {diff_id}: {e}")
            raise

    def approve_patchset(self, diff_ids: list[str], project_root: str) -> dict[str, Any]:
        """Apply a reviewed set of pending diffs as one atomic operation."""
        from nexcoder.agent.patch_generator import PatchGenerator
        from nexcoder.services.checkpoint import CheckpointManager

        if not diff_ids:
            raise ValueError("No pending changes selected")

        missing = [diff_id for diff_id in diff_ids if diff_id not in self._pending_diffs]
        if missing:
            raise ValueError(f"Pending changes not found: {', '.join(missing)}")

        patches = [dict(self._pending_diffs[diff_id]) for diff_id in diff_ids]
        files: list[str] = []
        for patch in patches:
            for candidate in (patch.get("file"), patch.get("source")):
                if candidate and candidate not in files:
                    files.append(str(candidate))
        checkpoint_mgr = CheckpointManager(project_root)
        checkpoint_id = checkpoint_mgr.create(
            [os.path.join(project_root, file_path) for file_path in files],
            label="agent-patchset",
        )
        patch_gen = PatchGenerator(project_root)

        try:
            patch_gen.apply_patchset(patches)
            mismatched: list[str] = []
            for patch in patches:
                file_path = patch.get("file")
                action = patch.get("action")
                if not file_path:
                    continue
                target = os.path.join(project_root, file_path)
                if action == "mkdir":
                    if not os.path.isdir(target):
                        mismatched.append(file_path)
                    continue
                if action in {"delete", "rmdir"}:
                    if os.path.exists(target):
                        mismatched.append(file_path)
                    continue
                if action == "move":
                    source = os.path.join(project_root, str(patch.get("source") or ""))
                    if os.path.exists(source):
                        mismatched.append(str(patch.get("source")))
                expected = patch.get("content")
                if not os.path.isfile(target):
                    mismatched.append(file_path)
                    continue
                if isinstance(expected, str):
                    actual = Path(target).read_text(encoding="utf-8", errors="replace")
                    if actual != expected:
                        mismatched.append(file_path)
            if mismatched:
                raise IOError("Applied file verification failed: " + ", ".join(mismatched))
        except Exception:
            checkpoint_mgr.restore(
                checkpoint_id,
                [os.path.join(project_root, file_path) for file_path in files],
            )
            raise

        for diff_id in diff_ids:
            self._pending_diffs.pop(diff_id, None)

        return {
            "checkpoint_id": checkpoint_id,
            "files": files,
            "validation": {
                "success": True,
                "label": "Verified applied files",
                "files_checked": len(files),
            },
        }

    def reject_diff(self, diff_id: str, project_root: str | None = None) -> None:
        """Reject a pending diff (rolls back modifications using CheckpointManager)."""
        diff = self._pending_diffs.pop(diff_id, None)
        if diff and diff.get("checkpoint_id") and project_root:
            checkpoint_id = diff["checkpoint_id"]
            file_path = diff.get("file", "")
            if file_path:
                try:
                    from nexcoder.services.checkpoint import CheckpointManager
                    checkpoint_mgr = CheckpointManager(project_root)
                    checkpoint_mgr.restore(checkpoint_id, [file_path])
                    logger.info(f"Successfully rolled back file {file_path} from checkpoint {checkpoint_id}")
                except Exception as e:
                    logger.error(f"Failed to roll back file {file_path} in reject_diff: {e}")

    def get_memory(self, project_root: str) -> Any:
        """Return an AgentMemory instance for the project (cached)."""
        if project_root in self._memory_managers:
            return self._memory_managers[project_root]
        from nexcoder.agent.memory import AgentMemory
        mem = AgentMemory(project_root)
        mem.load()
        self._memory_managers[project_root] = mem
        return mem

    # ── Sessions ─────────────────────────────────────────────────────

    def get_session_store(self, project_root: str) -> Any:
        """Return an :class:`AgentSessionStore` for *project_root*.

        The store is cached on the instance so multiple bridge calls
        share the same on-disk lock. The store is also safe to drop —
        callers can re-instantiate it at any time.
        """
        from nexcoder.agent.session import AgentSessionStore

        if not hasattr(self, "_session_stores"):
            self._session_stores: dict[str, Any] = {}
        cache = self._session_stores
        if project_root in cache:
            return cache[project_root]
        store = AgentSessionStore(project_root)
        cache[project_root] = store
        return store

    def _emit_status(self, status: str, message: str) -> None:
        """Emit a status update to the frontend."""
        self.status_update.emit(json.dumps({"status": status, "message": message}))

    def _emit_timeline(self, item: dict[str, Any]) -> None:
        """Emit a structured timeline item to the frontend."""
        self.status_update.emit(json.dumps({
            "status": "timeline",
            "message": item.get("label") or item.get("tool") or "Agent step",
            "timeline_item": item,
        }))

    def set_ai_settings(self, endpoint: str, model: str) -> None:
        """Update active AI settings globally."""
        import os
        os.environ["NEXA_API_URL"] = endpoint
        os.environ["NEXA_MODEL"] = model
        for mode in self._modes.values():
            if hasattr(mode, "_model"):
                mode._model.set_endpoint(endpoint)
                mode._model.set_model(model)

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._conversation_history.clear()
