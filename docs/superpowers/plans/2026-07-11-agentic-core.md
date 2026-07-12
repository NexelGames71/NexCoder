# NexCoder Agentic Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild NexCoder's agent into a Cursor-class agentic loop: direct file edits with checkpoint revert, permission-gated commands, self-verification, repo map, live todo list, and context compaction — working against the local Qwen 7B (XML tool calls) today and the team's GPU-hosted model (native function calling) later.

**Architecture:** New package `nexcoder/agent/core/` holds a mode-agnostic `AgentLoop`, a `ToolCallAdapter` transport layer (XmlAdapter / NativeAdapter), a `Conversation` with compaction, and one module per tool. Reuses existing `CheckpointManager`, `SafetyChecker`, `ToolGuardrailController`, `AgentTrajectoryRecorder`, `tool_call_parser`, `path_filters`, `skills_registry`. The old `hermes_runtime.py` keeps serving until acceptance passes (Task 16).

**Tech Stack:** Python 3.11 (stdlib + httpx, already a dep), pytest, PySide6/QWebChannel bridge, React + TypeScript + zustand UI.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-11-agentic-core-design.md`. Backend config seam: `{base_url, model, api_key, adapter: "xml"|"native", context_window}`.
- No new Python runtime dependencies. Windows-first (`shell=True` commands, CRLF-safe file handling).
- Tool results are plain dicts with a `success: bool` key (existing codebase idiom). Tool handlers never raise to the loop.
- All new-core tests live under `tests/core/`. Test command: `venv\Scripts\python.exe -m pytest tests\core -q`.
- Every task ends with a commit. Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- File writes by tools always snapshot into the run checkpoint BEFORE mutating (revert-all must always work).
- The agent's `run_command` refuses SafetyChecker-blocked commands unconditionally, in every gate mode.

---

### Task 1: Typed event stream (`events.py`)

**Files:**
- Create: `nexcoder/agent/core/__init__.py`, `nexcoder/agent/core/events.py`
- Test: `tests/core/test_events.py`

**Interfaces:**
- Produces: `AgentEvent(type, payload, ts)` frozen dataclass with `.to_dict()`; `EventCallback = Callable[[AgentEvent], None]`; `EventType` literal.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_events.py
from nexcoder.agent.core.events import AgentEvent


def test_event_to_dict_roundtrip():
    event = AgentEvent(type="tool_started", payload={"tool": "read_file"})
    data = event.to_dict()
    assert data["type"] == "tool_started"
    assert data["payload"] == {"tool": "read_file"}
    assert isinstance(data["ts"], float)


def test_event_default_payload_is_empty_dict():
    event = AgentEvent(type="run_started")
    assert event.payload == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_events.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/__init__.py
"""NexCoder agentic core: loop, transport adapters, conversation, tools."""
```

```python
# nexcoder/agent/core/events.py
"""Typed event stream shared by the agent loop, CLI renderer, and UI bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Literal

EventType = Literal[
    "run_started",
    "turn_started",
    "text_delta",
    "tool_started",
    "tool_result",
    "command_output",
    "todo_updated",
    "edit_applied",
    "permission_request",
    "permission_resolved",
    "checkpoint_created",
    "compaction",
    "run_completed",
    "run_error",
]


@dataclass(frozen=True)
class AgentEvent:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload, "ts": self.ts}


EventCallback = Callable[[AgentEvent], None]
```

