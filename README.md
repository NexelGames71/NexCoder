# NexCoder

NexCoder is a PySide6 desktop code editor for the Nexa ecosystem. It embeds a React, TypeScript, and Monaco frontend in `QWebEngineView`, with Python services exposed through `QWebChannel`.

## Development

```powershell
python -m venv venv
venv\Scripts\pip.exe install -r requirements.txt
venv\Scripts\pip.exe install -r requirements-gpu.txt
cd nexcoder\ui
npm.cmd install
npm.cmd run build
cd ..\..
venv\Scripts\python.exe -m nexcoder.main
```

## Build

```powershell
venv\Scripts\python.exe build.py
```

The packaged app is written to `dist\NexCoder`.

## Local Qwen3-Coder-30B-A3B GGUF Model (recommended)

The MoE 30B (3B active) model is markedly more reliable for agent mode than
the 7B and runs on 32GB RAM + a consumer GPU via partial offload:

```powershell
cd models
.\start_qwen3_coder.bat
```

Then point the agent at a matching context budget:

```powershell
$env:NEXA_CONTEXT_WINDOW = "16384"
```

Tuning: `NEXCODER_GGUF_GPU_LAYERS` (default 14 — raise with more VRAM,
lower on CUDA OOM), `NEXCODER_GGUF_CTX` (default 16384).

## Local Qwen2.5-Coder GGUF Model

NexCoder can use the bundled `Qwen2.5-Coder-7B-Instruct` GGUF model through the local OpenAI-compatible server in `models/server.py`.

```powershell
cd models
..\venv\Scripts\pip.exe install -r ..\requirements-gpu.txt
.\start_api.bat
```

If the Hugging Face repo contains multiple `.gguf` files, start the server with `--model-path` pointing to the exact `.gguf` file you want.

```powershell
$env:NEXCODER_REQUIRE_GPU = "1"
$env:NEXCODER_GGUF_GPU_LAYERS = "-1"
C:\NexCoder\venv\Scripts\python.exe C:\NexCoder\models\server.py --port 8001 --model-path C:\NexCoder\models\coder\Qwen2.5-Coder-7B-Instruct-GGUF\qwen2.5-coder-7b-instruct-q6_k.gguf
```
## CLI Agent (v2 agentic core)

The v2 engine is a Cursor-class agentic loop: it plans with a visible todo
list, edits files directly (checkpoint-backed revert), asks permission before
running commands, and verifies its own work.

```powershell
# Interactive (prompts before each command; [a]lways adds to the allowlist)
C:\NexCoder\venv\Scripts\python.exe -m nexcoder.cli --engine v2 --project C:\MyApp "fix the failing test"

# Full auto (no command prompts; risky commands still denied)
C:\NexCoder\venv\Scripts\python.exe -m nexcoder.cli --engine v2 --auto --project C:\MyApp "build a landing page"
```

Configuration (env vars, also read from `.env`):

| Variable | Default | Purpose |
|---|---|---|
| `NEXA_API_URL` | `http://127.0.0.1:8001` | OpenAI-compatible backend |
| `NEXA_MODEL` | `default` | Model name sent to the backend |
| `NEXCODER_ADAPTER` | `xml` | Tool-call transport: `xml` (local GGUF) or `native` (OpenAI function calling) |
| `NEXA_CONTEXT_WINDOW` | `8192` | Context budget for compaction |
| `NEXCODER_ENGINE` | `v2` | Default CLI engine (`v1` = legacy Hermes loop) |

**GPU-server migration:** point `NEXA_API_URL` at the hosted endpoint and set
`NEXCODER_ADAPTER=native`. Nothing else changes.

Per-project state lives in `.nexcoder/`: `permissions.json` (command
allowlist), `checkpoints/` (revert snapshots), `repo_map.json`, `sessions/`,
`trajectories/`, and `skills/` (project-local skills).

### Skills

The v2 agent sees a catalog of all skills in its prompt and loads relevant
ones itself via `load_skill`. You can also invoke a skill directly:

```powershell
# Slash prefix in the prompt (chat panel or CLI)
... -m nexcoder.cli "/commit group and commit my changes"

# Or the explicit flag
... -m nexcoder.cli --skill code-review "review the auth module"
```

Built-in workflow skills include `commit`, `init`, `code-review`,
`systematic-debugging`, `verification-before-completion`, and
`writing-plans`. Projects can add or override skills by creating
`.nexcoder/skills/<id>/SKILL.md` with `name:` and `description:`
frontmatter — they appear in the picker under "Project" and take
precedence over built-ins with the same id.

Acceptance harnesses (require the local model server):

```powershell
venv\Scripts\python.exe tests\e2e\run_greenfield.py
venv\Scripts\python.exe tests\e2e\run_brownfield.py
```

## CLI Agent (legacy v1)

Run NexCoder's Hermes-style coding agent directly in a terminal:

```powershell
C:\NexCoder\venv\Scripts\python.exe -m nexcoder.cli --project C:\NexCoder "scan the project and create a codebase map"
```

Useful options:

```powershell
# Run agent mode and show tool steps / patch previews
C:\NexCoder\venv\Scripts\python.exe -m nexcoder.cli --project C:\Spinner "build a single-file spinner page"

# Emit machine-readable events
C:\NexCoder\venv\Scripts\python.exe -m nexcoder.cli --jsonl --project C:\Spinner "scan the project"

# Apply prepared full-file patches after a successful run
C:\NexCoder\venv\Scripts\python.exe -m nexcoder.cli --apply --project C:\Spinner "update index.html"
```

By default, `write_file` prepares patch previews and does not write them to disk. Use `--apply` only when you want the CLI to write the prepared patch payloads.

Create a polished responsive static product page. Create index.html, styles.css, script.js, and README.md. Use plain HTML, CSS, and JavaScript only. Include a dark visual system, responsive navigation, three product cards, accessible controls, and a working theme toggle. Do not install packages. Complete every requested file in this run and prepare all changes for review.
