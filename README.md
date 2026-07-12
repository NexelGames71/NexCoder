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
## CLI Agent

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