Also create empty `tests/core/__init__.py` if pytest needs it (it does not; skip unless collection fails).

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_events.py -q`
Expected: 2 passed

- [ ] **Step 5: Commit** — `feat(core): typed agent event stream`

---

### Task 2: Tool belt foundation (`tools/base.py`) + `CheckpointManager.add_file`

**Files:**
- Create: `nexcoder/agent/core/tools/__init__.py`, `nexcoder/agent/core/tools/base.py`
- Modify: `nexcoder/services/checkpoint.py` (add `add_file`)
- Test: `tests/core/test_tool_base.py`, `tests/core/test_checkpoint_add_file.py`

**Interfaces:**
- Consumes: `AgentEvent`, `EventCallback` (Task 1); `CheckpointManager`, `SafetyChecker` (existing).
- Produces:
  - `ToolContext(project_root, emit, checkpoints=None, safety=None, permission_gate=None, run_id="")` with `.resolve(target) -> Path | None`, `.snapshot_before_mutation(relative_path)`, `.mutated_files: set[str]`, `.checkpoint_id: str | None`, `.todos: list[dict]`.
  - `ToolSpec(name, description, parameters, handler, mutating=False)` with `.openai_schema()`.
  - `ToolBelt` with `.register(spec)`, `.get(name)`, `.names`, `.schemas()`, `.execute(name, args, ctx) -> dict`.
  - `PermissionGate` protocol: `request(*, tool: str, detail: str) -> str` returning `"allow" | "allow_always" | "deny"`; `AllowAllGate`.
  - `CheckpointManager.add_file(checkpoint_id: str, file_path: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_checkpoint_add_file.py
import json
import os

from nexcoder.services.checkpoint import CheckpointManager


def test_add_file_snapshots_and_restores(tmp_path):
    (tmp_path / "a.txt").write_text("A1", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B1", encoding="utf-8")
    manager = CheckpointManager(str(tmp_path))
    cp_id = manager.create([str(tmp_path / "a.txt")], label="run")
    manager.add_file(cp_id, str(tmp_path / "b.txt"))
    (tmp_path / "a.txt").write_text("A2", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B2", encoding="utf-8")
    manager.restore(cp_id)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "A1"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "B1"


def test_add_file_missing_file_marks_not_existed_and_restore_deletes(tmp_path):
    (tmp_path / "a.txt").write_text("A1", encoding="utf-8")
    manager = CheckpointManager(str(tmp_path))
    cp_id = manager.create([str(tmp_path / "a.txt")], label="run")
    manager.add_file(cp_id, str(tmp_path / "new.txt"))  # does not exist yet
    (tmp_path / "new.txt").write_text("created later", encoding="utf-8")
    manager.restore(cp_id)
    assert not (tmp_path / "new.txt").exists()


def test_add_file_is_idempotent(tmp_path):
    (tmp_path / "a.txt").write_text("A1", encoding="utf-8")
    manager = CheckpointManager(str(tmp_path))
    cp_id = manager.create([str(tmp_path / "a.txt")], label="run")
    manager.add_file(cp_id, str(tmp_path / "a.txt"))
    cp_dir = os.path.join(str(tmp_path), ".nexcoder", "checkpoints", cp_id)
    with open(os.path.join(cp_dir, "manifest.json")) as fh:
        manifest = json.load(fh)
    assert len(manifest["files"]) == 1
```

```python
# tests/core/test_tool_base.py
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import AllowAllGate, ToolBelt, ToolContext, ToolSpec


def make_ctx(tmp_path, events=None):
    return ToolContext(
        project_root=tmp_path,
        emit=(events.append if events is not None else (lambda _e: None)),
        run_id="run_test",
    )


def test_belt_registers_and_executes(tmp_path):
    def hello(args, ctx):
        return {"success": True, "greeting": f"hi {args['name']}"}

    belt = ToolBelt()
    belt.register(ToolSpec(
        name="hello", description="Say hi",
        parameters={"type": "object", "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
        handler=hello))
    result = belt.execute("hello", {"name": "world"}, make_ctx(tmp_path))
    assert result == {"success": True, "greeting": "hi world"}
    assert belt.names == ("hello",)
    schema = belt.schemas()[0]
    assert schema["function"]["name"] == "hello"


def test_belt_unknown_tool_and_exception_are_error_results(tmp_path):
    def boom(args, ctx):
        raise RuntimeError("kaboom")

    belt = ToolBelt()
    belt.register(ToolSpec(name="boom", description="", parameters={"type": "object", "properties": {}}, handler=boom))
    assert belt.execute("nope", {}, make_ctx(tmp_path))["error_code"] == "unknown_tool"
    result = belt.execute("boom", {}, make_ctx(tmp_path))
    assert result["success"] is False
    assert result["error_code"] == "tool_exception"
    assert "kaboom" in result["error"]


def test_context_resolve_blocks_escape(tmp_path):
    ctx = make_ctx(tmp_path)
    assert ctx.resolve("sub/file.txt") is not None
    assert ctx.resolve("..") is None
    assert ctx.resolve("../outside.txt") is None


def test_snapshot_before_mutation_creates_then_extends_checkpoint(tmp_path):
    (tmp_path / "one.txt").write_text("1", encoding="utf-8")
    (tmp_path / "two.txt").write_text("2", encoding="utf-8")
    events: list[AgentEvent] = []
    ctx = make_ctx(tmp_path, events)
    ctx.snapshot_before_mutation("one.txt")
    first_id = ctx.checkpoint_id
    assert first_id is not None
    ctx.snapshot_before_mutation("two.txt")
    ctx.snapshot_before_mutation("one.txt")  # no-op
    assert ctx.checkpoint_id == first_id
    assert ctx.mutated_files == {"one.txt", "two.txt"}
    assert [e.type for e in events] == ["checkpoint_created"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_tool_base.py tests\core\test_checkpoint_add_file.py -q`
Expected: FAIL (no `add_file`, no `tools.base` module)

- [ ] **Step 3: Implement**

Append to `nexcoder/services/checkpoint.py` (inside `CheckpointManager`, after `restore`):

```python
    def add_file(self, checkpoint_id: str, file_path: str) -> None:
        """Snapshot one more file into an existing checkpoint.

        No-op when the file is already captured, so the agent loop can call
        this on every mutation without tracking what the checkpoint holds.
        A missing file is recorded with ``existed: False`` so restore()
        deletes it (reverting a file the agent created).
        """
        cp_dir = os.path.join(self._checkpoints_dir(), checkpoint_id)
        manifest_path = os.path.join(cp_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        abs_path = os.path.abspath(file_path)
        try:
            rel_path = os.path.relpath(abs_path, self._root)
        except ValueError:
            rel_path = os.path.basename(abs_path)
        rel_norm = rel_path.replace("\\", "/")
        if any(item.get("relative") == rel_norm for item in manifest["files"]):
            return
        if os.path.isfile(abs_path):
            dest = os.path.join(cp_dir, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(abs_path, dest)
            entry = {"original": abs_path.replace("\\", "/"), "relative": rel_norm,
                     "size": os.path.getsize(abs_path), "existed": True, "type": "file"}
        else:
            entry = {"original": abs_path.replace("\\", "/"), "relative": rel_norm,
                     "size": 0, "existed": False, "type": "missing"}
        manifest["files"].append(entry)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
```

```python
# nexcoder/agent/core/tools/__init__.py
"""Agent core tool modules. Each module registers ToolSpecs onto a ToolBelt."""
```

```python
# nexcoder/agent/core/tools/base.py
"""ToolSpec / ToolBelt / ToolContext — the contract every core tool follows."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable, Protocol

from nexcoder.agent.core.events import AgentEvent, EventCallback
from nexcoder.agent.safety import SafetyChecker
from nexcoder.services.checkpoint import CheckpointManager

ALLOW = "allow"
ALLOW_ALWAYS = "allow_always"
DENY = "deny"


class PermissionGate(Protocol):
    def request(self, *, tool: str, detail: str) -> str: ...


class AllowAllGate:
    def request(self, *, tool: str, detail: str) -> str:
        return ALLOW


class ToolContext:
    """Everything a tool handler needs beyond its own args."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        emit: EventCallback,
        checkpoints: CheckpointManager | None = None,
        safety: SafetyChecker | None = None,
        permission_gate: PermissionGate | None = None,
        run_id: str = "",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.emit = emit
        self.checkpoints = checkpoints or CheckpointManager(str(self.project_root))
        self.safety = safety or SafetyChecker()
        self.permission_gate = permission_gate or AllowAllGate()
        self.run_id = run_id
        self.checkpoint_id: str | None = None
        self.mutated_files: set[str] = set()
        self.todos: list[dict[str, Any]] = []

    def resolve(self, target: str) -> Path | None:
        """Resolve a project-relative path; None when it escapes the root."""
        try:
            path = (self.project_root / (target or ".")).resolve()
            common = os.path.commonpath([str(self.project_root), str(path)])
        except (OSError, ValueError):
            return None
        return path if common == str(self.project_root) else None

    def snapshot_before_mutation(self, relative_path: str) -> None:
        """Capture the pre-edit state of a file into the run checkpoint."""
        if relative_path in self.mutated_files:
            return
        absolute = str(self.project_root / relative_path)
        if self.checkpoint_id is None:
            self.checkpoint_id = self.checkpoints.create(
                [absolute], label=f"agent-run {self.run_id}")
            self.emit(AgentEvent("checkpoint_created", {
                "checkpoint_id": self.checkpoint_id, "run_id": self.run_id}))
        else:
            self.checkpoints.add_file(self.checkpoint_id, absolute)
        self.mutated_files.add(relative_path)


ToolHandler = Callable[[dict[str, Any], ToolContext], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    handler: ToolHandler
    mutating: bool = False

    def openai_schema(self) -> dict[str, Any]:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters}}


class ToolBelt:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Duplicate tool: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def schemas(self) -> list[dict[str, Any]]:
        return [spec.openai_schema() for spec in self._specs.values()]

    def execute(self, name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        spec = self._specs.get(name)
        if spec is None:
            return {"success": False, "error_code": "unknown_tool",
                    "error": f"Unknown tool: {name}"}
        try:
            return spec.handler(args, ctx)
        except Exception as exc:  # tool bugs become observations, never crashes
            return {"success": False, "error_code": "tool_exception",
                    "error": f"{type(exc).__name__}: {exc}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_tool_base.py tests\core\test_checkpoint_add_file.py -q`
Expected: 7 passed

- [ ] **Step 5: Run the full existing suite (checkpoint change is shared code)**

Run: `venv\Scripts\python.exe -m pytest tests -q`
Expected: no new failures vs. baseline

- [ ] **Step 6: Commit** — `feat(core): tool belt foundation and incremental checkpoints`

---

### Task 3: Transport adapters (`transport.py`)

**Files:**
- Create: `nexcoder/agent/core/transport.py`
- Test: `tests/core/test_transport.py`

**Interfaces:**
- Consumes: `parse_tool_calls`, `strip_tool_calls`, `ToolCallParseError` (existing `tool_call_parser`).
- Produces:
  - `ToolCall(id, name, args)` frozen dataclass.
  - `ModelTurn(text, tool_calls: tuple[ToolCall, ...], parse_error: str | None)`.
  - `ToolCallAdapter` protocol: `request_extras(schemas) -> dict`, `system_prompt_suffix(schemas) -> str`, `parse_assistant_message(message: dict) -> ModelTurn`, `tool_result_messages(calls, results) -> list[dict]`.
  - `XmlAdapter`, `NativeAdapter`, `get_adapter(name: str) -> ToolCallAdapter`.

- [ ] **Step 1: Write the failing test** — the equivalence fixture is the core of this task: both adapters must produce identical `(name, args)` sequences from equivalent model output.

```python
# tests/core/test_transport.py
import json

from nexcoder.agent.core.transport import (
    ModelTurn, NativeAdapter, ToolCall, XmlAdapter, get_adapter,
)

SCHEMAS = [{"type": "function", "function": {
    "name": "read_file", "description": "Read a file",
    "parameters": {"type": "object",
                   "properties": {"path": {"type": "string"}},
                   "required": ["path"]}}}]


def test_adapters_parse_equivalent_calls_identically():
    xml_message = {"role": "assistant", "content":
                   'Reading it now.\n<tool_call name="read_file">{"path": "app.py"}</tool_call>'}
    native_message = {"role": "assistant", "content": "Reading it now.",
                      "tool_calls": [{"id": "call_1", "type": "function", "function": {
                          "name": "read_file", "arguments": '{"path": "app.py"}'}}]}
    xml_turn = XmlAdapter().parse_assistant_message(xml_message)
    native_turn = NativeAdapter().parse_assistant_message(native_message)
    assert [(c.name, c.args) for c in xml_turn.tool_calls] == \
           [(c.name, c.args) for c in native_turn.tool_calls] == [("read_file", {"path": "app.py"})]
    assert xml_turn.text == native_turn.text == "Reading it now."


def test_xml_adapter_reports_parse_error_not_exception():
    turn = XmlAdapter().parse_assistant_message(
        {"role": "assistant", "content": '<tool_call name="read_file">{bad json</tool_call>'})
    assert turn.tool_calls == ()
    assert turn.parse_error and "read_file" in turn.parse_error


def test_native_adapter_reports_bad_arguments_json():
    turn = NativeAdapter().parse_assistant_message(
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
         "function": {"name": "read_file", "arguments": "{oops"}}]})
    assert turn.tool_calls == ()
    assert turn.parse_error


def test_request_extras_and_prompt_suffix():
    assert XmlAdapter().request_extras(SCHEMAS) == {}
    assert NativeAdapter().request_extras(SCHEMAS) == {"tools": SCHEMAS}
    suffix = XmlAdapter().system_prompt_suffix(SCHEMAS)
    assert "read_file" in suffix and "tool_call" in suffix
    assert NativeAdapter().system_prompt_suffix(SCHEMAS) == ""


def test_tool_result_messages_shapes():
    calls = [ToolCall(id="c1", name="read_file", args={"path": "a"})]
    results = [{"success": True, "content": "hello"}]
    xml_msgs = XmlAdapter().tool_result_messages(calls, results)
    assert len(xml_msgs) == 1 and xml_msgs[0]["role"] == "user"
    assert "<tool_response>" in xml_msgs[0]["content"]
    native_msgs = NativeAdapter().tool_result_messages(calls, results)
    assert native_msgs[0]["role"] == "tool"
    assert native_msgs[0]["tool_call_id"] == "c1"
    assert json.loads(native_msgs[0]["content"])["success"] is True


def test_get_adapter():
    assert isinstance(get_adapter("xml"), XmlAdapter)
    assert isinstance(get_adapter("native"), NativeAdapter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_transport.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/transport.py
"""Tool-call transport adapters.

The loop never knows how tool calls travel. XmlAdapter keeps the local
Qwen-7B path (calls embedded in text); NativeAdapter speaks the OpenAI
tools / tool_calls protocol for the future GPU-hosted model. Switching
backend = switching adapter, zero loop changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol
import uuid

from nexcoder.agent.tool_call_parser import (
    ToolCallParseError, parse_tool_calls, strip_tool_calls,
)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    parse_error: str | None = None


class ToolCallAdapter(Protocol):
    def request_extras(self, schemas: list[dict[str, Any]]) -> dict[str, Any]: ...
    def system_prompt_suffix(self, schemas: list[dict[str, Any]]) -> str: ...
    def parse_assistant_message(self, message: dict[str, Any]) -> ModelTurn: ...
    def tool_result_messages(
        self, calls: list[ToolCall], results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


def _new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:8]}"


class XmlAdapter:
    """Tool calls embedded in assistant text as <tool_call> blocks."""

    def request_extras(self, schemas: list[dict[str, Any]]) -> dict[str, Any]:
        return {}

    def system_prompt_suffix(self, schemas: list[dict[str, Any]]) -> str:
        lines = [
            "",
            "# Tools",
            "Call tools by emitting one or more blocks exactly like:",
            '<tool_call name="tool_name">{"arg": "value"}</tool_call>',
            "Arguments must be a single valid JSON object.",
            "",
            "Available tools:",
        ]
        for schema in schemas:
            fn = schema["function"]
            props = fn["parameters"].get("properties", {})
            required = set(fn["parameters"].get("required", []))
            args_desc = ", ".join(
                f"{name}{'' if name in required else '?'}: {spec.get('type', 'any')}"
                for name, spec in props.items())
            lines.append(f"- {fn['name']}({args_desc}) — {fn['description']}")
        lines += [
            "",
            "Only emit a tool_call block when you want the tool executed. "
            "When the task is complete, reply with plain text and no tool_call blocks.",
        ]
        return "\n".join(lines)

    def parse_assistant_message(self, message: dict[str, Any]) -> ModelTurn:
        text = str(message.get("content") or "")
        try:
            parsed = parse_tool_calls(text)
        except ToolCallParseError as exc:
            return ModelTurn(text=strip_tool_calls(text).strip(), parse_error=str(exc))
        calls = tuple(
            ToolCall(id=_new_call_id(), name=item.tool, args=item.args)
            for item in parsed)
        return ModelTurn(text=strip_tool_calls(text).strip(), tool_calls=calls)

    def tool_result_messages(
        self, calls: list[ToolCall], results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        blocks = []
        for call, result in zip(calls, results):
            payload = json.dumps({"tool": call.name, "result": result},
                                 ensure_ascii=False, default=str)
            blocks.append(f"<tool_response>{payload}</tool_response>")
        return [{"role": "user", "content": "\n".join(blocks)}]


class NativeAdapter:
    """OpenAI tools / tool_calls protocol (vLLM, TGI, cloud APIs)."""

    def request_extras(self, schemas: list[dict[str, Any]]) -> dict[str, Any]:
        return {"tools": schemas} if schemas else {}

    def system_prompt_suffix(self, schemas: list[dict[str, Any]]) -> str:
        return ""

    def parse_assistant_message(self, message: dict[str, Any]) -> ModelTurn:
        calls: list[ToolCall] = []
        parse_error: str | None = None
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            name = str(fn.get("name") or "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                parse_error = f"Invalid JSON arguments for {name}: {exc.msg}"
                continue
            if not isinstance(args, dict):
                parse_error = f"Arguments for {name} must be a JSON object"
                continue
            calls.append(ToolCall(id=str(raw.get("id") or _new_call_id()),
                                  name=name, args=args))
        return ModelTurn(text=str(message.get("content") or "").strip(),
                         tool_calls=tuple(calls), parse_error=parse_error)

    def tool_result_messages(
        self, calls: list[ToolCall], results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {"role": "tool", "tool_call_id": call.id,
             "content": json.dumps(result, ensure_ascii=False, default=str)}
            for call, result in zip(calls, results)
        ]


def get_adapter(name: str) -> ToolCallAdapter:
    if name == "xml":
        return XmlAdapter()
    if name == "native":
        return NativeAdapter()
    raise ValueError(f"Unknown adapter: {name!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_transport.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit** — `feat(core): XML and native tool-call transport adapters`

---

### Task 4: Conversation with compaction (`conversation.py`)

**Files:**
- Create: `nexcoder/agent/core/conversation.py`
- Test: `tests/core/test_conversation.py`

**Interfaces:**
- Produces:
  - `estimate_tokens(text) -> int`, `message_tokens(message) -> int`.
  - `Conversation(system_prompt, *, context_window=8192, reserve_output=3072, compact_threshold=0.75)` with `.add(message)`, `.messages()`, `.payload_messages()` (strips keys starting `_`), `.total_tokens()`, `.needs_compaction()`, `.compact(summarizer=None) -> {"before": int, "after": int}`, `.input_budget`.
  - `Summarizer = Callable[[list[dict]], str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_conversation.py
from nexcoder.agent.core.conversation import Conversation


def make_convo(**kwargs):
    defaults = dict(context_window=1000, reserve_output=200, compact_threshold=0.5)
    defaults.update(kwargs)
    return Conversation("system prompt", **defaults)


def test_payload_messages_strip_private_keys():
    convo = make_convo()
    convo.add({"role": "user", "content": "hi", "_compacted": True})
    payload = convo.payload_messages()
    assert payload[0] == {"role": "system", "content": "system prompt"}
    assert payload[1] == {"role": "user", "content": "hi"}


def test_needs_compaction_threshold():
    convo = make_convo()
    assert not convo.needs_compaction()
    convo.add({"role": "user", "content": "x" * 3000})  # ~1000 tokens > 400 budget*0.5
    assert convo.needs_compaction()


def test_compact_collapses_old_tool_results_first():
    convo = make_convo()
    big = "line one of output\n" + ("y" * 2000)
    # Old tool result (both transport shapes), then enough recent messages to
    # push it past the protected window.
    convo.add({"role": "tool", "tool_call_id": "c1", "content": big})
    convo.add({"role": "user", "content": "<tool_response>" + big + "</tool_response>"})
    for i in range(Conversation.PROTECTED_RECENT):
        convo.add({"role": "user", "content": f"recent {i}"})
    stats = convo.compact()
    assert stats["after"] < stats["before"]
    collapsed = convo.messages()[1]
    assert collapsed["_compacted"] is True
    assert len(collapsed["content"]) < 200
    assert collapsed["tool_call_id"] == "c1"  # transport linkage preserved
    # Recent messages untouched
    assert convo.messages()[-1]["content"] == f"recent {Conversation.PROTECTED_RECENT - 1}"


def test_compact_summarizes_old_turns_when_still_over_budget():
    convo = make_convo(context_window=400, reserve_output=100)
    for i in range(10):
        convo.add({"role": "user", "content": f"turn {i} " + "z" * 400})
    called_with: list[list] = []

    def summarizer(messages):
        called_with.append(messages)
        return "the story so far"

    convo.compact(summarizer)
    assert called_with, "summarizer should be invoked when collapsing is not enough"
    contents = [m["content"] for m in convo.messages()]
    assert any("the story so far" in c for c in contents)
    assert contents[0] == "system prompt"  # system always survives
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_conversation.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/conversation.py
"""Message history with token accounting and two-stage compaction.

Stage 1: old tool results collapse to a one-line stub.
Stage 2: if still over budget, everything older than the protected recent
window is replaced by a model-written running summary.
The system prompt and the newest PROTECTED_RECENT messages always survive.
"""

from __future__ import annotations

import json
from typing import Any, Callable

Summarizer = Callable[[list[dict[str, Any]]], str]


def estimate_tokens(text: str) -> int:
    """Conservative chars/3 estimate (matches ModelConnector's heuristic)."""
    return max(1, (len(text or "") + 2) // 3)


def message_tokens(message: dict[str, Any]) -> int:
    content = str(message.get("content") or "")
    extra = json.dumps(message["tool_calls"]) if message.get("tool_calls") else ""
    return estimate_tokens(content) + (estimate_tokens(extra) if extra else 0) + 6


def _collapse_tool_content(content: str) -> str:
    first_line = (content or "").strip().splitlines()[0][:120] if content.strip() else ""
    return f"{first_line}\n[tool output collapsed: {len(content)} chars]"


class Conversation:
    PROTECTED_RECENT = 6

    def __init__(
        self,
        system_prompt: str,
        *,
        context_window: int = 8192,
        reserve_output: int = 3072,
        compact_threshold: float = 0.75,
    ) -> None:
        self.context_window = context_window
        self.reserve_output = reserve_output
        self.compact_threshold = compact_threshold
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}]

    def add(self, message: dict[str, Any]) -> None:
        self._messages.append(dict(message))

    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def payload_messages(self) -> list[dict[str, Any]]:
        """Messages ready for the API: private (underscore) keys stripped."""
        return [
            {key: value for key, value in message.items() if not key.startswith("_")}
            for message in self._messages
        ]

    @property
    def input_budget(self) -> int:
        return max(256, self.context_window - self.reserve_output)

    def total_tokens(self) -> int:
        return sum(message_tokens(message) for message in self._messages)

    def needs_compaction(self) -> bool:
        return self.total_tokens() > self.input_budget * self.compact_threshold

    def compact(self, summarizer: Summarizer | None = None) -> dict[str, int]:
        before = self.total_tokens()
        cutoff = max(1, len(self._messages) - self.PROTECTED_RECENT)

        for index in range(1, cutoff):
            message = self._messages[index]
            if message.get("_compacted"):
                continue
            content = str(message.get("content") or "")
            is_tool_result = (
                message.get("role") == "tool" or "<tool_response>" in content)
            if not is_tool_result:
                continue
            replacement: dict[str, Any] = {
                "role": message.get("role", "user"),
                "content": _collapse_tool_content(content),
                "_compacted": True,
            }
            if "tool_call_id" in message:
                replacement["tool_call_id"] = message["tool_call_id"]
            self._messages[index] = replacement

        if self.needs_compaction() and summarizer is not None and cutoff > 2:
            old = self._messages[1:cutoff]
            summary_text = summarizer(old)
            self._messages = [
                self._messages[0],
                {"role": "user",
                 "content": f"[Conversation summary — earlier turns compacted]\n{summary_text}",
                 "_compacted": True},
                *self._messages[cutoff:],
            ]

        return {"before": before, "after": self.total_tokens()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_conversation.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit** — `feat(core): conversation with token budget and compaction`

---

### Task 5: File tools (`tools/files.py`)

**Files:**
- Create: `nexcoder/agent/core/tools/files.py`
- Test: `tests/core/test_file_tools.py`

**Interfaces:**
- Consumes: `ToolContext`, `ToolSpec`, `ToolBelt` (Task 2); `AgentEvent` (Task 1); `should_skip_dir` from `nexcoder.agent.path_filters`.
- Produces: `register_file_tools(belt: ToolBelt) -> None` registering `read_file`, `edit_file`, `write_file`, `create_directory`, `move_path`, `list_directory`. Handlers are module functions `read_file(args, ctx)`, `edit_file(args, ctx)`, etc.
- Key results: `edit_file` → `{"success": True, "message", "replacements": int}` and emits `edit_applied` event with `{"path", "diff"}`; errors use `error_code` in `{"file_not_found", "not_found_in_file", "ambiguous_match", "no_change", "blocked", "tool_sensitive_file"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_file_tools.py
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext
from nexcoder.agent.core.tools.files import register_file_tools


def make(tmp_path):
    events: list[AgentEvent] = []
    belt = ToolBelt()
    register_file_tools(belt)
    ctx = ToolContext(project_root=tmp_path, emit=events.append, run_id="t")
    return belt, ctx, events


def test_read_file_with_offset_limit(tmp_path):
    (tmp_path / "a.txt").write_text("l1\nl2\nl3\nl4\n", encoding="utf-8")
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("read_file", {"path": "a.txt", "offset": 2, "limit": 2}, ctx)
    assert result["success"] and result["content"] == "l2\nl3"
    assert result["total_lines"] == 4
    full = belt.execute("read_file", {"path": "a.txt"}, ctx)
    assert full["content"] == "l1\nl2\nl3\nl4\n"


def test_read_file_not_found_and_escape(tmp_path):
    belt, ctx, _ = make(tmp_path)
    assert belt.execute("read_file", {"path": "nope.txt"}, ctx)["error_code"] == "file_not_found"
    assert belt.execute("read_file", {"path": "../x"}, ctx)["error_code"] == "blocked"


def test_edit_file_replaces_and_snapshots(tmp_path):
    (tmp_path / "m.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    belt, ctx, events = make(tmp_path)
    result = belt.execute("edit_file", {
        "path": "m.py", "old_string": "def old():", "new_string": "def new():"}, ctx)
    assert result["success"] and result["replacements"] == 1
    assert (tmp_path / "m.py").read_text(encoding="utf-8") == "def new():\n    return 1\n"
    assert "m.py" in ctx.mutated_files and ctx.checkpoint_id
    assert any(e.type == "edit_applied" for e in events)


def test_edit_file_error_codes(tmp_path):
    (tmp_path / "d.txt").write_text("aa bb aa", encoding="utf-8")
    belt, ctx, _ = make(tmp_path)
    assert belt.execute("edit_file", {"path": "d.txt", "old_string": "zz",
                        "new_string": "q"}, ctx)["error_code"] == "not_found_in_file"
    assert belt.execute("edit_file", {"path": "d.txt", "old_string": "aa",
                        "new_string": "q"}, ctx)["error_code"] == "ambiguous_match"
    assert belt.execute("edit_file", {"path": "d.txt", "old_string": "bb",
                        "new_string": "bb"}, ctx)["error_code"] == "no_change"
    ok = belt.execute("edit_file", {"path": "d.txt", "old_string": "aa",
                      "new_string": "q", "replace_all": True}, ctx)
    assert ok["success"] and ok["replacements"] == 2
    assert (tmp_path / "d.txt").read_text(encoding="utf-8") == "q bb q"


def test_edit_file_preserves_crlf(tmp_path):
    (tmp_path / "w.txt").write_bytes(b"one\r\ntwo\r\n")
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("edit_file", {"path": "w.txt", "old_string": "two",
                          "new_string": "2"}, ctx)
    assert result["success"]
    assert (tmp_path / "w.txt").read_bytes() == b"one\r\n2\r\n"


def test_write_file_creates_parents_and_snapshots(tmp_path):
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("write_file", {"path": "sub/new.txt", "content": "hello"}, ctx)
    assert result["success"]
    assert (tmp_path / "sub" / "new.txt").read_text(encoding="utf-8") == "hello"
    assert "sub/new.txt" in ctx.mutated_files


def test_write_file_sensitive_blocked(tmp_path):
    belt, ctx, _ = make(tmp_path)
    result = belt.execute("write_file", {"path": ".env", "content": "X=1"}, ctx)
    assert result["error_code"] == "tool_sensitive_file"


def test_move_and_mkdir_and_list(tmp_path):
    (tmp_path / "src.txt").write_text("s", encoding="utf-8")
    belt, ctx, _ = make(tmp_path)
    assert belt.execute("create_directory", {"path": "pkg"}, ctx)["success"]
    result = belt.execute("move_path", {"source": "src.txt", "destination": "pkg/dst.txt"}, ctx)
    assert result["success"]
    assert (tmp_path / "pkg" / "dst.txt").exists() and not (tmp_path / "src.txt").exists()
    listing = belt.execute("list_directory", {"path": "."}, ctx)
    names = [e["name"] for e in listing["entries"]]
    assert "pkg" in names
    assert belt.execute("move_path", {"source": ".git/x", "destination": "y"}, ctx)["error_code"] == "blocked"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_file_tools.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/tools/files.py
"""File tools: read, precise search/replace edit, write, mkdir, move, ls.

Edits write straight to disk (Cursor-style autonomy); every mutation is
snapshotted into the run checkpoint first so the UI can revert any file
or the whole run.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.path_filters import should_skip_dir

MAX_READ_BYTES = 1024 * 1024
PROTECTED_PARTS = {".git", ".nexcoder", "node_modules", "venv", ".venv", "__pycache__"}


def _relative(ctx: ToolContext, path: Path) -> str:
    return path.relative_to(ctx.project_root).as_posix()


def _is_protected(relative_path: str) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in Path(relative_path).parts)


def _read_text(path: Path) -> str:
    # newline="" preserves CRLF so search/replace round-trips Windows files.
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(content)


def read_file(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    path = ctx.resolve(str(args.get("path") or ""))
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    if not path.is_file():
        return {"success": False, "error_code": "file_not_found",
                "error": f"File not found: {args.get('path')}"}
    if path.stat().st_size > MAX_READ_BYTES:
        return {"success": False, "error_code": "file_too_large",
                "error": "File exceeds 1MB read limit"}
    content = _read_text(path)
    lines = content.splitlines()
    total = len(lines)
    offset = int(args.get("offset") or 0)
    limit = int(args.get("limit") or 0)
    if offset or limit:
        start = max(0, offset - 1) if offset else 0
        end = start + limit if limit else total
        content = "\n".join(lines[start:end])
    return {"success": True, "content": content, "total_lines": total,
            "message": f"Read {args.get('path')} ({total} lines)"}


def edit_file(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    target = str(args.get("path") or "")
    old = args.get("old_string")
    new = args.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str) or not old:
        return {"success": False, "error_code": "invalid_args",
                "error": "edit_file requires path, old_string, new_string"}
    if old == new:
        return {"success": False, "error_code": "no_change",
                "error": "old_string and new_string are identical"}
    path = ctx.resolve(target)
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    relative = _relative(ctx, path)
    if _is_protected(relative):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project path"}
    if ctx.safety.is_sensitive_file(relative):
        return {"success": False, "error_code": "tool_sensitive_file",
                "error": "Sensitive file edit blocked"}
    if not path.is_file():
        return {"success": False, "error_code": "file_not_found",
                "error": f"File not found: {target}"}
    content = _read_text(path)
    count = content.count(old)
    if count == 0:
        return {"success": False, "error_code": "not_found_in_file",
                "error": "old_string not found in file. Re-read the file and "
                         "copy the exact text, including whitespace."}
    replace_all = bool(args.get("replace_all"))
    if count > 1 and not replace_all:
        return {"success": False, "error_code": "ambiguous_match",
                "error": f"old_string matches {count} times. Add surrounding "
                         "context to make it unique, or set replace_all: true."}
    updated = content.replace(old, new) if replace_all else content.replace(old, new, 1)
    ctx.snapshot_before_mutation(relative)
    _write_text(path, updated)
    diff = "\n".join(difflib.unified_diff(
        content.splitlines(), updated.splitlines(),
        fromfile=f"a/{relative}", tofile=f"b/{relative}", lineterm=""))
    replacements = count if replace_all else 1
    ctx.emit(AgentEvent("edit_applied", {
        "path": relative, "diff": diff[:20000], "replacements": replacements}))
    return {"success": True, "replacements": replacements,
            "message": f"Edited {relative} ({replacements} replacement(s))"}


def write_file(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    target = str(args.get("path") or "")
    content = args.get("content")
    if not isinstance(content, str):
        return {"success": False, "error_code": "invalid_args",
                "error": "Missing file content"}
    path = ctx.resolve(target)
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    relative = _relative(ctx, path)
    if _is_protected(relative):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project path"}
    if ctx.safety.is_sensitive_file(relative):
        return {"success": False, "error_code": "tool_sensitive_file",
                "error": "Sensitive file write blocked"}
    existed = path.is_file()
    ctx.snapshot_before_mutation(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(path, content)
    ctx.emit(AgentEvent("edit_applied", {
        "path": relative, "created": not existed,
        "diff": f"[full file write: {len(content)} chars]"}))
    action = "Updated" if existed else "Created"
    return {"success": True, "message": f"{action} {relative}"}


def create_directory(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    path = ctx.resolve(str(args.get("path") or ""))
    if path is None or path == ctx.project_root:
        return {"success": False, "error_code": "blocked",
                "error": "Directory must be inside the active project"}
    relative = _relative(ctx, path)
    if _is_protected(relative):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project path"}
    if path.exists() and not path.is_dir():
        return {"success": False, "error_code": "path_conflict",
                "error": f"A file already exists at {relative}"}
    path.mkdir(parents=True, exist_ok=True)
    return {"success": True, "message": f"Directory ready: {relative}"}


def move_path(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    source = ctx.resolve(str(args.get("source") or ""))
    destination = ctx.resolve(str(args.get("destination") or ""))
    if source is None or destination is None or source == ctx.project_root:
        return {"success": False, "error_code": "blocked",
                "error": "Move must stay inside the active project"}
    source_rel = _relative(ctx, source)
    dest_rel = _relative(ctx, destination)
    if _is_protected(source_rel) or _is_protected(dest_rel):
        return {"success": False, "error_code": "blocked",
                "error": "Protected project paths cannot be moved"}
    if ctx.safety.is_sensitive_file(source_rel) or ctx.safety.is_sensitive_file(dest_rel):
        return {"success": False, "error_code": "tool_sensitive_file",
                "error": "Sensitive file move blocked"}
    if not source.exists():
        return {"success": False, "error_code": "file_not_found",
                "error": f"Source not found: {source_rel}"}
    if destination.exists():
        return {"success": False, "error_code": "path_conflict",
                "error": f"Destination already exists: {dest_rel}"}
    if source.is_file():
        ctx.snapshot_before_mutation(source_rel)
        ctx.snapshot_before_mutation(dest_rel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination) if source.is_file() else source.rename(destination)
    return {"success": True, "message": f"Moved {source_rel} -> {dest_rel}"}


def list_directory(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    path = ctx.resolve(str(args.get("path") or "."))
    if path is None:
        return {"success": False, "error_code": "blocked",
                "error": "Path is outside the active project"}
    if not path.is_dir():
        return {"success": False, "error_code": "directory_not_found",
                "error": "Directory not found"}
    entries = []
    for child in sorted(path.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir() and should_skip_dir(child.name, skip_hidden=False):
            continue
        entries.append({"name": child.name,
                        "type": "directory" if child.is_dir() else "file"})
        if len(entries) >= 200:
            break
    return {"success": True, "entries": entries,
            "message": f"Listed {len(entries)} item(s)"}


_PATH_PARAM = {"type": "object",
               "properties": {"path": {"type": "string", "description": "Project-relative path"}},
               "required": ["path"]}


def register_file_tools(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="read_file",
        description="Read a file. Optional offset (1-based line) and limit narrow the range.",
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer"},
            "limit": {"type": "integer"}}, "required": ["path"]},
        handler=read_file))
    belt.register(ToolSpec(
        name="edit_file",
        description=("Replace an exact string in a file. old_string must match the file "
                     "text exactly (including whitespace) and exactly once, unless "
                     "replace_all is true. Preferred over write_file for existing files."),
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean"}},
            "required": ["path", "old_string", "new_string"]},
        handler=edit_file, mutating=True))
    belt.register(ToolSpec(
        name="write_file",
        description="Create a new file or fully overwrite an existing one.",
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"}}, "required": ["path", "content"]},
        handler=write_file, mutating=True))
    belt.register(ToolSpec(
        name="create_directory", description="Create a directory (parents included).",
        parameters=_PATH_PARAM, handler=create_directory, mutating=True))
    belt.register(ToolSpec(
        name="move_path", description="Move or rename a file or directory.",
        parameters={"type": "object", "properties": {
            "source": {"type": "string"}, "destination": {"type": "string"}},
            "required": ["source", "destination"]},
        handler=move_path, mutating=True))
    belt.register(ToolSpec(
        name="list_directory", description="List directory entries.",
        parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=list_directory))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_file_tools.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit** — `feat(core): direct-write file tools with checkpoint snapshots`

---

### Task 6: Search tools (`tools/search.py`)

**Files:**
- Create: `nexcoder/agent/core/tools/search.py`
- Test: `tests/core/test_search_tools.py`

**Interfaces:**
- Consumes: Task 2 base types; `has_skipped_part` from `nexcoder.agent.path_filters`.
- Produces: `register_search_tools(belt) -> None` registering `glob` and `grep`.
  - `glob(args={"pattern", "path"?}) -> {"success", "files": [str], "message"}` — recency-sorted, cap 100.
  - `grep(args={"pattern", "path"?, "glob"?, "max_results"?}) -> {"success", "results": [{"file", "line", "content"}], "message"}` — regex, cap default 50.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_search_tools.py
import os
import time

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext
from nexcoder.agent.core.tools.search import register_search_tools


def make(tmp_path):
    belt = ToolBelt()
    register_search_tools(belt)
    return belt, ToolContext(project_root=tmp_path, emit=lambda _e: None, run_id="t")


def test_glob_matches_and_sorts_by_recency(tmp_path):
    (tmp_path / "old.py").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "new.py").write_text("y", encoding="utf-8")
    (tmp_path / "readme.md").write_text("z", encoding="utf-8")
    past = time.time() - 1000
    os.utime(tmp_path / "old.py", (past, past))
    belt, ctx = make(tmp_path)
    result = belt.execute("glob", {"pattern": "**/*.py"}, ctx)
    assert result["success"]
    assert result["files"] == ["sub/new.py", "old.py"]


def test_glob_skips_filtered_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.py").write_text("d", encoding="utf-8")
    (tmp_path / "app.py").write_text("a", encoding="utf-8")
    belt, ctx = make(tmp_path)
    assert belt.execute("glob", {"pattern": "**/*.py"}, ctx)["files"] == ["app.py"]


def test_grep_regex_with_glob_filter(tmp_path):
    (tmp_path / "a.py").write_text("def alpha():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.ts").write_text("function alpha() {}\n", encoding="utf-8")
    belt, ctx = make(tmp_path)
    result = belt.execute("grep", {"pattern": r"def \w+", "glob": "*.py"}, ctx)
    assert result["success"]
    assert result["results"] == [{"file": "a.py", "line": 1, "content": "def alpha():"}]


def test_grep_invalid_regex(tmp_path):
    belt, ctx = make(tmp_path)
    assert belt.execute("grep", {"pattern": "("}, ctx)["error_code"] == "invalid_args"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_search_tools.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/tools/search.py
"""glob + grep tools: how the agent finds files fast in large projects."""

from __future__ import annotations

import fnmatch
import re
from typing import Any

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.path_filters import has_skipped_part

TEXT_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".md",
                   ".json", ".toml", ".txt", ".css", ".html", ".yaml", ".yml"}
GLOB_CAP = 100
GREP_DEFAULT_CAP = 50


def glob_tool(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return {"success": False, "error_code": "invalid_args", "error": "Missing pattern"}
    root = ctx.resolve(str(args.get("path") or "."))
    if root is None or not root.is_dir():
        return {"success": False, "error_code": "blocked",
                "error": "Search path is outside the project or missing"}
    matches: list[tuple[float, str]] = []
    for path in root.rglob("*"):
        relative_parts = path.relative_to(ctx.project_root).parts
        if has_skipped_part(relative_parts):
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern):
            try:
                matches.append((path.stat().st_mtime,
                                path.relative_to(ctx.project_root).as_posix()))
            except OSError:
                continue
    matches.sort(key=lambda item: item[0], reverse=True)
    files = [name for _, name in matches[:GLOB_CAP]]
    return {"success": True, "files": files,
            "message": f"Found {len(files)} file(s) for {pattern}"}


def grep_tool(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return {"success": False, "error_code": "invalid_args", "error": "Missing pattern"}
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return {"success": False, "error_code": "invalid_args",
                "error": f"Invalid regex: {exc}"}
    root = ctx.resolve(str(args.get("path") or "."))
    if root is None or not root.is_dir():
        return {"success": False, "error_code": "blocked",
                "error": "Search path is outside the project or missing"}
    name_glob = str(args.get("glob") or "")
    cap = int(args.get("max_results") or GREP_DEFAULT_CAP)
    results: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if has_skipped_part(path.relative_to(ctx.project_root).parts):
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if name_glob and not fnmatch.fnmatch(path.name, name_glob):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                results.append({
                    "file": path.relative_to(ctx.project_root).as_posix(),
                    "line": line_no, "content": line.strip()[:240]})
                if len(results) >= cap:
                    return {"success": True, "results": results,
                            "message": f"Found {len(results)}+ match(es) (capped)"}
    return {"success": True, "results": results,
            "message": f"Found {len(results)} match(es)"}


def register_search_tools(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="glob",
        description="Find files by glob pattern (e.g. **/*.py). Newest first.",
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"]},
        handler=glob_tool))
    belt.register(ToolSpec(
        name="grep",
        description="Regex search file contents. Optional glob filters filenames.",
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string"},
            "glob": {"type": "string"}, "max_results": {"type": "integer"}},
            "required": ["pattern"]},
        handler=grep_tool))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_search_tools.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit** — `feat(core): glob and grep search tools`

---

### Task 7: Shell tool + permission gates (`tools/shell.py`, `permissions.py`)

**Files:**
- Create: `nexcoder/agent/core/permissions.py`, `nexcoder/agent/core/tools/shell.py`
- Test: `tests/core/test_permissions.py`, `tests/core/test_shell_tool.py`

**Interfaces:**
- Consumes: Task 2 base (`PermissionGate`, `ALLOW`, `ALLOW_ALWAYS`, `DENY`); `SafetyChecker`.
- Produces:
  - `AllowlistGate(inner: PermissionGate, project_root)` — persists `allow_always` commands to `.nexcoder/permissions.json` (shape `{"allowed_commands": ["npm test", ...]}`); exact-string match allows without asking.
  - `FullAutoGate()` — allows everything except commands matching `RISKY_PATTERNS` (`git push`, `rm -r`/`del /s`, `npm publish`, `pip install`-free? no — exactly: `r"git\s+push"`, `r"rm\s+-r"`, `r"del\s+/s"`, `r"rd\s+/s"`, `r"npm\s+publish"`, `r"git\s+reset\s+--hard"`), which return DENY (caller may re-prompt).
  - `register_shell_tool(belt) -> None` registering `run_command(args={"command", "timeout"?})`. Streams output lines via `command_output` events; blocklist always wins; permission flow emits `permission_request` / `permission_resolved` events.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_permissions.py
import json

from nexcoder.agent.core.permissions import AllowlistGate, FullAutoGate
from nexcoder.agent.core.tools.base import ALLOW, ALLOW_ALWAYS, DENY


class ScriptedGate:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def request(self, *, tool, detail):
        self.calls.append(detail)
        return self.answer


def test_allowlist_skips_inner_when_listed(tmp_path):
    (tmp_path / ".nexcoder").mkdir()
    (tmp_path / ".nexcoder" / "permissions.json").write_text(
        json.dumps({"allowed_commands": ["npm test"]}), encoding="utf-8")
    inner = ScriptedGate(DENY)
    gate = AllowlistGate(inner, tmp_path)
    assert gate.request(tool="run_command", detail="npm test") == ALLOW
    assert inner.calls == []


def test_allow_always_persists(tmp_path):
    inner = ScriptedGate(ALLOW_ALWAYS)
    gate = AllowlistGate(inner, tmp_path)
    assert gate.request(tool="run_command", detail="pytest -q") == ALLOW
    saved = json.loads((tmp_path / ".nexcoder" / "permissions.json").read_text(encoding="utf-8"))
    assert "pytest -q" in saved["allowed_commands"]
    # Second time: no inner prompt
    inner2 = ScriptedGate(DENY)
    gate2 = AllowlistGate(inner2, tmp_path)
    assert gate2.request(tool="run_command", detail="pytest -q") == ALLOW
    assert inner2.calls == []


def test_full_auto_gate_blocks_risky():
    gate = FullAutoGate()
    assert gate.request(tool="run_command", detail="npm test") == ALLOW
    assert gate.request(tool="run_command", detail="git push origin main") == DENY
    assert gate.request(tool="run_command", detail="rm -r build") == DENY
```

```python
# tests/core/test_shell_tool.py
import sys

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import DENY, ToolBelt, ToolContext
from nexcoder.agent.core.tools.shell import register_shell_tool


class DenyGate:
    def request(self, *, tool, detail):
        return DENY


def make(tmp_path, gate=None):
    events: list[AgentEvent] = []
    belt = ToolBelt()
    register_shell_tool(belt)
    ctx = ToolContext(project_root=tmp_path, emit=events.append,
                      permission_gate=gate, run_id="t")
    return belt, ctx, events


def test_run_command_streams_and_reports_exit(tmp_path):
    belt, ctx, events = make(tmp_path)
    code = "import sys; print('out1'); print('err1', file=sys.stderr)"
    result = belt.execute("run_command", {"command": f'"{sys.executable}" -c "{code}"'}, ctx)
    assert result["success"] and result["exit_code"] == 0
    assert "out1" in result["stdout"] and "err1" in result["stderr"]
    assert any(e.type == "command_output" for e in events)


def test_run_command_denied_by_gate(tmp_path):
    belt, ctx, events = make(tmp_path, DenyGate())
    result = belt.execute("run_command", {"command": "echo hi"}, ctx)
    assert result["error_code"] == "permission_denied"
    types = [e.type for e in events]
    assert "permission_request" in types and "permission_resolved" in types


def test_run_command_blocklist_always_wins(tmp_path):
    belt, ctx, _ = make(tmp_path)  # AllowAllGate default
    result = belt.execute("run_command", {"command": "rm -rf /"}, ctx)
    assert result["error_code"] == "tool_command_blocked"


def test_run_command_timeout(tmp_path):
    belt, ctx, _ = make(tmp_path)
    code = "import time; time.sleep(30)"
    result = belt.execute("run_command",
                          {"command": f'"{sys.executable}" -c "{code}"', "timeout": 2}, ctx)
    assert result["error_code"] == "tool_timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_permissions.py tests\core\test_shell_tool.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/permissions.py
"""Permission gates: project allowlist persistence and full-auto policy."""

from __future__ import annotations

import json
from pathlib import Path
import re

from nexcoder.agent.core.tools.base import ALLOW, ALLOW_ALWAYS, DENY, PermissionGate

RISKY_PATTERNS = [
    r"git\s+push", r"git\s+reset\s+--hard", r"rm\s+-r", r"del\s+/s",
    r"rd\s+/s", r"npm\s+publish",
]


class AllowlistGate:
    """Wraps another gate with a persisted per-project command allowlist."""

    def __init__(self, inner: PermissionGate, project_root: str | Path) -> None:
        self.inner = inner
        self._path = Path(project_root) / ".nexcoder" / "permissions.json"

    def _load(self) -> list[str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [str(item) for item in data.get("allowed_commands", [])]
        except (OSError, json.JSONDecodeError, ValueError):
            return []

    def _save(self, commands: list[str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"allowed_commands": sorted(set(commands))}, indent=2),
            encoding="utf-8")

    def request(self, *, tool: str, detail: str) -> str:
        command = detail.strip()
        allowed = self._load()
        if command in allowed:
            return ALLOW
        decision = self.inner.request(tool=tool, detail=detail)
        if decision == ALLOW_ALWAYS:
            self._save(allowed + [command])
            return ALLOW
        return decision


class FullAutoGate:
    """YOLO mode: allow everything except risky commands (those get denied
    so the caller surfaces them; the hard blocklist lives in the tool)."""

    def request(self, *, tool: str, detail: str) -> str:
        lowered = detail.lower()
        for pattern in RISKY_PATTERNS:
            if re.search(pattern, lowered):
                return DENY
        return ALLOW
```

```python
# nexcoder/agent/core/tools/shell.py
"""run_command: permission-gated, blocklist-checked, streaming shell tool."""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any
import uuid

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ALLOW, ToolBelt, ToolContext, ToolSpec

DEFAULT_TIMEOUT = 180.0
TAIL_CHARS = 8000


def run_command(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    command = str(args.get("command") or "").strip()
    if not command:
        return {"success": False, "error_code": "invalid_args", "error": "Missing command"}
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_permissions.py tests\core\test_shell_tool.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit** — `feat(core): permission-gated streaming shell tool and gates`

---

### Task 8: Todo + skill tools, belt factory (`tools/todo.py`, `tools/skill.py`, `belt_factory.py`)

**Files:**
- Create: `nexcoder/agent/core/tools/todo.py`, `nexcoder/agent/core/tools/skill.py`, `nexcoder/agent/core/belt_factory.py`
- Test: `tests/core/test_todo_and_factory.py`

**Interfaces:**
- Consumes: Tasks 2, 5, 6, 7 registrars; `get_skill_body` from `nexcoder.agent.skills_registry`.
- Produces:
  - `todo_write(args={"todos": [{"content": str, "status": "pending"|"in_progress"|"completed"}]})` — replaces `ctx.todos`, emits `todo_updated` with the full list.
  - `load_skill(args={"id"})` — wraps `get_skill_body`, body capped 12000 chars.
  - `build_default_belt() -> ToolBelt` — registers all tools: files + search + shell + todo + skill.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_todo_and_factory.py
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolContext


def make_ctx(tmp_path, events):
    return ToolContext(project_root=tmp_path, emit=events.append, run_id="t")


def test_default_belt_has_all_tools():
    belt = build_default_belt()
    assert set(belt.names) == {
        "read_file", "edit_file", "write_file", "create_directory", "move_path",
        "list_directory", "glob", "grep", "run_command", "todo_write", "load_skill"}


def test_todo_write_updates_context_and_emits(tmp_path):
    belt = build_default_belt()
    events: list[AgentEvent] = []
    ctx = make_ctx(tmp_path, events)
    result = belt.execute("todo_write", {"todos": [
        {"content": "plan", "status": "completed"},
        {"content": "build", "status": "in_progress"}]}, ctx)
    assert result["success"]
    assert [t["status"] for t in ctx.todos] == ["completed", "in_progress"]
    updated = [e for e in events if e.type == "todo_updated"]
    assert updated and len(updated[0].payload["todos"]) == 2


def test_todo_write_rejects_bad_status(tmp_path):
    belt = build_default_belt()
    ctx = make_ctx(tmp_path, [])
    result = belt.execute("todo_write", {"todos": [{"content": "x", "status": "done"}]}, ctx)
    assert result["error_code"] == "invalid_args"


def test_load_skill_unknown(tmp_path):
    belt = build_default_belt()
    ctx = make_ctx(tmp_path, [])
    assert belt.execute("load_skill", {"id": "no-such-skill"}, ctx)["error_code"] == "skill_not_found"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_todo_and_factory.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/tools/todo.py
"""todo_write: the agent's visible task list."""

from __future__ import annotations

from typing import Any

from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec

VALID_STATUSES = {"pending", "in_progress", "completed"}


def todo_write(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    raw = args.get("todos")
    if not isinstance(raw, list) or not raw:
        return {"success": False, "error_code": "invalid_args",
                "error": "todos must be a non-empty array"}
    todos: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        content = str((item or {}).get("content") or "").strip()
        status = str((item or {}).get("status") or "pending")
        if not content or status not in VALID_STATUSES:
            return {"success": False, "error_code": "invalid_args",
                    "error": f"todos[{index}] needs content and status in "
                             f"{sorted(VALID_STATUSES)}"}
        todos.append({"id": index + 1, "content": content, "status": status})
    ctx.todos = todos
    ctx.emit(AgentEvent("todo_updated", {"todos": todos}))
    done = sum(1 for t in todos if t["status"] == "completed")
    return {"success": True, "message": f"Todo list updated ({done}/{len(todos)} done)"}


def register_todo_tool(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="todo_write",
        description=("Replace your task list. Call early on multi-step tasks and "
                     "keep statuses current as you work."),
        parameters={"type": "object", "properties": {
            "todos": {"type": "array", "items": {"type": "object", "properties": {
                "content": {"type": "string"},
                "status": {"type": "string",
                           "enum": ["pending", "in_progress", "completed"]}},
                "required": ["content", "status"]}}},
            "required": ["todos"]},
        handler=todo_write))
```

```python
# nexcoder/agent/core/tools/skill.py
"""load_skill: read a SKILL.md body from the skills registry."""

from __future__ import annotations

from typing import Any

from nexcoder.agent.core.tools.base import ToolBelt, ToolContext, ToolSpec
from nexcoder.agent.skills_registry import get_skill_body

MAX_BODY = 12000


def load_skill(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    skill_id = str(args.get("id") or "").strip()
    record = get_skill_body(skill_id) if skill_id else None
    if record is None:
        return {"success": False, "error_code": "skill_not_found",
                "error": f"Unknown skill: {skill_id}"}
    return {"success": True, "skill": {**record, "body": (record.get("body") or "")[:MAX_BODY]},
            "message": "Skill loaded"}


def register_skill_tool(belt: ToolBelt) -> None:
    belt.register(ToolSpec(
        name="load_skill", description="Load a skill guide by id.",
        parameters={"type": "object", "properties": {"id": {"type": "string"}},
                    "required": ["id"]},
        handler=load_skill))
```

```python
# nexcoder/agent/core/belt_factory.py
"""Assemble the default agent tool belt."""

from __future__ import annotations

from nexcoder.agent.core.tools.base import ToolBelt
from nexcoder.agent.core.tools.files import register_file_tools
from nexcoder.agent.core.tools.search import register_search_tools
from nexcoder.agent.core.tools.shell import register_shell_tool
from nexcoder.agent.core.tools.skill import register_skill_tool
from nexcoder.agent.core.tools.todo import register_todo_tool


def build_default_belt() -> ToolBelt:
    belt = ToolBelt()
    register_file_tools(belt)
    register_search_tools(belt)
    register_shell_tool(belt)
    register_todo_tool(belt)
    register_skill_tool(belt)
    return belt
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_todo_and_factory.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit** — `feat(core): todo and skill tools, default belt factory`

---

### Task 9: The AgentLoop (`loop.py`)

**Files:**
- Create: `nexcoder/agent/core/loop.py`
- Test: `tests/core/test_loop.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8; `ToolGuardrailController`, `ToolGuardrailConfig` (existing); `AgentTrajectoryRecorder` (existing).
- Produces:
  - `ModelClient` protocol: `complete(messages: list[dict], *, extras: dict, on_delta: Callable[[str], None] | None) -> dict` returning an OpenAI-style assistant message dict.
  - `AgentLoop(project_root, model, adapter, belt, system_prompt, *, emit=None, permission_gate=None, max_turns=50, context_window=8192, reserve_output=3072, extra_system="", trajectory_mode="agent")`.
  - `AgentLoop.run(task: str) -> dict` — `{"success", "status": "completed"|"max_turns"|"stalled"|"error", "final_text", "run_id", "checkpoint_id", "mutated_files": [str], "todos": [dict], "turns": int}`.
  - `AGENT_SYSTEM_PROMPT` constant (default v2 agent prompt).
  - `MAX_GUARDRAIL_BLOCKS = 6` (run stops with status "stalled" after this many blocked calls).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_loop.py
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.transport import XmlAdapter


class FakeModel:
    """Scripted ModelClient: returns queued assistant messages in order."""

    def __init__(self, messages):
        self.queue = list(messages)
        self.received: list[list[dict]] = []

    def complete(self, messages, *, extras, on_delta=None):
        self.received.append(messages)
        message = self.queue.pop(0) if self.queue else {"role": "assistant", "content": "done"}
        if on_delta and message.get("content"):
            on_delta(message["content"])
        return message


def xml_call(tool, args_json):
    return {"role": "assistant",
            "content": f'<tool_call name="{tool}">{args_json}</tool_call>'}


def make_loop(tmp_path, model, **kwargs):
    events: list[AgentEvent] = []
    loop = AgentLoop(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="You are a test agent.",
        emit=events.append, **kwargs)
    return loop, events


def test_loop_executes_tools_then_finishes(tmp_path):
    (tmp_path / "hello.txt").write_text("world", encoding="utf-8")
    model = FakeModel([
        xml_call("read_file", '{"path": "hello.txt"}'),
        {"role": "assistant", "content": "The file says world."},
    ])
    loop, events = make_loop(tmp_path, model)
    result = loop.run("what does hello.txt say?")
    assert result["success"] and result["status"] == "completed"
    assert result["final_text"] == "The file says world."
    assert result["turns"] == 2
    types = [e.type for e in events]
    assert "run_started" in types and "tool_started" in types
    assert "tool_result" in types and "run_completed" in types
    # Tool result was fed back to the model as a tool_response user message
    second_request = model.received[1]
    assert any("<tool_response>" in str(m.get("content")) for m in second_request)


def test_loop_edit_creates_checkpoint_and_reports_mutations(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    model = FakeModel([
        xml_call("edit_file", '{"path": "a.py", "old_string": "x = 1", "new_string": "x = 2"}'),
        {"role": "assistant", "content": "Changed x to 2."},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("set x to 2")
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = 2\n"
    assert result["mutated_files"] == ["a.py"]
    assert result["checkpoint_id"]


def test_loop_feeds_parse_errors_back(tmp_path):
    model = FakeModel([
        {"role": "assistant", "content": '<tool_call name="read_file">{broken</tool_call>'},
        {"role": "assistant", "content": "ok, giving up"},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("do something")
    assert result["status"] == "completed"
    correction = model.received[1]
    assert any("valid JSON" in str(m.get("content")) for m in correction)


def test_loop_duplicate_calls_blocked_then_stalls(tmp_path):
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    same = xml_call("read_file", '{"path": "f.txt"}')
    model = FakeModel([same] * 12)
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("loop forever")
    assert result["status"] == "stalled"
    assert result["success"] is False


def test_loop_max_turns(tmp_path):
    # Alternating distinct reads so guardrails never block.
    calls = [xml_call("read_file", f'{{"path": "no{i}.txt"}}') for i in range(20)]
    model = FakeModel(calls)
    loop, _ = make_loop(tmp_path, model, max_turns=3)
    result = loop.run("never finish")
    assert result["status"] == "max_turns" and result["turns"] == 3


def test_loop_todo_state_in_result(tmp_path):
    model = FakeModel([
        xml_call("todo_write",
                 '{"todos": [{"content": "step 1", "status": "in_progress"}]}'),
        {"role": "assistant", "content": "planned"},
    ])
    loop, _ = make_loop(tmp_path, model)
    result = loop.run("plan it")
    assert result["todos"][0]["content"] == "step 1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_loop.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/loop.py
"""AgentLoop — the canonical agentic loop.

messages -> model -> tool calls -> results -> repeat, until the model
answers with no tool calls, guardrails stall it, or the turn cap hits.
Mode-specific behaviour lives in the system prompt and belt, never here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Protocol
import uuid

from nexcoder.agent.core.conversation import Conversation
from nexcoder.agent.core.events import AgentEvent, EventCallback
from nexcoder.agent.core.tools.base import PermissionGate, ToolBelt, ToolContext
from nexcoder.agent.core.transport import ToolCallAdapter
from nexcoder.agent.tool_guardrails import ToolGuardrailConfig, ToolGuardrailController
from nexcoder.agent.trajectory import AgentTrajectoryRecorder

logger = logging.getLogger(__name__)

MAX_GUARDRAIL_BLOCKS = 6

AGENT_SYSTEM_PROMPT = """You are NexCoder, an autonomous coding agent working \
inside the user's project.

How you work:
1. On non-trivial tasks, call todo_write first with your plan, and keep \
statuses current as you complete each step.
2. Inspect before you change: use glob/grep/read_file to find and understand \
the relevant code. Never invent file contents.
3. Edit precisely: prefer edit_file with an exact unique old_string. Use \
write_file only for new files or full rewrites.
4. Verify your work: after making changes, run a verification command \
(tests, build, or a quick check) with run_command. If it fails, read the \
error, fix the code, and verify again before finishing.
5. When the task is fully complete and verified, reply with a short plain-text \
summary of what changed and how it was verified. No tool calls in that final \
message."""


class ModelClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        extras: dict[str, Any],
        on_delta: Callable[[str], None] | None = None,
    ) -> dict[str, Any]: ...


class AgentLoop:
    def __init__(
        self,
        *,
        project_root: str | Path,
        model: ModelClient,
        adapter: ToolCallAdapter,
        belt: ToolBelt,
        system_prompt: str,
        emit: EventCallback | None = None,
        permission_gate: PermissionGate | None = None,
        max_turns: int = 50,
        context_window: int = 8192,
        reserve_output: int = 3072,
        extra_system: str = "",
        trajectory_mode: str = "agent",
        guardrail_config: ToolGuardrailConfig | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.model = model
        self.adapter = adapter
        self.belt = belt
        self.system_prompt = system_prompt
        self.emit: EventCallback = emit or (lambda _event: None)
        self.permission_gate = permission_gate
        self.max_turns = max_turns
        self.context_window = context_window
        self.reserve_output = reserve_output
        self.extra_system = extra_system
        self.trajectory_mode = trajectory_mode
        self.guardrail_config = guardrail_config

    def _summarize(self, old_messages: list[dict[str, Any]]) -> str:
        transcript = "\n".join(
            f"{m.get('role')}: {str(m.get('content'))[:400]}" for m in old_messages)
        prompt = [
            {"role": "system", "content":
             "Summarize this agent transcript in under 200 words. Keep: the "
             "task, files touched, decisions made, and current state."},
            {"role": "user", "content": transcript[:12000]},
        ]
        try:
            message = self.model.complete(prompt, extras={}, on_delta=None)
            return str(message.get("content") or "").strip() or "(no summary)"
        except Exception as exc:
            logger.warning("Compaction summarizer failed: %s", exc)
            return "(summary unavailable)"

    def run(self, task: str) -> dict[str, Any]:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        ctx = ToolContext(
            project_root=self.project_root, emit=self.emit,
            permission_gate=self.permission_gate, run_id=run_id)
        schemas = self.belt.schemas()
        system = self.system_prompt
        if self.extra_system:
            system += "\n\n" + self.extra_system
        system += self.adapter.system_prompt_suffix(schemas)
        conversation = Conversation(
            system, context_window=self.context_window,
            reserve_output=self.reserve_output)
        conversation.add({"role": "user", "content": task})
        guardrails = ToolGuardrailController(self.guardrail_config)
        trajectory = AgentTrajectoryRecorder(
            self.project_root, task=task, mode=self.trajectory_mode)
        extras = self.adapter.request_extras(schemas)

        self.emit(AgentEvent("run_started", {"run_id": run_id, "task": task}))
        status = "max_turns"
        final_text = ""
        blocked_total = 0
        turns_used = 0

        try:
            for turn in range(1, self.max_turns + 1):
                turns_used = turn
                self.emit(AgentEvent("turn_started", {"turn": turn, "run_id": run_id}))

                if conversation.needs_compaction():
                    stats = conversation.compact(self._summarize)
                    self.emit(AgentEvent("compaction", stats))

                message = self.model.complete(
                    conversation.payload_messages(), extras=extras,
                    on_delta=lambda delta: self.emit(
                        AgentEvent("text_delta", {"text": delta, "turn": turn})))
                conversation.add(message)
                turn_data = self.adapter.parse_assistant_message(message)

                if turn_data.parse_error:
                    trajectory.record("parse_error", {"error": turn_data.parse_error})
                    conversation.add({"role": "user", "content":
                                      f"Tool call error: {turn_data.parse_error}. "
                                      "Re-emit the call with valid JSON arguments."})
                    continue

                if not turn_data.tool_calls:
                    final_text = turn_data.text
                    status = "completed"
                    break

                results: list[dict[str, Any]] = []
                for call in turn_data.tool_calls:
                    decision = guardrails.before_call(call.name, call.args)
                    if not decision.allows_execution:
                        blocked_total += 1
                        result: dict[str, Any] = {
                            "success": False, "error_code": decision.code,
                            "error": decision.message}
                    else:
                        self.emit(AgentEvent("tool_started", {
                            "tool": call.name, "args": call.args, "turn": turn}))
                        result = self.belt.execute(call.name, call.args, ctx)
                        after = guardrails.after_call(call.name, call.args, result)
                        if after.action == "block":
                            blocked_total += 1
                            result = {**result, "guardrail": after.message}
                        elif after.action == "warn":
                            result = {**result, "guardrail": after.message}
                    self.emit(AgentEvent("tool_result", {
                        "tool": call.name, "success": bool(result.get("success")),
                        "summary": str(result.get("message") or result.get("error") or "")[:200],
                        "turn": turn}))
                    trajectory.record("tool_call", {
                        "tool": call.name, "args": call.args, "result": result})
                    results.append(result)

                for result_message in self.adapter.tool_result_messages(
                        list(turn_data.tool_calls), results):
                    conversation.add(result_message)

                if blocked_total >= MAX_GUARDRAIL_BLOCKS:
                    status = "stalled"
                    final_text = ("Run stopped: the agent repeated unproductive "
                                  "tool calls too many times.")
                    break
        except Exception as exc:
            logger.exception("Agent run failed")
            status = "error"
            final_text = f"Run failed: {exc}"
            self.emit(AgentEvent("run_error", {"run_id": run_id, "error": str(exc)}))

        result = {
            "success": status == "completed",
            "status": status,
            "final_text": final_text,
            "run_id": run_id,
            "checkpoint_id": ctx.checkpoint_id,
            "mutated_files": sorted(ctx.mutated_files),
            "todos": ctx.todos,
            "turns": turns_used,
        }
        trajectory.finish(status=status, result={
            "final_text": final_text, "mutated_files": result["mutated_files"]})
        self.emit(AgentEvent("run_completed", result))
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_loop.py -q`
Expected: 6 passed

- [ ] **Step 5: Run the whole core suite**

Run: `venv\Scripts\python.exe -m pytest tests\core -q`
Expected: all pass

- [ ] **Step 6: Commit** — `feat(core): the AgentLoop`

---

### Task 10: Repo map (`repo_map.py`)

**Files:**
- Create: `nexcoder/agent/core/repo_map.py`
- Test: `tests/core/test_repo_map.py`

**Interfaces:**
- Consumes: `has_skipped_part` (existing path_filters).
- Produces:
  - `build_repo_map(project_root: str | Path) -> dict` — `{"generated_at": iso, "files": [{"path": str, "symbols": [str]}]}` (files sorted by path; symbols only for .py via `ast` and .ts/.tsx/.js/.jsx via regex; max 400 files, max 20 symbols/file).
  - `save_repo_map(project_root, repo_map) -> Path` — writes `.nexcoder/repo_map.json`.
  - `load_repo_map(project_root) -> dict | None`.
  - `render_repo_map(repo_map, token_budget: int = 1500) -> str` — tree-ish text block truncated to `token_budget * 3` chars.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_repo_map.py
from nexcoder.agent.core.repo_map import (
    build_repo_map, load_repo_map, render_repo_map, save_repo_map,
)


def seed(tmp_path):
    (tmp_path / "app.py").write_text(
        "class Server:\n    def start(self):\n        pass\n\n"
        "def helper():\n    pass\n", encoding="utf-8")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "main.ts").write_text(
        "export function boot() {}\nexport class App {}\nconst x = 1\n",
        encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.py").write_text("def hidden(): pass", encoding="utf-8")


def test_build_extracts_symbols_and_skips_filtered(tmp_path):
    seed(tmp_path)
    repo_map = build_repo_map(tmp_path)
    paths = {f["path"]: f["symbols"] for f in repo_map["files"]}
    assert "app.py" in paths and "web/main.ts" in paths
    assert "node_modules/dep.py" not in paths
    assert "class Server" in paths["app.py"] and "def helper" in paths["app.py"]
    assert "function boot" in paths["web/main.ts"] and "class App" in paths["web/main.ts"]


def test_save_and_load_roundtrip(tmp_path):
    seed(tmp_path)
    repo_map = build_repo_map(tmp_path)
    save_repo_map(tmp_path, repo_map)
    loaded = load_repo_map(tmp_path)
    assert loaded == repo_map
    assert load_repo_map(tmp_path / "nowhere") is None


def test_render_respects_budget(tmp_path):
    seed(tmp_path)
    text = render_repo_map(build_repo_map(tmp_path), token_budget=50)
    assert len(text) <= 50 * 3 + 40  # small tolerance for truncation marker
    assert "app.py" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_repo_map.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/repo_map.py
"""Repo map: lightweight file + symbol index injected into agent prompts."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from nexcoder.agent.path_filters import has_skipped_part

MAX_FILES = 400
MAX_SYMBOLS = 20
SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
JS_SYMBOL_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?"
    r"(?:(class)\s+([A-Za-z_$][\w$]*)|(?:async\s+)?(function)\s+([A-Za-z_$][\w$]*))",
    re.MULTILINE)


def _python_symbols(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(f"def {node.name}")
    return symbols[:MAX_SYMBOLS]


def _js_symbols(text: str) -> list[str]:
    symbols: list[str] = []
    for match in JS_SYMBOL_PATTERN.finditer(text):
        if match.group(1):
            symbols.append(f"class {match.group(2)}")
        elif match.group(3):
            symbols.append(f"function {match.group(4)}")
        if len(symbols) >= MAX_SYMBOLS:
            break
    return symbols


def build_repo_map(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if len(files) >= MAX_FILES:
            break
        relative_parts = path.relative_to(root).parts
        if has_skipped_part(relative_parts):
            continue
        if not path.is_file() or path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        symbols = (_python_symbols(text) if path.suffix.lower() == ".py"
                   else _js_symbols(text))
        files.append({"path": path.relative_to(root).as_posix(), "symbols": symbols})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "files": files}


def save_repo_map(project_root: str | Path, repo_map: dict[str, Any]) -> Path:
    folder = Path(project_root) / ".nexcoder"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "repo_map.json"
    path.write_text(json.dumps(repo_map, indent=2), encoding="utf-8")
    return path


def load_repo_map(project_root: str | Path) -> dict[str, Any] | None:
    path = Path(project_root) / ".nexcoder" / "repo_map.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def render_repo_map(repo_map: dict[str, Any], token_budget: int = 1500) -> str:
    lines = ["# Project map"]
    for item in repo_map.get("files", []):
        symbols = ", ".join(item.get("symbols") or [])
        lines.append(f"{item['path']}" + (f" — {symbols}" if symbols else ""))
    text = "\n".join(lines)
    char_budget = token_budget * 3
    if len(text) > char_budget:
        text = text[:char_budget] + "\n[map truncated]"
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_repo_map.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit** — `feat(core): repo map builder and renderer`

---

### Task 11: Session persistence (`session_store.py`)

**Files:**
- Create: `nexcoder/agent/core/session_store.py`
- Modify: `nexcoder/agent/core/loop.py` (persist after every turn when `session_store` passed)
- Test: `tests/core/test_session_store.py`

**Interfaces:**
- Produces:
  - `SessionStore(project_root)` with `.save(run_id, payload: dict) -> Path` (writes `.nexcoder/sessions/<run_id>.json`), `.load(run_id) -> dict | None`, `.list_runs() -> list[str]` (newest first).
  - `AgentLoop.__init__` gains keyword `session_store: SessionStore | None = None`; when set, after each turn the loop calls `session_store.save(run_id, {"task", "status": "running", "messages": conversation.messages(), "todos": ctx.todos, "turn": turn})`, and once more at the end with the final status.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_session_store.py
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.session_store import SessionStore
from nexcoder.agent.core.transport import XmlAdapter


class OneShotModel:
    def complete(self, messages, *, extras, on_delta=None):
        return {"role": "assistant", "content": "all done"}


def test_store_save_load_list(tmp_path):
    store = SessionStore(tmp_path)
    store.save("run_a", {"task": "t1"})
    store.save("run_b", {"task": "t2"})
    assert store.load("run_a") == {"task": "t1"}
    assert store.load("missing") is None
    assert set(store.list_runs()) == {"run_a", "run_b"}


def test_loop_persists_session(tmp_path):
    store = SessionStore(tmp_path)
    loop = AgentLoop(
        project_root=tmp_path, model=OneShotModel(), adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="sys", session_store=store)
    result = loop.run("say done")
    saved = store.load(result["run_id"])
    assert saved is not None
    assert saved["status"] == "completed"
    assert saved["task"] == "say done"
    assert any(m["role"] == "assistant" for m in saved["messages"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_session_store.py -q`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/session_store.py
"""Persist agent run transcripts so crashed runs can be inspected/resumed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, project_root: str | Path) -> None:
        self._folder = Path(project_root) / ".nexcoder" / "sessions"

    def save(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._folder.mkdir(parents=True, exist_ok=True)
        path = self._folder / f"{run_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                   default=str), encoding="utf-8")
        return path

    def load(self, run_id: str) -> dict[str, Any] | None:
        path = self._folder / f"{run_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list_runs(self) -> list[str]:
        if not self._folder.is_dir():
            return []
        entries = sorted(self._folder.glob("run_*.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        return [entry.stem for entry in entries]
```

In `loop.py`:
1. Add import `from nexcoder.agent.core.session_store import SessionStore` and `session_store: SessionStore | None = None` parameter stored as `self.session_store`.
2. Add a helper inside `run` (after `results` are appended, end of each turn iteration) and after the loop finishes:

```python
        def _persist(current_status: str, turn_number: int) -> None:
            if self.session_store is None:
                return
            try:
                self.session_store.save(run_id, {
                    "task": task, "status": current_status,
                    "messages": conversation.messages(),
                    "todos": ctx.todos, "turn": turn_number})
            except Exception:
                logger.warning("Session persist failed", exc_info=True)
```

Call `_persist("running", turn)` as the last statement of each loop iteration (after the guardrail-stall check, before `continue`/next turn), and `_persist(status, turns_used)` right before `trajectory.finish(...)`.

- [ ] **Step 4: Run tests**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_session_store.py tests\core\test_loop.py -q`
Expected: all pass

- [ ] **Step 5: Commit** — `feat(core): session persistence for agent runs`

---

### Task 12: ModelConnector agent client (`chat_agent`)

**Files:**
- Modify: `nexcoder/agent/model_connector.py`
- Test: `tests/core/test_model_connector_agent.py`

**Interfaces:**
- Consumes: existing `ModelConnector` env config (`NEXA_API_URL`, `NEXA_MODEL`, `NEXA_API_KEY`).
- Produces:
  - `ModelConnector.chat_agent(messages, *, extras=None, on_delta=None, temperature=0.2, max_tokens=3072) -> dict` — returns a full OpenAI-style assistant message dict `{"role": "assistant", "content": str, "tool_calls"?: [...]}`. Streams SSE; aggregates `delta.content` (calling `on_delta`) and `delta.tool_calls` fragments by index. Raises `ModelUnavailableError` / `ModelHTTPError` / `ModelStreamError` on failure (never yields warning strings — the loop needs exceptions).
  - Static method `ModelConnector.merge_stream_chunks(chunks: list[dict]) -> dict` — pure aggregation function (this is what unit tests cover; the HTTP path reuses it).
  - `AgentModelClient(connector)` — tiny adapter satisfying the loop's `ModelClient` protocol: `complete(messages, *, extras, on_delta)` calls `connector.chat_agent(messages, extras=extras, on_delta=on_delta)` merging `extras` into the payload (e.g. `tools`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_model_connector_agent.py
from nexcoder.agent.model_connector import ModelConnector


def chunk(delta, finish=None):
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


def test_merge_text_only():
    message = ModelConnector.merge_stream_chunks([
        chunk({"role": "assistant"}),
        chunk({"content": "Hello "}),
        chunk({"content": "world"}),
        chunk({}, finish="stop"),
    ])
    assert message == {"role": "assistant", "content": "Hello world"}


def test_merge_tool_call_fragments():
    message = ModelConnector.merge_stream_chunks([
        chunk({"role": "assistant"}),
        chunk({"tool_calls": [{"index": 0, "id": "call_9", "type": "function",
                               "function": {"name": "read_file", "arguments": ""}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"path":'}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": ' "a.py"}'}}]}),
        chunk({}, finish="tool_calls"),
    ])
    assert message["content"] == ""
    call = message["tool_calls"][0]
    assert call["id"] == "call_9"
    assert call["function"]["name"] == "read_file"
    assert call["function"]["arguments"] == '{"path": "a.py"}'


def test_merge_parallel_tool_calls():
    message = ModelConnector.merge_stream_chunks([
        chunk({"tool_calls": [{"index": 0, "id": "a", "function": {"name": "glob", "arguments": "{}"}}]}),
        chunk({"tool_calls": [{"index": 1, "id": "b", "function": {"name": "grep", "arguments": "{}"}}]}),
    ])
    assert [c["id"] for c in message["tool_calls"]] == ["a", "b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_model_connector_agent.py -q`
Expected: FAIL (no `merge_stream_chunks`)

- [ ] **Step 3: Implement** — add to `ModelConnector` (and a module-level class at the bottom):

```python
    @staticmethod
    def merge_stream_chunks(chunks: list[dict]) -> dict:
        """Aggregate OpenAI streaming chunks into one assistant message."""
        content_parts: list[str] = []
        calls: dict[int, dict] = {}
        for item in chunks:
            delta = (item.get("choices") or [{}])[0].get("delta") or {}
            if delta.get("content"):
                content_parts.append(str(delta["content"]))
            for fragment in delta.get("tool_calls") or []:
                index = int(fragment.get("index", 0))
                slot = calls.setdefault(index, {
                    "id": "", "type": "function",
                    "function": {"name": "", "arguments": ""}})
                if fragment.get("id"):
                    slot["id"] = fragment["id"]
                fn = fragment.get("function") or {}
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
        message: dict = {"role": "assistant", "content": "".join(content_parts)}
        if calls:
            message["tool_calls"] = [calls[i] for i in sorted(calls)]
        return message

    def chat_agent(
        self,
        messages: list[dict],
        *,
        extras: dict | None = None,
        on_delta=None,
        temperature: float = 0.2,
        max_tokens: int = 3072,
    ) -> dict:
        """Agent-loop entry point: full assistant message, exceptions on failure."""
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        payload.update(extras or {})
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = f"{self._base_url.rstrip('/')}/v1/chat/completions"
        chunks: list[dict] = []
        try:
            with httpx.Client(timeout=self._timeout) as client:
                with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        chunks.append(chunk)
                        if on_delta:
                            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                            if delta.get("content"):
                                on_delta(str(delta["content"]))
        except httpx.ConnectError as exc:
            raise ModelUnavailableError(
                f"Cannot connect to AI backend at {self._base_url}") from exc
        except httpx.HTTPStatusError as exc:
            raise ModelHTTPError(
                f"AI backend error: HTTP {exc.response.status_code}") from exc
        except (ModelUnavailableError, ModelHTTPError):
            raise
        except Exception as exc:
            raise ModelStreamError(f"AI stream interrupted: {exc}") from exc
        return self.merge_stream_chunks(chunks)


class AgentModelClient:
    """Adapts ModelConnector to the AgentLoop ModelClient protocol."""

    def __init__(self, connector: ModelConnector) -> None:
        self.connector = connector

    def complete(self, messages, *, extras, on_delta=None):
        return self.connector.chat_agent(messages, extras=extras, on_delta=on_delta)
```

(`AgentModelClient` goes at module bottom of `model_connector.py`.)

- [ ] **Step 4: Run tests**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_model_connector_agent.py tests -q`
Expected: new tests pass; no regressions

- [ ] **Step 5: Commit** — `feat(core): streaming agent chat client with tool_calls aggregation`

---

### Task 13: Backend config + CLI engine v2

**Files:**
- Create: `nexcoder/agent/core/backend_config.py`
- Modify: `nexcoder/cli.py` (add `--engine`, `--adapter`, `--auto` flags and the v2 run path)
- Test: `tests/core/test_backend_config.py` (config only; CLI path is exercised in Task 16 acceptance)

**Interfaces:**
- Produces:
  - `BackendConfig(base_url, model, api_key, adapter, context_window)` dataclass; `load_backend_config() -> BackendConfig` reading env: `NEXA_API_URL` (default `http://127.0.0.1:8001`), `NEXA_MODEL` (default `default`), `NEXA_API_KEY` (default empty), `NEXCODER_ADAPTER` (default `xml`), `NEXA_CONTEXT_WINDOW` (default `8192`).
  - CLI: `--engine {v1,v2}` (default env `NEXCODER_ENGINE` or `v1`), `--adapter {xml,native}` (overrides env), `--auto` (FullAutoGate). v2 path builds: `ModelConnector` + `AgentModelClient`, adapter via `get_adapter`, `build_default_belt()`, repo map (`build_repo_map`/`save_repo_map`/`render_repo_map` as `extra_system`), `SessionStore`, terminal `ConsolePermissionGate` (prompts `[a]llow / always / [d]eny` via `input()`; wrapped in `AllowlistGate`; `--auto` swaps in `FullAutoGate`; `--jsonl` implies deny-less `AllowAllGate` is NOT used — jsonl mode uses AllowlistGate with a DenyGate inner so unattended runs never hang), `AgentLoop(system_prompt=AGENT_SYSTEM_PROMPT, max_turns=50, context_window=config.context_window)`. Events render through the existing `ConsoleRenderer.event` for `--jsonl`, else human-readable lines.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_backend_config.py
from nexcoder.agent.core.backend_config import load_backend_config


def test_defaults(monkeypatch):
    for var in ("NEXA_API_URL", "NEXA_MODEL", "NEXA_API_KEY",
                "NEXCODER_ADAPTER", "NEXA_CONTEXT_WINDOW"):
        monkeypatch.delenv(var, raising=False)
    config = load_backend_config()
    assert config.base_url == "http://127.0.0.1:8001"
    assert config.adapter == "xml"
    assert config.context_window == 8192


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("NEXA_API_URL", "http://gpu-server:8000")
    monkeypatch.setenv("NEXCODER_ADAPTER", "native")
    monkeypatch.setenv("NEXA_CONTEXT_WINDOW", "32768")
    config = load_backend_config()
    assert config.base_url == "http://gpu-server:8000"
    assert config.adapter == "native"
    assert config.context_window == 32768
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_backend_config.py -q`
Expected: FAIL

- [ ] **Step 3: Implement backend_config**

```python
# nexcoder/agent/core/backend_config.py
"""The migration seam: one config object describes any OpenAI-compatible backend."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class BackendConfig:
    base_url: str
    model: str
    api_key: str
    adapter: str  # "xml" | "native"
    context_window: int


def load_backend_config() -> BackendConfig:
    return BackendConfig(
        base_url=os.getenv("NEXA_API_URL", "http://127.0.0.1:8001"),
        model=os.getenv("NEXA_MODEL", "default"),
        api_key=os.getenv("NEXA_API_KEY", ""),
        adapter=os.getenv("NEXCODER_ADAPTER", "xml"),
        context_window=max(2048, int(os.getenv("NEXA_CONTEXT_WINDOW", "8192"))),
    )
```

- [ ] **Step 4: Wire CLI v2 path** — in `nexcoder/cli.py`:

Add to `parse_args`:

```python
    parser.add_argument("--engine", choices=["v1", "v2"],
                        default=os.getenv("NEXCODER_ENGINE", "v1"))
    parser.add_argument("--adapter", choices=["xml", "native"], default=None)
    parser.add_argument("--auto", action="store_true",
                        help="Full auto: skip command permission prompts")
```

Add the v2 runner (new function in `cli.py`):

```python
def run_v2(args, prompt: str, project_root: Path, renderer: ConsoleRenderer) -> int:
    from nexcoder.agent.core.backend_config import load_backend_config
    from nexcoder.agent.core.belt_factory import build_default_belt
    from nexcoder.agent.core.loop import AGENT_SYSTEM_PROMPT, AgentLoop
    from nexcoder.agent.core.permissions import AllowlistGate, FullAutoGate
    from nexcoder.agent.core.repo_map import build_repo_map, render_repo_map, save_repo_map
    from nexcoder.agent.core.session_store import SessionStore
    from nexcoder.agent.core.tools.base import ALLOW, ALLOW_ALWAYS, DENY
    from nexcoder.agent.core.transport import get_adapter
    from nexcoder.agent.model_connector import AgentModelClient, ModelConnector

    config = load_backend_config()
    adapter_name = args.adapter or config.adapter

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
            print(f"\n> {event.payload['tool']} {json.dumps(event.payload.get('args', {}))[:160]}")
        elif event.type == "tool_result":
            marker = "ok" if event.payload.get("success") else "FAIL"
            print(f"  [{marker}] {event.payload.get('summary', '')}")
        elif event.type == "command_output":
            print(f"  | {event.payload.get('line', '')}")
        elif event.type == "todo_updated":
            for todo in event.payload.get("todos", []):
                mark = {"pending": " ", "in_progress": ">", "completed": "x"}[todo["status"]]
                print(f"  [{mark}] {todo['content']}")

    loop = AgentLoop(
        project_root=project_root,
        model=AgentModelClient(ModelConnector()),
        adapter=get_adapter(adapter_name),
        belt=build_default_belt(),
        system_prompt=AGENT_SYSTEM_PROMPT,
        emit=emit,
        permission_gate=gate,
        max_turns=50,
        context_window=config.context_window,
        extra_system=render_repo_map(repo_map),
        session_store=SessionStore(project_root),
    )
    result = loop.run(prompt)
    print(f"\n--- {result['status']} in {result['turns']} turn(s); "
          f"{len(result['mutated_files'])} file(s) changed ---")
    if result["final_text"]:
        print(result["final_text"])
    return 0 if result["success"] else 1
```

In `run_cli`, immediately after the project root and renderer are resolved, branch: `if args.engine == "v2": return run_v2(args, prompt, project_root, renderer)`.

- [ ] **Step 5: Run tests + smoke check**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_backend_config.py -q` — 2 passed.
Run: `venv\Scripts\python.exe -m nexcoder.cli --help` — shows `--engine`, `--adapter`, `--auto` without errors.

- [ ] **Step 6: Commit** — `feat(cli): v2 agentic engine behind --engine flag`

---

### Task 14: Bridge wiring (`agent_runtime_v2.py` + bridge slots)

**Files:**
- Create: `nexcoder/agent/agent_runtime_v2.py`
- Modify: `nexcoder/bridge.py`
- Test: `tests/core/test_ui_permission_gate.py` (gate logic; Qt worker verified by running the app in Task 15)

**Interfaces:**
- Consumes: Tasks 8–13 core modules; existing bridge patterns (`Signal(str)` JSON payloads).
- Produces:
  - `UiPermissionGate` with `.request(tool, detail) -> str` that blocks on a `threading.Event` (300s timeout → DENY) and `.resolve(request_id, decision)`; the gate emits its request through a callback `on_request(request_id, tool, detail)` supplied at construction.
  - `AgentV2Worker(QThread)` — signals `event_json = Signal(str)`, `finished_json = Signal(str)`; constructor `(project_root: str, prompt: str, gate: UiPermissionGate, full_auto: bool)`; `run()` builds the same stack as CLI `run_v2` (connector, adapter from `load_backend_config`, belt, repo map, session store) and forwards every `AgentEvent.to_dict()` as JSON.
  - Bridge additions: `agent_event = Signal(str)` and slots `agent_run_v2(prompt: str) -> str`, `agent_permission_response(request_id: str, decision: str) -> str`, `agent_revert_run(checkpoint_id: str) -> str` (calls `CheckpointManager.restore`), `agent_revert_file(checkpoint_id: str, path: str) -> str` (restore with `files=[path]`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_ui_permission_gate.py
import threading

from nexcoder.agent.agent_runtime_v2 import UiPermissionGate
from nexcoder.agent.core.tools.base import ALLOW, DENY


def test_gate_blocks_until_resolved():
    requests = []
    gate = UiPermissionGate(on_request=lambda rid, tool, detail: requests.append(rid))
    result_box = {}

    def ask():
        result_box["decision"] = gate.request(tool="run_command", detail="npm test")

    thread = threading.Thread(target=ask)
    thread.start()
    for _ in range(100):
        if requests:
            break
        threading.Event().wait(0.01)
    assert requests, "on_request was never called"
    gate.resolve(requests[0], ALLOW)
    thread.join(timeout=2)
    assert result_box["decision"] == ALLOW


def test_gate_times_out_to_deny():
    gate = UiPermissionGate(on_request=lambda *a: None, timeout=0.05)
    assert gate.request(tool="run_command", detail="x") == DENY


def test_gate_unknown_request_id_is_ignored():
    gate = UiPermissionGate(on_request=lambda *a: None, timeout=0.05)
    gate.resolve("nope", ALLOW)  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests\core\test_ui_permission_gate.py -q`
Expected: FAIL

- [ ] **Step 3: Implement `agent_runtime_v2.py`**

```python
# nexcoder/agent/agent_runtime_v2.py
"""Qt worker + UI permission gate for the v2 agentic engine."""

from __future__ import annotations

import json
import threading
from typing import Callable
import uuid

from PySide6.QtCore import QThread, Signal

from nexcoder.agent.core.backend_config import load_backend_config
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.loop import AGENT_SYSTEM_PROMPT, AgentLoop
from nexcoder.agent.core.permissions import AllowlistGate, FullAutoGate
from nexcoder.agent.core.repo_map import build_repo_map, render_repo_map, save_repo_map
from nexcoder.agent.core.session_store import SessionStore
from nexcoder.agent.core.tools.base import DENY
from nexcoder.agent.core.transport import get_adapter
from nexcoder.agent.model_connector import AgentModelClient, ModelConnector

PERMISSION_TIMEOUT = 300.0


class UiPermissionGate:
    """Blocks the agent worker thread until the UI answers (or timeout)."""

    def __init__(self, on_request: Callable[[str, str, str], None],
                 timeout: float = PERMISSION_TIMEOUT) -> None:
        self._on_request = on_request
        self._timeout = timeout
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    def request(self, *, tool: str, detail: str) -> str:
        request_id = f"perm_{uuid.uuid4().hex[:8]}"
        entry = {"event": threading.Event(), "decision": DENY}
        with self._lock:
            self._pending[request_id] = entry
        self._on_request(request_id, tool, detail)
        entry["event"].wait(self._timeout)
        with self._lock:
            self._pending.pop(request_id, None)
        return entry["decision"]

    def resolve(self, request_id: str, decision: str) -> None:
        with self._lock:
            entry = self._pending.get(request_id)
        if entry is None:
            return
        entry["decision"] = decision
        entry["event"].set()


class AgentV2Worker(QThread):
    event_json = Signal(str)
    finished_json = Signal(str)

    def __init__(self, project_root: str, prompt: str,
                 gate: UiPermissionGate, full_auto: bool = False) -> None:
        super().__init__()
        self._project_root = project_root
        self._prompt = prompt
        self._gate = gate
        self._full_auto = full_auto

    def run(self) -> None:
        try:
            config = load_backend_config()
            permission_gate = (FullAutoGate() if self._full_auto
                               else AllowlistGate(self._gate, self._project_root))
            repo_map = build_repo_map(self._project_root)
            save_repo_map(self._project_root, repo_map)
            loop = AgentLoop(
                project_root=self._project_root,
                model=AgentModelClient(ModelConnector()),
                adapter=get_adapter(config.adapter),
                belt=build_default_belt(),
                system_prompt=AGENT_SYSTEM_PROMPT,
                emit=lambda event: self.event_json.emit(json.dumps(
                    event.to_dict(), ensure_ascii=False, default=str)),
                permission_gate=permission_gate,
                max_turns=50,
                context_window=config.context_window,
                extra_system=render_repo_map(repo_map),
                session_store=SessionStore(self._project_root),
            )
            result = loop.run(self._prompt)
        except Exception as exc:  # worker must never crash the app
            result = {"success": False, "status": "error", "final_text": str(exc),
                      "run_id": "", "checkpoint_id": None, "mutated_files": [],
                      "todos": [], "turns": 0}
        self.finished_json.emit(json.dumps(result, ensure_ascii=False, default=str))
```

- [ ] **Step 4: Wire the bridge** — in `nexcoder/bridge.py`, following the existing signal/slot idiom (`@Slot(str, result=str)`, JSON strings in/out):

1. Add signal: `agent_event = Signal(str)` next to the existing agent signals.
2. Add fields in `__init__`: `self._agent_v2_worker = None` and `self._agent_v2_gate = None`.
3. Add slots:

```python
    @Slot(str, result=str)
    def agent_run_v2(self, prompt: str) -> str:
        if self._agent_v2_worker is not None and self._agent_v2_worker.isRunning():
            return json.dumps({"success": False, "error": "Agent is already running"})
        project_root = self._project.current_project_path
        if not project_root:
            return json.dumps({"success": False, "error": "No project open"})
        from nexcoder.agent.agent_runtime_v2 import AgentV2Worker, UiPermissionGate
        self._agent_v2_gate = UiPermissionGate(
            on_request=lambda rid, tool, detail: self.agent_event.emit(json.dumps({
                "type": "permission_request",
                "payload": {"id": rid, "tool": tool, "command": detail}})))
        self._agent_v2_worker = AgentV2Worker(project_root, prompt, self._agent_v2_gate)
        self._agent_v2_worker.event_json.connect(self.agent_event.emit)
        self._agent_v2_worker.finished_json.connect(self._on_agent_v2_finished)
        self._agent_v2_worker.start()
        return json.dumps({"success": True})

    def _on_agent_v2_finished(self, result_json: str) -> None:
        self.agent_complete.emit(result_json)
        try:
            tree = self._filesystem.get_file_tree()
            self.file_tree_updated.emit(json.dumps(tree))
        except Exception:
            pass

    @Slot(str, str, result=str)
    def agent_permission_response(self, request_id: str, decision: str) -> str:
        if self._agent_v2_gate is not None:
            self._agent_v2_gate.resolve(request_id, decision)
        return json.dumps({"success": True})

    @Slot(str, result=str)
    def agent_revert_run(self, checkpoint_id: str) -> str:
        from nexcoder.services.checkpoint import CheckpointManager
        manager = CheckpointManager(self._project.current_project_path)
        try:
            restored = manager.restore(checkpoint_id)
            tree = self._filesystem.get_file_tree()
            self.file_tree_updated.emit(json.dumps(tree))
            return json.dumps({"success": True, **restored})
        except FileNotFoundError as exc:
            return json.dumps({"success": False, "error": str(exc)})

    @Slot(str, str, result=str)
    def agent_revert_file(self, checkpoint_id: str, path: str) -> str:
        from nexcoder.services.checkpoint import CheckpointManager
        manager = CheckpointManager(self._project.current_project_path)
        try:
            restored = manager.restore(checkpoint_id, files=[path])
            return json.dumps({"success": True, **restored})
        except FileNotFoundError as exc:
            return json.dumps({"success": False, "error": str(exc)})
```

(Adapt attribute names — `self._project.current_project_path`, `self._filesystem.get_file_tree()` — to the actual names used elsewhere in `bridge.py`; read the neighboring `agent_run` slot and reuse its project-root and tree-refresh calls exactly.)

- [ ] **Step 5: Run tests**

Run: `venv\Scripts\python.exe -m pytest tests\core -q`
Expected: all pass. Then `venv\Scripts\python.exe -c "import nexcoder.bridge"` — imports cleanly.

- [ ] **Step 6: Commit** — `feat(bridge): v2 agent worker, UI permission gate, revert slots`

---

### Task 15: React UI — agent run panel, todos, permissions, revert

**Files:**
- Create: `nexcoder/ui/src/components/AIPanel/AgentRunPanel.tsx`, `nexcoder/ui/src/store/useAgentRunStore.ts`
- Modify: `nexcoder/ui/src/services/bridge.ts`, `nexcoder/ui/src/types/bridge.d.ts`, `nexcoder/ui/src/components/AIPanel/AIPanel.tsx` (render AgentRunPanel when agent mode is active and a v2 run exists; send via `agentRunV2`)
- Verify: `cd nexcoder\ui && npm.cmd run build`

**Interfaces:**
- Consumes: bridge slots/signals from Task 14 (`agent_event`, `agent_run_v2`, `agent_permission_response`, `agent_revert_run`, `agent_revert_file`).
- Produces (TS):
  - `bridge.ts`: `agentRunV2(prompt: string): Promise<{success: boolean}>`, `agentPermissionResponse(id: string, decision: "allow" | "allow_always" | "deny"): void`, `agentRevertRun(checkpointId: string)`, `agentRevertFile(checkpointId: string, path: string)`, `onAgentEvent(cb: (event: AgentEventMsg) => void)` — connect to the `agent_event` signal following the existing `agent_stream` connection pattern in `services/bridge.ts`.
  - `useAgentRunStore`: state `{ runActive, steps: AgentStep[], todos: Todo[], permission: PermissionReq | null, checkpointId: string | null, mutatedFiles: string[], finalText: string }`; action `handleEvent(event)` switch on `event.type` (`tool_started` appends a step; `tool_result` finalizes it; `todo_updated` replaces todos; `permission_request` sets permission; `permission_resolved` clears it; `checkpoint_created` stores id; `edit_applied` appends to mutatedFiles; `run_completed` stores result and sets runActive false).
  - `AgentRunPanel` renders: todo checklist, tool-step list (icon + label + ok/fail), streaming text, permission card with Allow / Always allow / Deny buttons calling `agentPermissionResponse`, and after completion a changed-files list with per-file "Revert" and a "Revert all" button.

- [ ] **Step 1: Add types + bridge methods** (`types/bridge.d.ts` gains `agent_event` signal and the four new slot signatures matching the existing declaration style; `services/bridge.ts` adds the methods and `onAgentEvent`, mirroring how `agent_stream`/`agent_run` are declared and connected).

- [ ] **Step 2: Create the store**

```tsx
// nexcoder/ui/src/store/useAgentRunStore.ts
import { create } from "zustand";

export interface AgentTodo { id: number; content: string; status: "pending" | "in_progress" | "completed"; }
export interface AgentStep { tool: string; args?: Record<string, unknown>; success?: boolean; summary?: string; done: boolean; }
export interface PermissionReq { id: string; tool: string; command: string; }
export interface AgentEventMsg { type: string; payload: Record<string, any>; ts?: number; }

interface AgentRunState {
  runActive: boolean;
  steps: AgentStep[];
  todos: AgentTodo[];
  permission: PermissionReq | null;
  checkpointId: string | null;
  mutatedFiles: string[];
  streamText: string;
  finalText: string;
  status: string;
  start: () => void;
  handleEvent: (event: AgentEventMsg) => void;
  reset: () => void;
}

export const useAgentRunStore = create<AgentRunState>((set) => ({
  runActive: false, steps: [], todos: [], permission: null,
  checkpointId: null, mutatedFiles: [], streamText: "", finalText: "", status: "",
  start: () => set({ runActive: true, steps: [], todos: [], permission: null,
                     checkpointId: null, mutatedFiles: [], streamText: "", finalText: "", status: "running" }),
  reset: () => set({ runActive: false, steps: [], todos: [], permission: null,
                     checkpointId: null, mutatedFiles: [], streamText: "", finalText: "", status: "" }),
  handleEvent: (event) => set((state) => {
    const { type, payload } = event;
    switch (type) {
      case "run_started": return { runActive: true, status: "running" };
      case "text_delta": return { streamText: state.streamText + (payload.text ?? "") };
      case "tool_started":
        return { steps: [...state.steps, { tool: payload.tool, args: payload.args, done: false }], streamText: "" };
      case "tool_result": {
        const steps = [...state.steps];
        for (let i = steps.length - 1; i >= 0; i--) {
          if (!steps[i].done && steps[i].tool === payload.tool) {
            steps[i] = { ...steps[i], done: true, success: payload.success, summary: payload.summary };
            break;
          }
        }
        return { steps };
      }
      case "todo_updated": return { todos: payload.todos ?? [] };
      case "permission_request":
        return { permission: { id: payload.id, tool: payload.tool, command: payload.command } };
      case "permission_resolved": return { permission: null };
      case "checkpoint_created": return { checkpointId: payload.checkpoint_id };
      case "edit_applied":
        return state.mutatedFiles.includes(payload.path)
          ? {} : { mutatedFiles: [...state.mutatedFiles, payload.path] };
      case "run_completed":
        return { runActive: false, status: payload.status, finalText: payload.final_text ?? "",
                 checkpointId: payload.checkpoint_id ?? state.checkpointId,
                 mutatedFiles: payload.mutated_files ?? state.mutatedFiles };
      case "run_error": return { runActive: false, status: "error", finalText: payload.error ?? "" };
      default: return {};
    }
  }),
}));
```

- [ ] **Step 3: Create AgentRunPanel** — presentational component reading the store; reuse existing `AIPanel.css` classes where possible (step rows can reuse the timeline-item styling used by `AgentTurnPanel.tsx`; inspect that file and match class names).

```tsx
// nexcoder/ui/src/components/AIPanel/AgentRunPanel.tsx
import { useAgentRunStore } from "../../store/useAgentRunStore";
import { bridge } from "../../services/bridge";

export function AgentRunPanel() {
  const { steps, todos, permission, checkpointId, mutatedFiles,
          streamText, finalText, status, runActive } = useAgentRunStore();

  return (
    <div className="agent-run-panel">
      {todos.length > 0 && (
        <div className="agent-todos">
          {todos.map((todo) => (
            <div key={todo.id} className={`agent-todo agent-todo-${todo.status}`}>
              <span>{todo.status === "completed" ? "☑" : todo.status === "in_progress" ? "▸" : "☐"}</span>
              <span>{todo.content}</span>
            </div>
          ))}
        </div>
      )}
      {steps.map((step, index) => (
        <div key={index} className="agent-step">
          <span className={step.done ? (step.success ? "step-ok" : "step-fail") : "step-running"}>
            {step.done ? (step.success ? "✓" : "✗") : "…"}
          </span>
          <span className="step-tool">{step.tool}</span>
          <span className="step-summary">{step.summary ?? ""}</span>
        </div>
      ))}
      {streamText && <div className="agent-stream-text">{streamText}</div>}
      {permission && (
        <div className="agent-permission-card">
          <div className="perm-title">Run command?</div>
          <code>{permission.command}</code>
          <div className="perm-actions">
            <button onClick={() => bridge.agentPermissionResponse(permission.id, "allow")}>Allow</button>
            <button onClick={() => bridge.agentPermissionResponse(permission.id, "allow_always")}>Always allow</button>
            <button onClick={() => bridge.agentPermissionResponse(permission.id, "deny")}>Deny</button>
          </div>
        </div>
      )}
      {!runActive && status && (
        <div className="agent-run-result">
          <div className={`run-status run-status-${status}`}>{status}</div>
          {finalText && <div className="run-final-text">{finalText}</div>}
          {mutatedFiles.length > 0 && checkpointId && (
            <div className="run-changed-files">
              {mutatedFiles.map((file) => (
                <div key={file} className="changed-file">
                  <span>{file}</span>
                  <button onClick={() => bridge.agentRevertFile(checkpointId, file)}>Revert</button>
                </div>
              ))}
              <button className="revert-all"
                      onClick={() => bridge.agentRevertRun(checkpointId)}>Revert all</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire into AIPanel** — in `AIPanel.tsx`: subscribe once (`useEffect`) with `bridge.onAgentEvent(useAgentRunStore.getState().handleEvent)`; when the user sends a message in agent mode, call `useAgentRunStore.getState().start()` then `bridge.agentRunV2(prompt)` (keep the existing v1 path for other modes); render `<AgentRunPanel />` in the message list while a v2 run exists. Add minimal styles for the new class names to `AIPanel.css` (follow its existing card/timeline styles).

- [ ] **Step 5: Build**

Run: `cd nexcoder\ui; npm.cmd run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit** — `feat(ui): agent run panel with todos, permissions, revert`

---

### Task 16: Acceptance — greenfield + brownfield e2e, engine default flip

**Files:**
- Create: `tests/e2e/run_greenfield.py`, `tests/e2e/run_brownfield.py`, `tests/e2e/fixtures/brownfield/calc.py`, `tests/e2e/fixtures/brownfield/test_calc.py`
- Modify: `nexcoder/cli.py` (default engine → `v2`), `README.md` (document v2 agent usage)

**Interfaces:**
- Consumes: the full v2 stack via `python -m nexcoder.cli --engine v2`.
- Both scripts require the local model server running (README instructions); they are manual acceptance harnesses, not pytest tests (no `test_` prefix, live under `tests/e2e/`).

- [ ] **Step 1: Brownfield fixture**

```python
# tests/e2e/fixtures/brownfield/calc.py
def add(a, b):
    return a - b  # seeded bug


def multiply(a, b):
    return a * b
```

```python
# tests/e2e/fixtures/brownfield/test_calc.py
from calc import add, multiply


def test_add():
    assert add(2, 3) == 5


def test_multiply():
    assert multiply(2, 3) == 6
```

- [ ] **Step 2: Greenfield harness**

```python
# tests/e2e/run_greenfield.py
"""Acceptance 1: empty folder -> complete product page, unattended.

Usage: venv\\Scripts\\python.exe tests\\e2e\\run_greenfield.py
Requires the local model server (models/start_api.bat) to be running.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

PROMPT = ("Build a responsive product page: index.html, styles.css, script.js. "
          "Dark theme, three product cards, working theme toggle. "
          "Plan with todo_write first, verify the files exist when done.")


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexcoder_greenfield_"))
    print(f"Workdir: {workdir}")
    proc = subprocess.run(
        [sys.executable, "-m", "nexcoder.cli", "--engine", "v2", "--auto",
         "--project", str(workdir), PROMPT],
        timeout=1800)
    expected = ["index.html", "styles.css", "script.js"]
    missing = [name for name in expected if not (workdir / name).is_file()]
    if proc.returncode != 0 or missing:
        print(f"FAIL: exit={proc.returncode}, missing={missing}")
        return 1
    print("PASS: all files created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Brownfield harness**

```python
# tests/e2e/run_brownfield.py
"""Acceptance 2: seeded failing test -> agent fixes it until green.

Usage: venv\\Scripts\\python.exe tests\\e2e\\run_brownfield.py
Requires the local model server to be running.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "brownfield"
PROMPT = ("The test suite is failing. Run 'python -m pytest -q' to see the "
          "failure, find the bug, fix it with edit_file, and re-run the tests "
          "until they pass.")


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexcoder_brownfield_"))
    shutil.copytree(FIXTURE, workdir, dirs_exist_ok=True)
    print(f"Workdir: {workdir}")
    proc = subprocess.run(
        [sys.executable, "-m", "nexcoder.cli", "--engine", "v2", "--auto",
         "--project", str(workdir), PROMPT],
        timeout=1800)
    verify = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                            cwd=workdir, capture_output=True, text=True)
    if proc.returncode != 0 or verify.returncode != 0:
        print(f"FAIL: agent exit={proc.returncode}, pytest exit={verify.returncode}")
        print(verify.stdout[-2000:])
        return 1
    print("PASS: tests green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run both harnesses against the local model** (start `models\start_api.bat` first). Both must print PASS. If the 7B model fails a run, inspect the trajectory under the workdir's `.nexcoder/trajectories/`, tune `AGENT_SYSTEM_PROMPT` wording or tool descriptions, and re-run — prompt/description tuning is expected here; loop/tool code changes require going back through the relevant task's tests.

- [ ] **Step 5: Flip the default** — in `cli.py`: `default=os.getenv("NEXCODER_ENGINE", "v2")`. Update `README.md` CLI section: document `--engine`, `--adapter`, `--auto`, the permission allowlist file `.nexcoder/permissions.json`, and the backend env vars (`NEXA_API_URL`, `NEXCODER_ADAPTER`, `NEXA_CONTEXT_WINDOW`) with the GPU-server migration note (set `NEXCODER_ADAPTER=native` + new URL).

- [ ] **Step 6: Full suite + commit** — `venv\Scripts\python.exe -m pytest tests -q` all green. Commit: `feat: v2 agentic engine passes acceptance; default engine flipped`.

---

## Deferred (explicitly out of this plan)

- Retiring `hermes_runtime.py` and porting ask/edit/debug/review/scan modes onto the new loop (do after v2 has soaked in agent mode).
- Embeddings/semantic search, sub-agents, plan-then-approve mode, web tools (spec: out of scope v1).

## Self-Review Notes

- Spec coverage: architecture/data-flow (T1–T4, T9), tool belt (T5–T8), autonomy+permissions (T5, T7, T14, T15), repo map (T10, wired T13/T14), todos (T8, T15), compaction (T4, T9), sessions (T11), migration seam (T3, T12, T13), error handling (T2 exception wrapping, T9 parse errors/stall, T7 timeout), acceptance (T16). Monaco live-refresh on edits arrives via the existing `file_tree_updated`/`file_changed` bridge flow after `_on_agent_v2_finished`; per-edit live refresh can hook `agent_event`/`edit_applied` in `AIPanel` later without core changes.
- Type consistency: `ToolContext.snapshot_before_mutation` used by files tools; `PermissionGate.request(tool=, detail=)` used by shell tool, gates, CLI, UI gate; `AgentEvent.to_dict()` shape `{type, payload, ts}` consumed by CLI emit, worker JSON, and the TS store's `AgentEventMsg`.
