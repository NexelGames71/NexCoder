# NexCoder User Guide

NexCoder is an AI-first code editor for working on real projects with an AI
assistant built into the workspace. It is designed to help you understand a
codebase, make changes, fix errors, review code, run commands, preview project
files, and work with screenshots or images when the selected model supports
vision.

This guide is written for NexCoder users. It does not assume you are developing
NexCoder itself.

## 1. Getting started

### Open a project

1. Launch NexCoder.
2. Click **Open Folder**.
3. Select your project folder.
4. Wait for the file tree to load.
5. Open files from the sidebar or ask the AI to scan the project.

NexCoder works best when you open the root folder of the project, not a nested
subfolder. For example, open the folder that contains `package.json`,
`pyproject.toml`, `requirements.txt`, `.git`, or the main source directory.

### First useful prompt

If you are opening a project for the first time, start with:

```text
Scan this project and explain the structure, how to run it, and what files are
most important.
```

This helps NexCoder build context before you ask it to make changes.

## 2. Workspace overview

NexCoder is organized into several main areas:

| Area | What it does |
|---|---|
| File sidebar | Browse folders and files. |
| Editor | Edit source files and preview supported media files. |
| AI panel | Ask questions, run the agent, upload images, switch models, and steer tasks. |
| Bottom panel | View Problems, Output, Terminal, and Git Diff. |
| Top bar | Search, settings, project controls, and account controls. |
| Agent Mesh panel | Run larger multi-step agent workflows. |

## 3. AI panel

The AI panel is where you talk to NexCoder.

You can:

- ask questions
- run coding tasks
- upload screenshots or images
- choose the AI mode
- choose the model
- stop an active run
- queue follow-up prompts while the agent is working
- edit and resend previous prompts
- revert AI-made changes

### Prompt tips

Good prompts include the goal and the expected validation.

Better:

```text
Fix the TypeScript errors in the Problems panel and run npm.cmd run build.
```

Less useful:

```text
Fix it.
```

Better:

```text
The attached screenshot shows the world rendering as a tiny corner. Analyze the
image, inspect the renderer, fix the likely camera or mesh issue, then run the
game to verify it launches.
```

Less useful:

```text
Why does it look wrong?
```

## 4. AI modes

NexCoder has different modes for different levels of control.

### Ask

Use Ask when you want explanations.

Examples:

```text
What does this file do?
```

```text
Explain how authentication works in this project.
```

Ask mode should not edit files.

### Agent

Use Agent for normal coding work.

Examples:

```text
Add a settings page and wire the settings button to open it.
```

```text
Fix the failing tests and summarize the files changed.
```

Agent mode can read, edit, run commands, and verify work.

### Edit

Use Edit for smaller, focused changes.

Examples:

```text
Refactor this selected function to be clearer without changing behavior.
```

```text
Update this component so the button is disabled while loading.
```

Edit mode is best when the active file or selected code is already the main
context.

### Debug

Use Debug when something is broken.

Examples:

```text
Reproduce this error, find the root cause, fix it, and rerun the command.
```

```text
The terminal shows an import error. Diagnose and fix it.
```

Debug mode should start from the actual error or failing command when possible.

### Review

Use Review when you want feedback without edits.

Examples:

```text
Review this pull-request-sized change for bugs and security issues.
```

```text
Review the payment flow and flag risky logic.
```

Review mode should cite the files it inspected and should not modify code.

### Scan

Use Scan when NexCoder needs to understand a project.

Examples:

```text
Scan the codebase and tell me how it is organized.
```

```text
Find the main entrypoints, build commands, and test commands.
```

### Plan

Use Plan for larger changes where you want to approve the approach first.

Examples:

```text
Create an implementation plan for adding multi-user support.
```

```text
Plan how to migrate this 2D renderer to a 3D renderer. Do not edit files yet.
```

After the plan is created, review it before approving implementation.

### Terminal

Use Terminal mode for command-oriented work.

