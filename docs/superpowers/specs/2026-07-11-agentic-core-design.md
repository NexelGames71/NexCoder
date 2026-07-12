# NexCoder Agentic Core — Design Spec

Date: 2026-07-11
Status: Approved design, pending implementation plan

## Goal

Upgrade NexCoder's agent from an approval-gated, XML-only, 16-turn loop into a
true agentic coding agent comparable to Cursor / Claude Code / Codex: it plans,
edits files directly, runs commands (with permission), verifies its own work,
and keeps going until the task is done.

## Decisions (from brainstorming)

- **Model strategy:** Build against the local Qwen2.5-Coder-7B GGUF server now;
  support clean migration to the team's own GPU-hosted model later. Both are
  OpenAI-compatible endpoints, so migration is a backend-config change only.
- **Surface:** Desktop app (Cursor-style) first. The CLI remains a thin harness
  over the same runtime.
- **Autonomy:** Auto-edit + gated commands. File edits apply immediately with
  checkpoint-backed revert; terminal commands prompt for permission with a
  per-project allowlist. An off-by-default "Full auto" session toggle skips
  command prompts.
- **Scope:** All four pillars — core loop rebuild, codebase intelligence,
  planning/task tracking, context management.
- **Approach:** New core `AgentLoop` (Approach B), not evolving
  `hermes_runtime.py` in place and not adopting an OSS framework.
- **Acceptance:** Two end-to-end scenarios must pass against the local model:
  greenfield build and brownfield bug fix (see Testing).

## Architecture

New package `nexcoder/agent/core/`:

```
core/
  loop.py          AgentLoop — the single agentic loop, mode-agnostic
  transport.py     ToolCallAdapter protocol + XmlAdapter + NativeAdapter
  conversation.py  Message history, token budgeting, compaction
  tools/           One module per tool (read, edit, write, glob, grep, ls,
                   mkdir/move, run_command, todo, load_skill)
  events.py        Typed event stream (tool_started, tool_result, text_delta,
                   todo_updated, edit_applied, permission_request, ...)
```

### Data flow

1. UI (QWebChannel bridge) or CLI sends a task to `AgentLoop`.
2. Loop builds the system prompt from a mode profile + repo map.
3. `ModelConnector` (extended) sends the conversation; when the adapter is
   native it passes the OpenAI `tools` parameter.
4. The `ToolCallAdapter` extracts tool calls — `XmlAdapter` parses
   `<tool_call>` blocks from text (local 7B path); `NativeAdapter` reads
   `message.tool_calls` (GPU-server path).
5. Tools execute through the existing `ToolRegistry` with the existing
   guardrail controller (repeat-call and no-progress detection).
6. Results are appended to the conversation; loop repeats until the model
   produces a final answer or a guardrail stops it.

Every step emits a typed event. The QWebChannel bridge forwards events to the
React UI; the CLI renders the same events as text. There is one event
vocabulary for both surfaces.

### Backend config / migration seam

```json
{ "base_url": "...", "model": "...", "api_key": "...",
  "adapter": "xml" | "native", "context_window": 8192 }
```

Local Qwen today: `adapter=xml`, `context_window=8192`. Future GPU server:
`adapter=native`, larger window. Nothing else in the loop changes.

### Turn budget and stopping

Turn budget rises to ~50. The guardrail controller is the real stop mechanism:
repeated identical calls, repeated failures, and no-progress sequences warn
then hard-stop. The turn cap is a backstop, not the design.

### Retirement path for hermes_runtime.py

The old runtime keeps serving all modes until the new loop passes acceptance
in agent mode. Then ask / edit / debug / review / scan become thin mode
profiles over the new loop, and `hermes_runtime.py` is deleted. Reused as-is
or lightly adapted: `ToolRegistry`, `CheckpointManager`, `tool_guardrails`,
`trajectory`, `path_filters`, `SafetyChecker`, `session.py`, `mode_profiles`
(simplified).

## Tool belt

Each tool is a small module exposing a JSON schema. The native adapter sends
the schemas as OpenAI function definitions; the XML adapter renders them into
the system prompt.

