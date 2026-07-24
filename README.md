# NexCoder

NexCoder is an AI-first coding workspace from Nexa Labs. It helps you open a
project, understand the codebase, ask questions, fix bugs, make edits, run
commands, review changes, and work with images or project files from one
desktop app.

NexCoder is built for people who want an assistant that can do more than chat.
It can inspect your project, read the active file, see selected code, understand
open problems, edit files, run tests, and explain what changed.

## What you can do with NexCoder

- Open a local folder and browse your project files.
- Edit code with Monaco, the same editor engine used by VS Code.
- Ask NexCoder questions about your codebase.
- Let the agent fix bugs or implement features.
- Use Plan mode to review an implementation plan before code changes happen.
- Use Agent Mesh for larger tasks that benefit from exploration,
  implementation, testing, and review steps.
- See project problems and diagnostics in the Problems panel.
- Open images, audio, video, PDFs, fonts, and other files without corrupting
  them as text.
- Upload images to supported vision models so the AI can analyze screenshots,
  UI issues, rendering bugs, or visual problems.
- Run project commands in the integrated terminal.
- Revert AI-made file changes when needed.
- Switch between configured AI models when one is slow, unavailable, or
  rate-limited.

## Quick start

1. Launch NexCoder.
2. Choose **Open Folder**.
3. Select the project you want to work on.
4. Open a file or ask NexCoder to scan the project.
5. Type a task in the AI panel.

Example prompts:

```text
Scan this project and explain how it works.
```

```text
Fix the errors shown in the Problems panel.
```

```text
Review the authentication code for security issues.
```

```text
Use this screenshot to diagnose why the UI is misaligned.
```

## AI modes

NexCoder includes several modes so you can choose how much control the AI has.

| Mode | Best for | Can edit files? |
|---|---|---:|
| Ask | Explanations, architecture questions, code understanding | No |
| Agent | Multi-step coding tasks, fixes, feature work | Yes |
| Edit | Focused changes to selected code or active files | Yes |
| Debug | Reproducing and fixing errors | Yes |
| Review | Code review and risk analysis | No |
| Scan | Mapping a new project | No |
| Plan | Creating a reviewable implementation plan | No, until approved |
| Terminal | Build/test/tooling tasks | Can run commands |

Read-only modes are intentionally limited. If you choose Ask, Review, Scan, or
Plan, NexCoder should inspect and explain without changing your files.

## Working with the agent

When you run the agent, NexCoder can:

1. Read relevant files.
2. Search the codebase.
3. Create a short task list.
4. Edit files.
5. Run safe commands or ask for approval.
6. Use diagnostics from the Problems panel.
7. Summarize what changed.
8. Let you revert changes if needed.

For best results, be specific:

```text
Fix the TypeScript errors in the Problems panel and run the frontend build.
```

```text
In main.py, make the settings button open the agent settings page.
```

```text
Use the attached screenshot to identify the rendering issue, then fix the
smallest likely cause.
```

## Model selection

NexCoder can use OpenAI-compatible model providers, including Nexa-hosted
models, NVIDIA-hosted models, local GGUF servers, or other compatible APIs.

Use the model selector in the composer to switch models. This is useful when:

- A model is too slow.
- A model returns HTTP 429 rate-limit or capacity errors.
- A text-only model cannot analyze an image.
- You want a faster model for small edits.
- You want a stronger model for large agent tasks.

If you upload an image, choose a model that supports vision. Text-only models
will reject image input.

## Images and file previews

NexCoder can preview common project files directly in the editor.

Supported preview categories include:

- Images: PNG, JPG, JPEG, GIF, WebP, SVG, ICO, BMP, TIFF, HEIC/HEIF where
  supported by the runtime.
- Audio: MP3, WAV, OGG, M4A, AAC, OPUS, MIDI.
- Video: MP4, WebM, MOV, MKV, AVI, M4V.
- Documents: PDF.
- Fonts: preview samples.
- Unknown binary files: safe metadata preview.

