# NexCoder

NexCoder is a production-grade agentic coding IDE for the Nexa ecosystem: a
PySide6 desktop app embedding a React + TypeScript + Monaco frontend in
`QWebEngineView`, with Python services exposed through `QWebChannel`.

One engine powers everything. Every AI surface — the chat panel's Agent,
Ask, Edit, Debug, Review, and Scan modes, and the terminal CLI — is a thin
policy profile (system prompt + tool subset + turn budget) over the same
v2 agentic core (`nexcoder/agent/core/`).

## Highlights

- **Agentic loop** — plans with a visible todo list, edits files directly
  (checkpoint-backed revert per run or per file), asks permission before
  running commands, verifies its own work, records trajectories.
- **Structural safety** — read-only modes (Ask/Review/Scan) simply do not
  receive mutating tools; permission gates + per-project command allowlist
  guard the rest. Full-auto mode still denies risky commands.
- **Auto-context** — the active editor file and text selection travel with
  every run ("fix this" means the selected code).
- **Persistent chat history** — every run appends to a per-project session
  (`.nexcoder/sessions/`); follow-up prompts replay recent conversation;
  history survives restarts and is browsable in the Chats sidebar.
- **Skills** — a Claude-Code-style skill catalog (commit, code-review,
  systematic-debugging, …) the agent loads on demand; invoke directly with
  `/skill-id` or `--skill`. Projects add their own under
  `.nexcoder/skills/<id>/SKILL.md`.
- **Context management** — token budgeting, two-stage compaction, and a
  hard force-fit guarantee before every model call; live context meter in
  the composer.
- **Local-first** — runs fully offline against a local GGUF model server;
  switching to a hosted GPU endpoint is config-only.

## Development

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements-gpu.txt
cd nexcoder\ui
npm.cmd install
npm.cmd run build
cd ..\..
venv\Scripts\python.exe -m nexcoder.main
```

Tests:

```powershell
venv\Scripts\python.exe -m pytest tests -q
```

## Build (packaged exe)

```powershell
venv\Scripts\python.exe build.py
```

The packaged app is written to `dist\NexCoder`. The frozen exe reads `.env`
from its own directory.

## Local model (Qwen3-Coder-30B-A3B GGUF, recommended)

Models and the serving stack live centrally in `C:\Nexa` (see
`C:\Nexa\GGUF_SERVING.md`). The MoE 30B (3B active) runs on 32GB RAM + a
consumer GPU by housing the KV cache in system RAM:

```powershell
C:\Nexa\start_gguf.bat            # default: Qwen3-Coder-30B at :8002
```

Tuning env vars: `NEXCODER_GGUF_GPU_LAYERS` (raise with more VRAM, lower on
OOM), `NEXCODER_GGUF_CTX` (server context), `NEXCODER_GGUF_KV_OFFLOAD=0`
(KV in RAM). The server is OpenAI-compatible, so other coding agents
(Cursor, etc.) can use it too — `start_tunnel.bat` exposes it via
cloudflared (set `NEXCODER_API_KEY` first).

## CLI agent

```powershell
# Interactive (prompts before each command; [a]lways adds to the allowlist)
venv\Scripts\python.exe -m nexcoder.cli --project C:\MyApp "fix the failing test"

# Full auto (no command prompts; risky commands still denied)
venv\Scripts\python.exe -m nexcoder.cli --auto --project C:\MyApp "build a landing page"

# Mode profiles (agent | ask | edit | debug | review | scan)
venv\Scripts\python.exe -m nexcoder.cli --mode review --project C:\MyApp "review the auth module"

# Skills
venv\Scripts\python.exe -m nexcoder.cli "/commit group and commit my changes"
venv\Scripts\python.exe -m nexcoder.cli --skill code-review "review the auth module"

# Machine-readable events
venv\Scripts\python.exe -m nexcoder.cli --jsonl --project C:\MyApp "scan the project"
```

## Configuration

Env vars (also read from `.env` next to the repo root or the frozen exe):

| Variable | Default | Purpose |
|---|---|---|
| `NEXA_API_URL` | `http://127.0.0.1:8002` | OpenAI-compatible backend |
| `NEXA_MODEL` | `default` | Model name sent to the backend |
| `NEXCODER_ADAPTER` | `xml` | Tool-call transport: `xml` (local GGUF) or `native` (OpenAI function calling) |
| `NEXA_CONTEXT_WINDOW` | `32768` | Context budget for compaction |

All of these are also editable live in the app under Agent Settings
(`Ctrl+Shift+,`), alongside the per-project command allowlist and the
project memory the agent injects into every run.

**GPU-server migration:** point `NEXA_API_URL` at the hosted endpoint and
set `NEXCODER_ADAPTER=native`. Nothing else changes.

## Per-project state (`.nexcoder/`)

| Path | Contents |
|---|---|
| `sessions/` | Chat history (index + JSONL messages per session) |
| `checkpoints/` | Revert snapshots taken before every mutation |
| `permissions.json` | Always-allowed commands |
| `MEMORY.md` | Durable project memory (agent `remember` tool) |
| `repo_map.json` | Cached repository map |
| `trajectories/` | Compact JSONL run traces |
| `skills/` | Project-local skills (override built-ins by id) |

## Acceptance harnesses

Require the local model server:

```powershell
venv\Scripts\python.exe tests\e2e\run_greenfield.py
venv\Scripts\python.exe tests\e2e\run_brownfield.py
```
