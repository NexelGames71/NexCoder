# Claude Code-Style Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire skill auto-discovery into the v2 agent (catalog in prompt), add project-local skills, slash-command execution via deterministic preloading, and six ported Claude Code workflow skills.

**Architecture:** Extend `skills_registry` with an optional `project_root` merge layer; render a token-budgeted catalog into the v2 loop's `extra_system`; `AgentLoop.run` gains `preload_skill` which injects the skill body as a system message before turn 1; a shared slash parser feeds both CLI and UI.

**Tech Stack:** Python 3.11 stdlib, pytest, React/TS (existing patterns only).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-12-claude-code-skills-design.md`.
- No new dependencies. Tool results stay `{success: bool, ...}` dicts.
- Skill bodies written for an 8k-context model: imperative, < 150 lines.
- Tests in `tests/core/`; command `venv\Scripts\python.exe -m pytest tests\core -q`.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Project-local skills in the registry

**Files:**
- Modify: `nexcoder/agent/skills_registry.py`
- Test: `tests/core/test_skills_registry_project.py`

**Interfaces:**
- Produces: `get_skills(project_root: str | None = None)`, `get_skill(skill_id, project_root=None)`, `get_skill_body(skill_id, project_root=None)`, `get_skills_grouped(project_root=None)` — same return shapes as today. New category `project` (order 0). Project skills load from `<project_root>/.nexcoder/skills/*/SKILL.md` and override built-ins by id.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_skills_registry_project.py
from nexcoder.agent.skills_registry import get_skill_body, get_skills, get_skills_grouped


def make_project_skill(tmp_path, skill_id, description="A project skill", body="Do the thing."):
    folder = tmp_path / ".nexcoder" / "skills" / skill_id
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8")


def test_project_skills_merge_with_builtins(tmp_path):
    make_project_skill(tmp_path, "deploy-widget")
    skills = get_skills(str(tmp_path))
    by_id = {s["id"]: s for s in skills}
    assert "deploy-widget" in by_id
    assert by_id["deploy-widget"]["category"] == "project"
    assert "test-driven-development" in by_id  # built-ins still present


def test_project_skill_overrides_builtin(tmp_path):
    make_project_skill(tmp_path, "test-driven-development",
                       description="Our custom TDD", body="Custom body.")
    body = get_skill_body("test-driven-development", str(tmp_path))
    assert body is not None and body["body"] == "Custom body."


def test_no_project_root_is_builtins_only(tmp_path):
    baseline = {s["id"] for s in get_skills()}
    make_project_skill(tmp_path, "deploy-widget")
    assert "deploy-widget" not in baseline
    assert get_skill_body("deploy-widget") is None


def test_grouped_includes_project_category_first(tmp_path):
    make_project_skill(tmp_path, "deploy-widget")
    grouped = get_skills_grouped(str(tmp_path))
    categories = grouped["categories"]
    assert categories[0]["id"] == "project"
    assert any(s["id"] == "deploy-widget" for s in grouped["skills_by_category"]["project"])


def test_malformed_project_skill_is_skipped(tmp_path):
    folder = tmp_path / ".nexcoder" / "skills" / "broken"
    folder.mkdir(parents=True)
    # No SKILL.md at all
    skills = get_skills(str(tmp_path))
    assert all(s["id"] != "broken" for s in skills)
```

- [ ] **Step 2: Run to verify failure** — `venv\Scripts\python.exe -m pytest tests\core\test_skills_registry_project.py -q` — FAIL (`get_skills() takes 0 positional arguments`).

- [ ] **Step 3: Implement** in `skills_registry.py`:

1. Add to `SKILL_CATEGORIES` (top of list): `SkillCategory(id="project", label="Project", description="Skills defined by the open project", order=0)` and `CATEGORY_ICONS["project"] = "Folder"`.
2. `_load_skill_dir(skill_dir, *, default_category: str | None = None)` — after computing `category = _category_for(name, metadata)`, apply: when `default_category` is set and the frontmatter declared no valid category, use `default_category`. Concretely replace the category line with:

```python
    declared = (metadata.get("category") or "").strip().lower()
    if declared in CATEGORY_BY_ID:
        category = declared
    elif default_category is not None:
        category = default_category
    else:
        category = SKILL_CATEGORY_OVERRIDES.get(name, "meta")
```

3. `_load_all_skills(project_root: str | None = None)`:

```python
def _load_all_skills(project_root: str | None = None) -> list[SkillFull]:
    by_id: dict[str, SkillFull] = {}
    base = _skills_dir()
    if os.path.isdir(base):
        for entry in sorted(os.listdir(base)):
            full = os.path.join(base, entry)
            if os.path.isdir(full):
                loaded = _load_skill_dir(full)
                if loaded is not None:
                    by_id[loaded.meta.id] = loaded
    if project_root:
        project_base = os.path.join(project_root, ".nexcoder", "skills")
        if os.path.isdir(project_base):
            for entry in sorted(os.listdir(project_base)):
                full = os.path.join(project_base, entry)
                if os.path.isdir(full):
                    loaded = _load_skill_dir(full, default_category="project")
                    if loaded is not None:
                        by_id[loaded.meta.id] = loaded  # project wins
    return list(by_id.values())
```

4. Thread `project_root: str | None = None` through `get_skills`, `get_skill`, `get_skill_body`, `get_skills_grouped` (each passes it to `_load_all_skills`; grouped seeds `grouped` from all categories including `project`).

- [ ] **Step 4: Run new tests + full suite** — both green (`tests\core` then `tests -q`).

- [ ] **Step 5: Commit** — `feat(skills): project-local skills merge over built-ins`

---

### Task 2: Skills catalog renderer

**Files:**
- Create: `nexcoder/agent/core/skills_catalog.py`
- Test: `tests/core/test_skills_catalog.py`

**Interfaces:**
- Consumes: `get_skills(project_root)` (Task 1).
- Produces: `render_skills_catalog(project_root: str | None = None, token_budget: int = 800) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_skills_catalog.py
from nexcoder.agent.core.skills_catalog import render_skills_catalog
from tests.core.test_skills_registry_project import make_project_skill


def test_catalog_lists_skills_with_header():
    text = render_skills_catalog()
    assert text.startswith("# Skills")
    assert "load_skill" in text
    assert "- test-driven-development" in text


def test_project_skills_listed_first(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", description="Deploy the widget")
    text = render_skills_catalog(str(tmp_path))
    lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert lines[0].startswith("- deploy-widget")


def test_catalog_truncates_at_budget(tmp_path):
    for i in range(40):
        make_project_skill(tmp_path, f"skill-{i:02}", description="x" * 200)
    text = render_skills_catalog(str(tmp_path), token_budget=100)
    assert len(text) <= 100 * 3 + 80
    assert "[more skills omitted]" in text


def test_description_capped_at_90_chars(tmp_path):
    make_project_skill(tmp_path, "wordy", description="d" * 300)
    text = render_skills_catalog(str(tmp_path))
    line = next(l for l in text.splitlines() if l.startswith("- wordy"))
    assert len(line) <= len("- wordy — ") + 90
```

- [ ] **Step 2: Run to verify failure** — ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/skills_catalog.py
"""Render the skill catalog block for the v2 agent system prompt."""

from __future__ import annotations

from nexcoder.agent.skills_registry import get_skills

HEADER = (
    "# Skills\n"
    "Load a skill with load_skill when the task matches its purpose, "
    "then follow it.")
TRUNCATION_MARKER = "[more skills omitted]"
DESCRIPTION_CAP = 90


def render_skills_catalog(project_root: str | None = None,
                          token_budget: int = 800) -> str:
    skills = get_skills(project_root)
    project = sorted((s for s in skills if s["category"] == "project"),
                     key=lambda s: s["id"])
    builtin = sorted((s for s in skills if s["category"] != "project"),
                     key=lambda s: s["id"])
    char_budget = token_budget * 3
    lines = [HEADER]
    used = len(HEADER)
    for skill in [*project, *builtin]:
        line = f"- {skill['id']} — {(skill['description'] or '')[:DESCRIPTION_CAP]}"
        if used + len(line) + 1 > char_budget:
            lines.append(TRUNCATION_MARKER)
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `feat(core): skill catalog renderer for agent prompt`

---

### Task 3: Slash-command parser

**Files:**
- Create: `nexcoder/agent/core/slash.py`
- Test: `tests/core/test_slash.py`

**Interfaces:**
- Produces: `parse_slash_command(text: str, known_ids: set[str]) -> tuple[str | None, str]`; `DEFAULT_SKILL_TASK = "Follow the skill instructions on the current project state."`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_slash.py
from nexcoder.agent.core.slash import DEFAULT_SKILL_TASK, parse_slash_command

IDS = {"commit", "code-review"}


def test_known_slash_with_task():
    assert parse_slash_command("/commit fix the auth bug", IDS) == ("commit", "fix the auth bug")


def test_bare_slash_gets_default_task():
    assert parse_slash_command("/commit", IDS) == ("commit", DEFAULT_SKILL_TASK)


def test_unknown_slash_passes_through():
    assert parse_slash_command("/wat do things", IDS) == (None, "/wat do things")


def test_plain_text_passes_through():
    assert parse_slash_command("commit my changes", IDS) == (None, "commit my changes")
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement**

```python
# nexcoder/agent/core/slash.py
"""Slash-command parsing shared by the CLI and the UI bridge."""

from __future__ import annotations

DEFAULT_SKILL_TASK = "Follow the skill instructions on the current project state."


def parse_slash_command(text: str, known_ids: set[str]) -> tuple[str | None, str]:
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return None, text
    first, _, rest = stripped[1:].partition(" ")
    if first in known_ids:
        return first, rest.strip() or DEFAULT_SKILL_TASK
    return None, text
```

- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `feat(core): slash-command parser`

---

### Task 4: Skill preloading in AgentLoop + load_skill short-circuit

**Files:**
- Modify: `nexcoder/agent/core/loop.py` (`run` signature, skill message injection, run_started payload), `nexcoder/agent/core/tools/skill.py` (project_root + short-circuit)
- Test: `tests/core/test_loop_preload.py`

**Interfaces:**
- Consumes: `get_skill_body(skill_id, project_root)` (Task 1).
- Produces: `AgentLoop.run(task: str, *, preload_skill: str | None = None)`. Preloaded body arrives as message 2: `{"role": "system", "content": "[Skill: <id>]\n<body>"}`. Unknown id → `run_started` payload gains `"preload_warning": "Unknown skill: <id>"`. `ToolContext` gains attribute `preloaded_skill` (set by the loop). `load_skill` on that id returns `{"success": True, "message": "Skill already loaded in context"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_loop_preload.py
from nexcoder.agent.core.belt_factory import build_default_belt
from nexcoder.agent.core.events import AgentEvent
from nexcoder.agent.core.loop import AgentLoop
from nexcoder.agent.core.transport import XmlAdapter
from tests.core.test_skills_registry_project import make_project_skill


class RecordingModel:
    def __init__(self):
        self.received = []

    def complete(self, messages, *, extras, on_delta=None):
        self.received.append(messages)
        return {"role": "assistant", "content": "done"}


def make_loop(tmp_path, model, events=None):
    return AgentLoop(
        project_root=tmp_path, model=model, adapter=XmlAdapter(),
        belt=build_default_belt(), system_prompt="sys",
        emit=(events.append if events is not None else None))


def test_preload_injects_skill_system_message(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", body="Step 1: widgetize.")
    model = RecordingModel()
    loop = make_loop(tmp_path, model)
    loop.run("ship it", preload_skill="deploy-widget")
    first_request = model.received[0]
    assert first_request[1]["role"] == "system"
    assert "[Skill: deploy-widget]" in first_request[1]["content"]
    assert "widgetize" in first_request[1]["content"]
    assert first_request[2]["role"] == "user"


def test_preload_unknown_skill_warns_and_proceeds(tmp_path):
    events: list[AgentEvent] = []
    model = RecordingModel()
    loop = make_loop(tmp_path, model, events)
    result = loop.run("ship it", preload_skill="nope")
    assert result["status"] == "completed"
    started = next(e for e in events if e.type == "run_started")
    assert "nope" in started.payload["preload_warning"]


def test_load_skill_short_circuits_when_preloaded(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", body="B" * 500)
    call = {"role": "assistant", "content":
            '<tool_call name="load_skill">{"id": "deploy-widget"}</tool_call>'}

    class TwoTurn:
        def __init__(self):
            self.queue = [call, {"role": "assistant", "content": "ok"}]
            self.received = []

        def complete(self, messages, *, extras, on_delta=None):
            self.received.append(messages)
            return self.queue.pop(0)

    model = TwoTurn()
    loop = make_loop(tmp_path, model)
    loop.run("ship it", preload_skill="deploy-widget")
    tool_response = str(model.received[1][-1]["content"])
    assert "already loaded" in tool_response
    assert "B" * 100 not in tool_response  # body not re-sent


def test_load_skill_reads_project_skills(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", body="Widget body.")
    call = {"role": "assistant", "content":
            '<tool_call name="load_skill">{"id": "deploy-widget"}</tool_call>'}

    class TwoTurn:
        def __init__(self):
            self.queue = [call, {"role": "assistant", "content": "ok"}]
            self.received = []

        def complete(self, messages, *, extras, on_delta=None):
            self.received.append(messages)
            return self.queue.pop(0)

    model = TwoTurn()
    loop = make_loop(tmp_path, model)
    loop.run("ship it")
    tool_response = str(model.received[1][-1]["content"])
    assert "Widget body." in tool_response
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement**

`loop.py` — signature `def run(self, task: str, *, preload_skill: str | None = None) -> dict[str, Any]:`. After `conversation` is constructed (before the user task is added):

```python
        preload_warning = ""
        if preload_skill:
            from nexcoder.agent.skills_registry import get_skill_body
            record = get_skill_body(preload_skill, str(self.project_root))
            if record is None:
                preload_warning = f"Unknown skill: {preload_skill}"
            else:
                conversation.add({"role": "system",
                                  "content": f"[Skill: {preload_skill}]\n{record['body']}"})
                ctx.preloaded_skill = preload_skill
```

(`ctx` is created before the conversation; move `ToolContext` creation up if needed — it already is.) Change the `run_started` emit to:

```python
        started_payload = {"run_id": run_id, "task": task}
        if preload_warning:
            started_payload["preload_warning"] = preload_warning
        self.emit(AgentEvent("run_started", started_payload))
```

`tools/skill.py`:

```python
def load_skill(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    skill_id = str(args.get("id") or "").strip()
    if skill_id and skill_id == getattr(ctx, "preloaded_skill", None):
        return {"success": True, "message": "Skill already loaded in context"}
    record = get_skill_body(skill_id, str(ctx.project_root)) if skill_id else None
    if record is None:
        return {"success": False, "error_code": "skill_not_found",
                "error": f"Unknown skill: {skill_id}"}
    return {"success": True,
            "skill": {**record, "body": (record.get("body") or "")[:MAX_BODY]},
            "message": "Skill loaded"}
```

Also add `self.preloaded_skill: str | None = None` to `ToolContext.__init__` in `tools/base.py` (explicit beats getattr-only).

- [ ] **Step 4: Run new tests + `tests\core` suite.**
- [ ] **Step 5: Commit** — `feat(core): skill preloading in AgentLoop`

---

### Task 5: CLI wiring (--skill, slash, catalog)

**Files:**
- Modify: `nexcoder/cli.py` (`parse_args`, `run_v2`)
- Test: smoke via `--help` + existing suites (slash/catalog logic is unit-tested in Tasks 2–3)

**Interfaces:**
- Consumes: `render_skills_catalog`, `parse_slash_command`, `get_skills`.
- Produces: `--skill <id>` flag; prompts starting with `/<known-id>` route to preload.

- [ ] **Step 1: Add flag** in `parse_args`:

```python
    parser.add_argument(
        "--skill",
        default=None,
        help="Preload a skill by id for the v2 run (same as a /skill prompt prefix).",
    )
```

- [ ] **Step 2: Wire run_v2.** Add imports `render_skills_catalog` (from `nexcoder.agent.core.skills_catalog`), `parse_slash_command` (from `nexcoder.agent.core.slash`), `get_skills` (from `nexcoder.agent.skills_registry`) to the local import block. After `adapter_name` is resolved:

```python
    known_ids = {s["id"] for s in get_skills(str(project_root))}
    skill_id, task = parse_slash_command(prompt, known_ids)
    if args.skill:
        skill_id, task = args.skill, prompt
```

Change `extra_system=render_repo_map(repo_map)` to:

```python
        extra_system=(render_repo_map(repo_map) + "\n\n"
                      + render_skills_catalog(str(project_root))),
```

and `result = loop.run(prompt)` to `result = loop.run(task, preload_skill=skill_id)`.

- [ ] **Step 3: Verify** — `venv\Scripts\python.exe -m nexcoder.cli --help` shows `--skill`; `venv\Scripts\python.exe -m pytest tests -q` green.
- [ ] **Step 4: Commit** — `feat(cli): --skill flag, slash prompts, skill catalog in v2 prompt`

---

### Task 6: Bridge + worker + React UI

**Files:**
- Modify: `nexcoder/agent/agent_runtime_v2.py`, `nexcoder/bridge.py` (`agent_run_v2` slot, `get_skills`-serving slot passes project root), `nexcoder/ui/src/services/bridge.ts`, `nexcoder/ui/src/components/AIPanel/AIPanel.tsx`, `nexcoder/ui/src/components/AIPanel/SkillPicker.tsx`
- Verify: `cd nexcoder\ui; npm.cmd run build` + `python -c "import nexcoder.bridge"`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces: `AgentV2Worker(project_root, prompt, gate, full_auto=False, skill_id="")`; bridge slot `agent_run_v2(prompt: str, skill_id: str = "") -> str`; TS `agentRunV2(prompt: string, skillId = ''): Promise<any>`.

- [ ] **Step 1: Worker.** `AgentV2Worker.__init__` gains `skill_id: str = ""` (stored as `self._skill_id`). In `run()`: `extra_system=render_repo_map(repo_map) + "\n\n" + render_skills_catalog(self._project_root)` (import from `nexcoder.agent.core.skills_catalog`), and `result = loop.run(self._prompt, preload_skill=self._skill_id or None)`.

- [ ] **Step 2: Bridge.** `agent_run_v2` becomes `@Slot(str, str, result=str)` with signature `(self, prompt: str, skill_id: str = "") -> str`, passing `skill_id=skill_id` to the worker. Find the slot that serves `get_skills` to the UI (search `get_skills` in bridge.py) and pass `self._current_project_path` through to `get_skills_grouped`/`get_skills` so the picker sees project skills.

- [ ] **Step 3: bridge.ts.**

```ts
export async function agentRunV2(prompt: string, skillId = ''): Promise<any> {
  return callBridge('agent_run_v2', prompt, skillId);
}
```

- [ ] **Step 4: AIPanel.** In `handleSend`, inside the `activeMode === 'agent'` branch, before `agentRunV2`:

```ts
      const knownIds = new Set(useChatStore.getState().skills.map((s) => s.id));
      let task = userMessage.content;
      let skillId = '';
      const trimmed = task.trim();
      if (trimmed.startsWith('/')) {
        const [first, ...rest] = trimmed.slice(1).split(' ');
        if (knownIds.has(first)) {
          skillId = first;
          task = rest.join(' ').trim() || 'Follow the skill instructions on the current project state.';
        }
      }
      ...
      await agentRunV2(task, skillId);
```

(Adjust the store accessor to the actual `skills` field name in `useChatStore`; if the store keeps them elsewhere, read from where `setSkills` writes.)

- [ ] **Step 5: SkillPicker.** On selection in agent mode, set the input to `/<id> ` (prefill) instead of only recording `activeSkill` — find the selection handler and call the parent's `onChange`-equivalent with the slash prefix so the user sees and sends the command. Keep existing behavior for non-agent modes.

- [ ] **Step 6: Verify** — `venv\Scripts\python.exe -c "import nexcoder.bridge"`; `cd nexcoder\ui; npm.cmd run build` clean.
- [ ] **Step 7: Commit** — `feat(ui): slash-command skills and project skills in picker`

---

### Task 7: The six skills + retire two overlapping ones

**Files:**
- Create: `nexcoder/agent/skills/{commit,init,code-review,systematic-debugging,verification-before-completion,writing-plans}/SKILL.md`
- Delete: `nexcoder/agent/skills/code-review-and-quality/`, `nexcoder/agent/skills/debugging-and-error-recovery/`
- Modify: `nexcoder/agent/skills_registry.py` (remove the two ids from `SKILL_CATEGORY_OVERRIDES` and `SKILL_ICON_OVERRIDES`; add icons for new ids)
- Regenerate: `venv\Scripts\python.exe generate_skills.py`
- Test: `tests/core/test_builtin_skills.py`

**Interfaces:**
- Consumes: registry (Task 1).
- Produces: six loadable skill ids with frontmatter categories `quality`/`workflow`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_builtin_skills.py
from nexcoder.agent.skills_registry import get_skill_body, get_skills

NEW_IDS = {"commit", "init", "code-review", "systematic-debugging",
           "verification-before-completion", "writing-plans"}
RETIRED_IDS = {"code-review-and-quality", "debugging-and-error-recovery"}


def test_new_skills_present_with_bodies():
    ids = {s["id"] for s in get_skills()}
    assert NEW_IDS <= ids
    for skill_id in NEW_IDS:
        record = get_skill_body(skill_id)
        assert record and len(record["body"]) > 200, skill_id


def test_retired_skills_gone():
    ids = {s["id"] for s in get_skills()}
    assert not (RETIRED_IDS & ids)


def test_new_skills_have_descriptions_for_catalog():
    by_id = {s["id"]: s for s in get_skills()}
    for skill_id in NEW_IDS:
        assert len(by_id[skill_id]["description"]) > 20, skill_id
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Write the six SKILL.md files.** Each uses frontmatter `name:`, `description:`, `category:`. Full contents:

`commit/SKILL.md`:

```markdown
---
name: commit
description: Inspect staged and unstaged changes, group them logically, and write a conventional commit
category: quality
---
# Commit

Create well-formed git commits from the current working tree.

## Process
1. Run `git status` and `git diff` (and `git diff --cached`) with run_command to see every change.
2. Group related changes. If unrelated changes are mixed, commit them separately (`git add <specific files>` per group).
3. Write the message in conventional-commit form: `type(scope): summary` where type is one of feat, fix, docs, refactor, test, chore. The summary is imperative, under 72 chars. Add a body only when the why is not obvious from the diff.
4. Commit with `git commit -m "..."`. For multi-line messages, use multiple `-m` flags.
5. Confirm with `git log -1 --stat` and report the commit hash and message.

## Rules
- Never push. Never use --no-verify, --amend (unless asked), or force flags.
- Never commit secrets, .env files, or large binaries; if staged, warn and unstage them instead.
- If there are no changes, say so and stop.
```

`init/SKILL.md`:

```markdown
---
name: init
description: Scan the project and generate an AGENTS.md guide with architecture, commands, and conventions
category: workflow
---
# Init

Generate a concise AGENTS.md so agents and new developers can work in this repo.

## Process
1. Inspect the project: list_directory the root, read the README, manifest files (package.json / pyproject.toml / etc.), and one or two core source files. Use the project map if provided.
2. Identify: what the project is, the language/framework, how to build, how to run tests, how to start the app, directory layout, and any conventions visible in the code.
3. Write AGENTS.md at the project root with exactly these sections:
   - `# <Project name>` — one-paragraph purpose.
   - `## Commands` — build, test, run, lint as copy-pasteable commands.
   - `## Architecture` — key directories and what lives in each; main entry points.
   - `## Conventions` — style, naming, and patterns observed in the code.
4. Verify the file exists by reading it back.

## Rules
- Only document what you verified in files; never guess commands.
- Keep it under 100 lines. If AGENTS.md already exists, update rather than replace it.
```

`code-review/SKILL.md`:

```markdown
---
name: code-review
description: Structured severity-tagged review of the working diff or named files, citing file and line
category: quality
---
# Code Review

Review code and report findings; do not change code unless explicitly asked.

## Process
1. Determine scope: the files the user named, or `git diff` (working tree) if none.
2. Read every file in scope fully before judging any of it.
3. Check in order: correctness bugs, security issues (injection, secrets, unsafe input), error handling gaps, performance traps, then clarity/simplification.
4. Report findings grouped by severity:
   - 🔴 Critical — bugs, security holes, data loss. Must fix.
   - 🟡 Warning — error-handling gaps, risky patterns, perf problems.
   - 🔵 Info — style, naming, simplification opportunities.
5. Cite every finding as `path/to/file.py:LINE` with a one-sentence defect statement and a concrete failure scenario.
6. End with a one-paragraph verdict: is this safe to merge?

## Rules
- Verify each finding by reading surrounding code; no speculation.
- No findings is a valid result — say the code looks correct and why.
```

`systematic-debugging/SKILL.md`:

```markdown
---
name: systematic-debugging
description: Hypothesis-driven debugging - reproduce, isolate the root cause, fix, verify; never patch blind
category: quality
---
# Systematic Debugging

Find the root cause before changing any code.

## Process
1. Reproduce: run the failing command/test with run_command and read the ACTUAL error output. Never work from a paraphrase.
2. Read the error carefully: exact exception, file, line. Read that code and the code that calls it.
3. Form ONE hypothesis about the root cause. State it explicitly.
4. Test the hypothesis with evidence (read the code path, add a focused check, or run a narrower command) before editing.
5. Fix the root cause with edit_file — the smallest change that addresses the cause, not the symptom.
6. Re-run the original failing command. If still failing, the hypothesis was wrong: return to step 2 with the new output. Do not stack speculative fixes.
7. Run the broader test suite to check for regressions.

## Rules
- One hypothesis at a time. Revert speculative edits that did not help.
- If three hypotheses fail, step back and re-read the whole failing path before continuing.
```

`verification-before-completion/SKILL.md`:

```markdown
---
name: verification-before-completion
description: Run the relevant verification and read its output before claiming any work is done
category: quality
---
# Verification Before Completion

Evidence before assertions. Never claim success without running proof.

## Process
1. Identify the verification for the work just done: the test suite for code changes, the build for config changes, reading the file back for generated files, running the app for behavior changes.
2. Run it with run_command and READ the output — exit code alone is not enough.
3. If it fails: the task is not done. Fix and re-verify. Report failures honestly if you cannot fix them.
4. Only after a passing verification, summarize: what changed, what command proved it, and the relevant output line.

## Rules
- "Should work" is banned. Either you ran it and saw it pass, or the task is unfinished.
- Partial completion must be reported as partial, with what remains.
```

`writing-plans/SKILL.md`:

```markdown
---
name: writing-plans
description: Break a multi-step task into ordered, verifiable todo items before touching code
category: workflow
---
# Writing Plans

Plan before implementing anything non-trivial.

## Process
1. Restate the goal in one sentence.
2. Inspect enough of the project (glob, grep, read_file) to know which files each step touches.
3. Call todo_write with ordered steps. Each step must be:
   - Small: one coherent change.
   - Verifiable: name the command or check that proves it done.
   - Ordered: earlier steps unblock later ones.
4. Execute steps in order. Mark each in_progress when started, completed only after its verification passes. Update the list when reality diverges from the plan.
5. Finish with every item completed or explicitly reported as blocked.

## Rules
- No implementation before the todo list exists (for tasks with 3+ steps).
- Never mark an item completed without having run its verification.
```

- [ ] **Step 4: Retire the two old skills.** Delete the two directories with `git rm -r`. In `skills_registry.py`, remove `"code-review-and-quality": "quality",` and `"debugging-and-error-recovery": "quality",` from `SKILL_CATEGORY_OVERRIDES` and their entries from `SKILL_ICON_OVERRIDES`; add icon overrides: `"commit": "GitCommit", "init": "FileText", "code-review": "ClipboardCheck", "systematic-debugging": "Bug", "verification-before-completion": "CheckCircle2", "writing-plans": "ListChecks"`.

- [ ] **Step 5: Regenerate + verify** — `venv\Scripts\python.exe generate_skills.py`; run `tests\core\test_builtin_skills.py` then the full suite; `cd nexcoder\ui; npm.cmd run build`.
- [ ] **Step 6: Commit** — `feat(skills): port six Claude Code workflow skills, retire two overlaps`

---

### Task 8: Acceptance — /commit e2e + greenfield regression

**Files:**
- Create: `tests/e2e/run_commit_skill.py`
- Run: commit-skill harness + greenfield re-run (local model server required)

- [ ] **Step 1: Write the harness**

```python
# tests/e2e/run_commit_skill.py
"""Acceptance: --skill commit produces a conventional commit.

Usage: venv\\Scripts\\python.exe tests\\e2e\\run_commit_skill.py
Requires the local model server to be running.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def git(workdir, *args):
    return subprocess.run(["git", *args], cwd=workdir, capture_output=True, text=True)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="nexcoder_commit_"))
    git(workdir, "init")
    git(workdir, "config", "user.email", "e2e@nexcoder.local")
    git(workdir, "config", "user.name", "NexCoder E2E")
    (workdir / "greet.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    git(workdir, "add", "-A")
    git(workdir, "commit", "-m", "chore: seed")
    (workdir / "greet.py").write_text(
        "def greet(name='world'):\n    return f'hello {name}'\n", encoding="utf-8")
    print(f"Workdir: {workdir}")
    proc = subprocess.run(
        [sys.executable, "-m", "nexcoder.cli", "--engine", "v2", "--auto",
         "--project", str(workdir), "--skill", "commit",
         "Commit the current changes."],
        timeout=900)
    log = git(workdir, "log", "-1", "--pretty=%s").stdout.strip()
    count = git(workdir, "rev-list", "--count", "HEAD").stdout.strip()
    pattern = r"^(feat|fix|docs|refactor|test|chore)(\(.+\))?: .+"
    if proc.returncode != 0 or count != "2" or not re.match(pattern, log):
        print(f"FAIL: exit={proc.returncode}, commits={count}, message={log!r}")
        return 1
    print(f"PASS: commit message {log!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it** (model server up): `venv\Scripts\python.exe tests\e2e\run_commit_skill.py` — PASS. If the model misbehaves, tune the `commit` SKILL.md body (content tuning only; code changes go back through the owning task's tests).
- [ ] **Step 3: Greenfield regression** — `venv\Scripts\python.exe tests\e2e\run_greenfield.py` — still PASS with the catalog in the prompt.
- [ ] **Step 4: Full suite + README** — add a "Skills" paragraph to README.md documenting `/skill` syntax, `--skill`, and `.nexcoder/skills/` project skills. `venv\Scripts\python.exe -m pytest tests -q` green.
- [ ] **Step 5: Commit** — `feat: Claude Code-style skills pass acceptance`

---

## Self-Review Notes

- Spec coverage: registry/project skills (T1), catalog (T2, wired T5/T6), preload + load_skill short-circuit (T4), slash parsing (T3, wired T5/T6), six skills + retirement (T7), error handling (unknown slash T3, unknown preload T4, malformed project skill T1), acceptance (T8).
- Type consistency: `parse_slash_command(text, known_ids) -> (skill_id | None, task)` used in T5/T6; `render_skills_catalog(project_root, token_budget=800)` in T2/T5/T6; `AgentLoop.run(task, *, preload_skill=None)` in T4/T5/T6; `get_skill_body(skill_id, project_root=None)` in T1/T4.
- Note: T2's test imports `make_project_skill` from T1's test module — keep that helper module-level.