Examples:

```text
Install the missing dependency after checking the package manager.
```

```text
Run the build and explain the error.
```

## 5. Agent Mesh

Agent Mesh is for large or complex tasks. It breaks a goal into multiple roles
instead of having one long agent turn do everything.

Use Agent Mesh when:

- the task has many steps
- the codebase is unfamiliar
- verification matters
- you want exploration, implementation, and review separated

Example:

```text
Upgrade this snake game into a polished installable desktop game. Verify the
executable and installer outputs exist before reporting success.
```

Agent Mesh may complete with issues. Read the final report carefully. A
completed run is not the same as a fully verified product result unless the
report says validation passed and shows what was checked.

## 6. Problems panel

The Problems panel shows errors, warnings, and hints from language tools.

Use it to:

- see how many problems are currently open
- click a problem and jump to the file
- give the agent exact diagnostics to fix

Example prompt:

```text
Fix all current Problems panel errors. Do not make unrelated changes. After
fixing, run the correct validation command.
```

NexCoder sends the problem count and details to the agent, so the agent can see
what you see in the Problems panel.

## 7. File previews

NexCoder can open more than code files.

### Images

Supported image previews include common project assets such as:

- `.png`
- `.jpg`
- `.jpeg`
- `.gif`
- `.webp`
- `.svg`
- `.ico`
- `.bmp`
- `.tif`
- `.tiff`
- `.heic`
- `.heif`

Click an image preview to view it larger when supported.

### Audio

Supported audio previews include:

- `.mp3`
- `.wav`
- `.ogg`
- `.m4a`
- `.aac`
- `.opus`
- `.mid`
- `.midi`

Audio opens with player controls.

### Video

Supported video previews include:

- `.mp4`
- `.webm`
- `.mov`
- `.mkv`
- `.avi`
- `.m4v`

Video opens with player controls when the embedded browser supports the codec.

### PDF and fonts

PDFs open in an embedded preview where supported. Fonts show a preview sample.

### Unknown binary files

Unknown binary files open in a safe metadata preview instead of being loaded as
text. This protects files such as archives, executables, generated assets, and
other non-text formats.

## 8. Image upload and vision models

You can attach an image to a prompt. This is useful for:

- UI bugs
- screenshot-based debugging
- rendering problems
- design feedback
- layout issues
- visual regression checks
- reading visible text in an image

Example:

```text
Analyze this screenshot, identify why the panel is overflowing, and fix the
layout.
```

Important: image analysis only works with vision-capable models. If the selected
model is text-only, NexCoder will ask you to switch models.

## 9. Model picker

The model picker lets you switch between configured models.

Use a faster model for:

- quick questions
- small edits
- simple explanations
- low-risk formatting fixes

Use a stronger model for:

- large refactors
- deep debugging
- Agent Mesh
- multimodal screenshot analysis
- complicated architecture work

If a model returns HTTP 429, switch to a different model or wait and retry.
HTTP 429 usually means the provider is rate-limiting you or the model has no
available capacity.

## 10. Terminal

The integrated terminal lets you run commands inside the current project.

Common commands:

```powershell
python main.py
```

```powershell
python -m pytest
```

```powershell
npm.cmd run build
```

```powershell
git status
```

On Windows, use `npm.cmd` if `npm` is blocked by PowerShell execution policy.

If the terminal is interrupted, start a new terminal session from the terminal
controls.

## 11. Reverting changes

NexCoder creates checkpoints for AI-made edits.

You can use revert when:

- the agent changed the wrong file
- the result is not what you wanted
- you edited and resent an earlier prompt
- a run partially failed

Prompt edit/resend should revert only the changes made after that prompt. It
should not remove work that happened before the prompt.

## 12. Privacy and data control

NexCoder works with local project files. Depending on your model settings, prompt
context may be sent to a hosted AI provider.

Follow these rules:

- Do not paste API keys into chat.
- Do not ask the agent to store secrets in project memory.
- Use trusted or local models for sensitive codebases.
- Review AI changes before shipping them.
- Be careful uploading screenshots that contain private data.

NexCoder should only send the context needed for the task, but you should still
treat hosted model requests as external processing.

## 13. Settings

Agent settings can include:

- model endpoint
- selected model
- tool adapter
- context window
- output reserve
- temperature
- maximum turns
- project command settings
- memory behavior
- disabled tools
- command approval behavior

Editor settings can include:

- theme
- font size
- tab size
- word wrap
- terminal font size
- terminal scrollback

If a setting does not appear to apply, restart NexCoder and reopen the project.

## 14. Troubleshooting

### NexCoder says the AI backend returned HTTP 404

The model endpoint URL may be wrong. Check that the base URL points to an
OpenAI-compatible API. Common valid shapes are:

```text
https://provider.example.com/v1
```

or:

```text
https://provider.example.com/v1/chat/completions
```

### NexCoder says HTTP 429

The provider is rate-limiting the request or has no capacity for that model.

Try:

- switch models
- wait and retry
- use a shorter prompt
- reduce output size
- use a paid/higher-quota endpoint

### The model is very slow

Large reasoning models can take longer, especially with long prompts and large
projects.

Try:

- a smaller model
- a shorter prompt
- a more specific active file or selection
- asking for one milestone at a time

### The agent stops with HTTP 400 after uploading an image

The selected model likely does not support images. Switch to a vision model.

### The agent made a bad change

Use the run/file revert controls. Then give a more specific prompt or switch to
Plan mode first.

### The agent says it completed but the app does not work

Ask it to verify with a concrete command:

```text
Run the app and verify the feature works. Do not claim completion just because
the application launches.
```

For packaged apps, ask it to confirm the output files actually exist.

### The terminal looks stuck

Start a new terminal session. If the problem repeats, restart NexCoder.

### A media file will not preview

The file may use a codec unsupported by the embedded browser. NexCoder should
still avoid opening it as corrupted text.

## 15. Best practices

- Start new projects with Scan mode.
- Use Ask mode before editing unfamiliar systems.
- Use Plan mode before large changes.
- Use Agent mode for normal implementation.
- Use Debug mode when there is a concrete error.
- Use Review mode before accepting large AI changes.
- Attach screenshots for visual bugs when using a vision model.
- Keep prompts specific and include validation steps.
- Revert early if the agent goes in the wrong direction.
- Switch models instead of repeatedly retrying a rate-limited model.

## 16. Example workflows

### Fix current errors

```text
Fix the current Problems panel errors. Use the smallest safe changes and run the
right validation command afterward.
```

### Add a feature

```text
Add user profile editing. First inspect the current auth and settings flow, then
implement the smallest working version and run the build.
```

### Work from a screenshot

```text
The attached screenshot shows the model picker dropdown is hidden. Analyze the
image, inspect the relevant UI components, and fix the positioning.
```

### Review before shipping

```text
Review the current changed files for correctness, security, and user-facing
regressions. Do not modify files.
```

### Use Agent Mesh

```text
Create a polished installable version of this game. Split the work into
exploration, implementation, verification, and review. Confirm the executable
and installer outputs exist before reporting success.
```

## 17. What NexCoder should not do silently

NexCoder should not silently:

- delete important user data
- commit or push changes without approval
- send messages or emails
- make purchases
- submit forms
- change passwords or account settings
- expose secrets
- claim success without meaningful verification

If a task involves sensitive or irreversible actions, require explicit approval.

## 18. Getting better results

If the agent struggles, give it stronger context:

- mention the file name
- select the broken code
- show the terminal error
- attach a screenshot
- ask for one milestone at a time
- specify the validation command
- tell it what not to change

Example:

```text
In src/menu.py, fix only the multiplayer score layout overflow. Do not redesign
the menu. After editing, run python -m py_compile src/menu.py.
```

Specific prompts produce better results than broad prompts.