Binary files are not opened as plain text. This helps prevent corrupted output
when opening media, archives, executables, or generated assets.

## Problems panel

The Problems panel shows diagnostics reported by the project language tools.
These can include errors, warnings, and hints.

You can use it in two ways:

- Click a problem to jump to the relevant file.
- Ask the agent to fix the visible problems.

Example:

```text
Fix the current Problems panel errors, then run the right validation command.
```

The agent receives the problem count and problem details as context, so it does
not need you to manually copy every error message.

## Agent Mesh

Agent Mesh is for larger tasks. Instead of treating a big request as one long
chat turn, NexCoder can split the goal into coordinated work units such as:

- exploration
- implementation
- testing
- review

Use Agent Mesh when the task is broad, risky, or likely to need multiple passes.

Example:

```text
Upgrade this game project, verify the executable exists, and do not report
success until the build output is confirmed.
```

Agent Mesh can still fail or complete with issues. Always read the final report
and verify important results.

## Plan mode

Plan mode is for controlled work. NexCoder inspects the project and writes an
implementation plan first. You can review it before allowing code changes.

Use Plan mode when:

- The task is large.
- The change touches many files.
- You want to approve the approach before implementation.
- You need a clear definition of done.

The plan should explain:

- what NexCoder found
- what files will change
- the implementation phases
- validation steps
- risks
- what counts as complete

## Reverting AI changes

NexCoder creates checkpoints around AI-made edits so you can recover from bad
changes.

You can revert:

- a whole run
- a single changed file
- changes made after a specific prompt when editing and resending that prompt

Prompt edit/resend is designed to keep earlier work intact while removing later
conversation turns and file changes caused by the edited prompt.

## Terminal

The integrated terminal lets you run project commands without leaving NexCoder.

Common uses:

```powershell
python main.py
```

```powershell
npm.cmd run build
```

```powershell
python -m pytest
```

On Windows, prefer `npm.cmd` instead of `npm` if PowerShell blocks npm scripts.

## Privacy and safety

NexCoder is designed to keep project work under your control.

- API keys should be stored in your local environment file, not pasted into
  chat.
- Read-only modes should not edit files.
- AI file changes are checkpointed for rollback.
- Commands may require approval depending on your settings.
- Uploaded images are sent to the selected model only when you include them in
  the prompt.
- Project memory and chat history may contain sensitive details, so do not put
  secrets in prompts or memory.

If you are using a hosted model, the model provider receives the prompt context
needed for the request. Use local or trusted endpoints for sensitive projects.

## Troubleshooting

### The model returns HTTP 429

HTTP 429 usually means the provider accepted your key but is rate-limiting you
or has no capacity for that model right now.

Try:

- switch to another model
- wait and retry
- reduce the prompt size
- use a faster/smaller model
- use a higher-quota endpoint

### The model rejects an image

The selected model is probably text-only. Switch to a vision-capable model and
send the image again.

### The agent is slow

Large reasoning models can be slow, especially with long prompts or big
projects. Try a faster model for small edits and reserve large models for deep
tasks.

### The agent keeps reading the codebase again

This can happen when:

- the project is new
- there is no saved project memory yet
- the task is broad
- context was compacted
- the active file or selection is unclear

Give the agent a specific file, error, screenshot, or goal to reduce repeated
exploration.

### The terminal stops or is interrupted

Start a new terminal from the terminal controls. If it keeps happening, restart
NexCoder and reopen the project.

### A file does not preview

Some media formats depend on what the embedded browser runtime supports. If a
file cannot be previewed, NexCoder should still show a safe binary preview
instead of corrupting it as text.

## More documentation

For a complete user guide, see [`docs/user-guide.md`](docs/user-guide.md).

## License

Proprietary. NexCoder is part of the Nexa Labs product ecosystem.
