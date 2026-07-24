# Using NexCoder's model as an OpenAI-compatible API

`models/server.py` speaks the OpenAI API (`/v1/chat/completions`,
`/v1/models`), so any tool that supports a custom OpenAI base URL can use
your local Qwen3-Coder-30B.

## Start the server

Localhost only (same machine):

```powershell
models\start_qwen3_coder.bat        # http://127.0.0.1:8002/v1
```

Reachable from other machines / tunnels:

```powershell
models\start_api_public.bat         # binds 0.0.0.0, prints your LAN IP
```

**Secure it before exposing** beyond your own machine — set an API key,
then clients must send `Authorization: Bearer <key>`:

```powershell
$env:NEXCODER_API_KEY = "choose-a-long-random-string"
models\start_api_public.bat
```

Quick check:

```powershell
curl http://127.0.0.1:8002/v1/models
```

The `id` it returns (`qwen3-coder-30b-a3b-instruct-q4_k_m`) is the model
name to use in clients. The server ignores the requested model name and
always uses the one it loaded, so any name also works.

## Tools that connect directly to localhost (easiest)

These send requests straight from your machine, so `http://127.0.0.1:8002/v1`
works with no tunnel:

| Tool | Where to set it |
|---|---|
| **Continue.dev** (VS Code/JetBrains) | `~/.continue/config.json` → a model with `"provider": "openai"`, `"apiBase": "http://127.0.0.1:8002/v1"`, `"model": "qwen3-coder-30b-a3b-instruct-q4_k_m"` |
| **Cline / Roo Code** (VS Code) | Provider: "OpenAI Compatible", Base URL `http://127.0.0.1:8002/v1`, any API key |
| **aider** (CLI) | `setx OPENAI_API_BASE http://127.0.0.1:8002/v1` then `aider --model qwen3-coder-30b-a3b-instruct-q4_k_m` |
| **Zed** | Assistant settings → OpenAI-compatible provider with the same base URL |

For all of these, if you set `NEXCODER_API_KEY`, use it as the API key;
otherwise any non-empty string is accepted.

## Cursor (needs a public tunnel)

Cursor routes model requests through **Cursor's own servers**, so it
cannot reach `localhost` directly — you must expose the server with a
tunnel first.

1. Start the server (ideally with `NEXCODER_API_KEY` set).
2. Open a public tunnel, e.g. with cloudflared:
   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8002
   ```
   (or `ngrok http 8002`). Copy the `https://...` URL it prints.
3. In Cursor: **Settings → Models**
   - Turn on **Override OpenAI Base URL** and set it to
     `https://<your-tunnel>/v1`.
   - Set the **OpenAI API key** to your `NEXCODER_API_KEY` (or any string
     if you didn't set one).
   - Add a custom model named `qwen3-coder-30b-a3b-instruct-q4_k_m` and
     enable it; disable the built-in models so Cursor uses yours.
   - Click **Verify**.

Caveats with Cursor specifically: its Tab/autocomplete and some Agent
features are hard-wired to Cursor's own models and will not use a custom
endpoint — only the chat/compose model does. Latency also includes the
round trip through Cursor's servers and your tunnel. If you want a fully
local, direct experience, Continue.dev or Cline above are the better fit.

## Migrating to your GPU server later

When the team's GPU-hosted model is live, point clients at its URL instead
— it is the same OpenAI API. NexCoder's own agent switches with
`NEXA_API_URL` + `NEXCODER_ADAPTER=native`; external tools just change
their base URL.
