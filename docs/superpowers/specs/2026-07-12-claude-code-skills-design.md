# NexCoder Claude Code-Style Skills — Design Spec

Date: 2026-07-12
Status: Approved design, pending implementation plan

## Goal

Give NexCoder's v2 agent Claude Code's skills mechanics: the agent discovers
and auto-invokes skills from a catalog in its prompt, projects can define
their own skills, users can trigger skills as slash commands, and six
signature Claude Code workflows ship as built-in skills.

## Decisions (from brainstorming)

- Scope: all four pillars — auto-invoking catalog in v2, six ported skills,
  project-local skills, slash commands in chat and CLI.
- Ported skills: `commit`, `init`, `code-review`, `systematic-debugging`,
  `verification-before-completion`, `writing-plans`.
- Approach A: extend the existing `skills_registry` + deterministic skill
  preloading. No allowed-tools/model-override frontmatter (YAGNI), no
  embedding-based routing.
- Existing overlapping skills `code-review-and-quality` and
  `debugging-and-error-recovery` are removed in favor of the new
  command-style ids (avoids duplicate catalog entries).

## Architecture

### Registry: project-local skills

`nexcoder/agent/skills_registry.py`:

- `_load_all_skills(project_root: str | None = None)` loads built-ins from
  `nexcoder/agent/skills/` as today, then, when `project_root` is given,
  `<project_root>/.nexcoder/skills/*/SKILL.md`. A project skill whose id
  matches a built-in replaces it.
- Project skills default to a new category `project`
  (`SkillCategory(id="project", label="Project", order=0)`) so they sort
  first in the picker and catalog.
- Public API (`get_skills`, `get_skill`, `get_skill_body`,
  `get_skills_grouped`) gains an optional `project_root` parameter, threaded
  through from the bridge (open project) and the CLI (`--project`).
- Malformed project SKILL.md files are skipped with a warning log
  (existing `_load_skill_dir` behavior).

### Catalog: auto-invoke in the v2 prompt

New module `nexcoder/agent/core/skills_catalog.py`:

- `render_skills_catalog(project_root: str | None, token_budget: int = 800) -> str`
  returns:

  ```
  # Skills
  Load a skill with load_skill when the task matches its purpose, then follow it.
  - commit — Write a conventional commit from the staged changes
  - ...
  ```

- One line per skill: `- {id} — {description[:90]}`. Project skills first,
  then built-ins alphabetically. Output truncates at `token_budget * 3`
  chars with a `[more skills omitted]` marker.
- The CLI v2 runner and `AgentV2Worker` append the catalog to the loop's
  `extra_system` (after the repo map). No `AgentLoop` change needed for
  the catalog itself.

### Preloading: deterministic slash-command execution

- `AgentLoop.run(task, *, preload_skill: str | None = None)`.
- When set, the loop resolves `get_skill_body(preload_skill, project_root=...)`
  and inserts `{"role": "system", "content": "[Skill: {id}]\n{body}"}` as the
  second message (after the system prompt) before turn 1.
- Unknown skill id: the run proceeds without it and emits a
  `tool_result`-style warning event (`{"type": "skill_preload_failed"}` is
  NOT added to the event vocabulary; reuse `run_started` payload field
  `preload_warning` instead — one less event type).
- `load_skill` on an already-preloaded id returns
  `{"success": True, "message": "Skill already loaded in context"}` without
  the body (saves tokens).

### Slash commands

Shared parser in `nexcoder/agent/core/slash.py`:

- `parse_slash_command(text: str, known_ids: set[str]) -> tuple[str | None, str]`
  — if `text` starts with `/` and the first token (minus `/`) is in
  `known_ids`, return `(skill_id, rest.strip())`; otherwise `(None, text)`.
- Empty rest → default task `"Follow the skill instructions on the current
  project state."`
- Unknown `/xyz` is NOT an error; the text passes through as a plain prompt.

Surfaces:

- **UI:** `bridge.agent_run_v2(prompt, skill_id="")` (slot gains a second
  arg). `AIPanel.handleSend` parses the input against skill ids from the
  chat store; on match calls `agentRunV2(task, skillId)`. `SkillPicker`
  selection routes the picked skill through the same path instead of only
  inserting text.
- **CLI:** `--skill <id>` flag; additionally the prompt itself is parsed for
  a leading slash command using ids from the registry.

## The six skills

Each is `nexcoder/agent/skills/<id>/SKILL.md` in the existing frontmatter
format (`name:`, `description:`, `category:`), body under ~150 lines, written
for an 8k-context model (imperative, no fluff):

| id | category | essence |
|---|---|---|
| `commit` | quality | Inspect `git status` + `git diff` via run_command; group related changes; conventional-commit message; commit. Never push, never `--no-verify`. |
| `init` | workflow | Scan repo map + key files; generate `AGENTS.md` (architecture, build/test commands, conventions). |
| `code-review` | quality | Severity-tagged review (🔴 Critical / 🟡 Warning / 🔵 Info) of working diff or named files; cite file:line; no fixes unless asked. |
| `systematic-debugging` | quality | Reproduce → read the actual error → one hypothesis → test it → fix root cause → verify. Never patch symptoms blind. |
| `verification-before-completion` | quality | Before claiming done: run the relevant verification command, read output, state the evidence. Failing = not done. |
| `writing-plans` | workflow | Break the task into ordered, independently verifiable todo_write items before touching code; keep statuses current. |

Removed: `code-review-and-quality`, `debugging-and-error-recovery`
(superseded; their category/icon override entries are cleaned up).
`generate_skills.py` is re-run to refresh the UI fallback list.

## Error handling

- Unknown slash command → plain prompt, no error.
- Unknown `preload_skill` → run proceeds; warning surfaced in `run_started`
  payload (`preload_warning`).
- Malformed project SKILL.md → skipped, logged.
- Catalog over budget → truncated with marker; never errors.

## Testing

- **Unit:** project-skill merge and override precedence; `project` category
  ordering; catalog rendering (project-first, description truncation, budget
  marker); `parse_slash_command` (known id, unknown id, bare `/commit`, no
  slash); preload injects the system message and `load_skill` short-circuits.
- **UI:** `npm run build` clean; manual: picker shows project skills, typing
  `/commit` runs a preloaded agent run.
- **Acceptance:** in a fixture repo with staged changes, CLI
  `--engine v2 --skill commit` produces a git commit whose message matches
  `^(feat|fix|docs|refactor|test|chore)(\(.+\))?: `; greenfield e2e re-run
  still passes with the catalog in the prompt (context grew ~800 tokens).

## Out of scope

- `allowed-tools` / `argument-hint` / model-override frontmatter.
- Embedding-based skill routing.
- Hooks, skill marketplaces, skill versioning.
