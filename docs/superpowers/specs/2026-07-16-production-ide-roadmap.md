# NexCoder Production IDE — Autonomous Completion Roadmap

Date: 2026-07-16
Mandate: user delegated full ownership — "finish NexCoder as a production
ready agentic coding IDE including settings, ui, chat, history, terminal,
main code editor, panels, sub-menus".

## Stages (each lands green + committed)

- **A. One engine — v2 mode profiles.** `core/profiles.py`: ask / edit /
  debug / review / scan / agent as thin profiles (system prompt + tool
  subset + turn budget) over `AgentLoop`. Read-only modes get read-only
  belts, enforced by tool absence rather than prompt hope.
- **B. All surfaces on v2.** Bridge mode routing (`agent_run_v2` gains
  `mode`; legacy per-mode slots delegate to it), AIPanel sends every mode
  through the v2 transcript UI, CLI `--mode` maps to profiles.
- **C. Auto-context.** Active file path + selection travel with the run
  and are injected into the prompt (the Cursor magic).
- **D. History that survives restarts.** Persist v2 runs per project via
  SessionStore; on project open the bridge returns recent runs and the UI
  rehydrates transcript history; ChatHistoryPanel lists them.
- **E. Settings surface.** Backend settings page (endpoint, model name,
  context window, engine defaults, full-auto), permissions allowlist
  viewer/removal, project memory viewer.
- **F. Legacy retirement.** Delete `hermes_runtime.py` + v1 runtime path,
  its bridge slots, dead UI branches and dead tests; port anything still
  referenced.
- **G. Ship.** Full suite, UI build, packaged exe rebuild + install,
  README refresh.

Terminal, Monaco editor, file explorer, git panel and bottom panels are
already functional; polish rides along in E/F rather than as rewrites.