| Tool | Behavior |
|---|---|
| `read_file` | Line-numbered output; offset/limit for large files |
| `edit_file` | **New.** Exact search/replace on file content. Fails loudly if the search string is absent or matches more than once. Primary edit tool. |
| `write_file` | Create new files or full overwrites only |
| `glob` | **New.** Pattern-based file finding, sorted by recency |
| `grep` | Regex content search with glob filters, context lines, result caps |
| `list_directory` | Kept from existing registry |
| `create_directory` / `move_path` | Kept from existing registry |
| `run_command` | Streams stdout/stderr as events; timeout; cwd = project root |
| `todo_write` | **New.** Agent-maintained task list; UI renders it live |
| `load_skill` | Kept from existing registry |

## Autonomy and permissions

- `edit_file` / `write_file` / `create_directory` execute immediately — no
  approval gate. Before the first mutation of a run, `CheckpointManager`
  snapshots touched files. The UI offers per-file "Revert" and whole-run
  "Revert all". Files open in Monaco refresh live with change highlights.
- `run_command` prompts via a UI permission request event. A per-project
  allowlist ("always allow `npm test`") is stored in
  `.nexcoder/permissions.json`. Dangerous patterns (existing `SafetyChecker`:
  `rm -rf`, force-push, etc.) always prompt, allowlist or not.
- "Full auto" toggle (settings, off by default) skips command prompts for the
  session. Dangerous-pattern prompts still fire.
- Self-verification is prompt-driven: agent mode's system prompt requires
  running a verification command after edits, reading failures, and fixing
  them before finishing. Guardrails prevent infinite fix loops.

## Codebase intelligence

On project open and after each agent run, a background job builds a repo map:

- Directory tree filtered by existing `path_filters`.
- Per-file top-level symbols for source files — Python via `ast`, TS/JS via
  regex. No heavy indexer or embeddings in v1.
- Stored at `.nexcoder/repo_map.json`; injected into the agent system prompt
  trimmed to a token budget (~1.5k tokens for the local backend, more for the
  GPU server).

## Planning and task tracking

- The agent-mode system prompt instructs the model to call `todo_write` first
  on non-trivial tasks and keep statuses current.
- The React panel renders the checklist live from `todo_updated` events.
- No separate plan-then-approve gate in v1; auto-edit + checkpoints covers the
  risk. Can be added later if needed.

## Context management

`conversation.py` owns the message list with per-message token accounting
(estimator now; real tokenizer counts when the backend reports usage).

When usage crosses ~75% of the backend context window, compact:

1. Old tool results collapse to one-line summaries ("read app.py — 250 lines").
2. If still over budget, the oldest turns are summarized by a single model
   call into a running task summary message.
3. The system prompt, todo state, and the most recent turns always survive.

Sessions persist to `.nexcoder/sessions/` (extending existing `session.py`)
so a crashed app can resume a run's transcript.

## Error handling

- Malformed tool call → structured error result fed back to the model;
  bounded retries via guardrails.
- Model connection drop mid-run → run pauses; UI offers resume.
- Tool exceptions never kill the loop; they become error observations.
- Command timeout → process killed, timeout reported as the observation.
- Every run writes a JSONL trajectory (existing `trajectory.py`).

## Testing

**Unit:** adapter equivalence (XML and native fixtures parse into identical
`ToolCall` objects); `edit_file` edge cases (no match, multiple matches, CRLF,
unicode); compaction (budget respected, protected messages survive).

**Integration:** `AgentLoop` against a scripted fake model connector —
multi-turn tool sequences, guardrail stops, permission flow, checkpoint/revert.

**Acceptance (definition of done):** via `nexcoder.cli` against the local
Qwen model:

1. **Greenfield:** empty folder, "build a responsive product page with
   HTML/CSS/JS" — agent plans (todo list), creates all files, verifies, and
   finishes without babysitting.
2. **Brownfield:** fixture repo with a seeded failing test, "this test is
   failing, fix it" — agent locates the cause, edits precisely with
   `edit_file`, re-runs the test until green.

## Out of scope (v1)

- Embeddings / semantic search indexing.
- Sub-agents and parallel tool execution.
- Plan-then-approve mode.
- Web search / browser tools.
- Multi-provider billing or cloud account features.
