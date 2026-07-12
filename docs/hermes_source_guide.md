# Hermes Agent Source Guide for NexCoder

This note records the Hermes Agent patterns that are useful for NexCoder. Use it
as a source guide, not as a direct copy target. NexCoder should keep its own
desktop/editor architecture and port only the pieces that improve agent quality.

## Source Reference

Hermes source path:

`C:\Users\sdami\Downloads\hermes-agent-main (1)\hermes-agent-main`

Important files inspected:

- `run_agent.py` - main agent loop, provider handling, tool call dispatch, retry and state handling.
- `agent/tool_guardrails.py` - repeated tool call and no-progress guardrails.
- `agent/tool_dispatch_helpers.py` - safe parallelism rules and file mutation tracking helpers.
- `agent/trajectory.py` - durable JSONL trajectory capture.
- `toolsets.py` - composable tool bundles for modes such as file, browser, terminal, memory, and project work.
- `README.md` - product-level agent capabilities and cross-platform workflow model.

## Patterns to Port

### 1. Toolsets

Hermes groups tools into named toolsets instead of giving every mode every tool.
NexCoder should use the same idea for:

- `ask`: read-only project tools only.
- `scan`: deterministic scanner tools only.
- `edit`: read, patch proposal, and validation tools.
- `agent`: read, patch, terminal, tests, and approval-aware write tools.
- `debug`: read, terminal, error parser, patch proposal, and test tools.

This keeps model behavior tighter and makes the UI more honest about what the
agent is allowed to do.

### 2. Tool Loop Guardrails

Hermes tracks repeated exact tool calls, repeated failures, and no-progress
idempotent tools. NexCoder already blocks repeated identical tool calls in its
agent runtime, but it should grow this into a reusable guardrail controller with:

- stable tool name plus canonical args signatures,
- warning thresholds,
- hard-stop thresholds,
- separate handling for read-only and mutating tools,
- structured timeline entries when a call is skipped or blocked.

### 3. Durable Trajectories

Hermes writes trajectories for completed and failed runs. NexCoder should store
compact project-local agent traces under `.nexcoder/`:

- user task,
- model turns,
- parsed tool calls,
- tool observations,
- patch proposals,
- approvals,
- verification results,
- final answer.

These traces can power session replay, debugging, and future local fine-tuning.

### 4. File Mutation Tracking

Hermes extracts file mutation targets from write and patch tools so final
verification can prove what changed. NexCoder should use this for:

- Apply/Reject UI confidence,
- automatic changed-file summaries,
- checkpoint labels,
- required post-edit validation.

### 5. Parallelism Rules

Hermes only parallelizes safe read-only or non-overlapping path-scoped tools.
NexCoder can use this later to make scans and read-heavy agent tasks faster
without risking write conflicts.

## What Not to Port Directly

- Hermes' large multi-provider CLI/gateway stack is not a fit for NexCoder's
  current PySide6 desktop app.
- Messaging gateway logic belongs outside the MVP editor loop.
- Cloud/provider billing and portal-specific logic should not be mixed into the
  local NexCoder agent runtime.

## Near-Term NexCoder Tasks

1. Add first-class `Toolset` definitions for each NexCoder mode.
2. Extract repeated-call detection into a reusable guardrail module.
3. Save compact JSONL trajectories for every agent task.
4. Add mutation-target tracking for patch proposals.
5. Add a project-map fast-answer path for common follow-up questions after scan.
