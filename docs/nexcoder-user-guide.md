# NexCoder User Guide

NexCoder is an AI-first coding workspace for opening real projects, editing
files, asking project-aware questions, planning changes, running agentic coding
tasks, reviewing problems, and verifying work from one desktop app.

This guide is for NexCoder users. It explains how to use the product day to day.
It does not cover source-code development, internal architecture, or packaging
NexCoder itself.

## Who NexCoder is for

NexCoder is designed for people who want an AI coding assistant inside their
editor instead of a detached chatbot. Use it when you want to:

- Understand an unfamiliar project.
- Ask questions about the code you have open.
- Make focused edits with AI assistance.
- Generate and review implementation plans before code changes happen.
- Let an agent inspect files, apply changes, and run verification commands.
- Work with terminals, diagnostics, Git changes, generated artifacts, and
  project memory in one place.

NexCoder is not a replacement for user judgment. Review AI-generated code,
inspect diffs, and run the relevant tests before trusting a change.

## System requirements

For production use, NexCoder is intended to run as a Windows desktop
application.

Recommended environment:

- Windows 10 or Windows 11.
- Git installed if you want repository cloning, source control status, diffs,
  and commits.
- A working internet connection for hosted AI model providers.
- Access to an OpenAI-compatible model endpoint, unless your NexCoder build is
  preconfigured by your organization.
- Enough disk space for opened projects, checkpoints, chat history, artifacts,
  and generated project state.

Some features depend on project tooling. For example, diagnostics depend on
language-server support, and verification depends on the project having working
test, build, lint, or type-check commands.

## First launch

When NexCoder opens, the welcome screen gives you three main starting options:

- Open Folder: open an existing local project directory.
- Open File: open a single local file.
- Clone Repository: clone a Git repository and open it as a project.

For the best AI experience, open a project folder rather than a single file.
Folder mode gives NexCoder the context it needs to search files, build a repo
map, understand diagnostics, create checkpoints, and run project-level
verification.

## Opening projects

### Open an existing folder

1. Select Open Folder.
2. Choose the root folder of your project.
3. Wait for the file explorer, editor, terminal, diagnostics, and AI panel to
   initialize.

Open the true repository root when possible. If you open a nested folder, the AI
may miss important files such as package manifests, tests, configuration, or
documentation.

### Open a recent project

The welcome screen lists recent projects. Select one to reopen it quickly.

### Clone a repository

1. Select Clone Repository.
2. Enter an HTTPS, SSH, git, file, or scp-style repository URL.
3. Choose the destination folder.
4. Optionally set a folder name.
5. Start the clone.

NexCoder opens the cloned repository automatically after a successful clone.
If cloning fails, check that Git is installed, the URL is correct, and you have
access to the repository.

## Workspace overview

NexCoder is organized around a few primary areas.

### Activity sidebar

The activity sidebar contains:

- Explorer: browse, open, create, rename, move, and delete project files.
- Search: search across the project.
- Source Control: review Git status and project changes.
- Extensions: manage available extension surfaces when supported by the build.
- Agent Tasks: track agent work items and task state.
- Agent Mesh: run and review larger multi-role AI workflows.

### Editor

The editor area supports:

- Multiple open tabs.
- Monaco-based code editing.
- Syntax highlighting and language detection.
- Editor diagnostics when language support is available.
- Image previews.
- Media and binary previews for supported file types.
- Implementation plan review pages.
- Read-only generated artifact views.

Use the editor like a normal code editor. Save files before running external
tools if those tools read from disk.

### AI panel

The AI panel is where you ask questions, request changes, attach context, switch
AI modes, queue follow-up prompts, stop active runs, and review agent output.

The AI panel can use:

- Your prompt.
- Active file context.
- Selected text.
- Open diagnostics.
- Mentioned files.
- Attached images if the selected model supports vision.
- Project memory.
- Project rules.
- Recent conversation history.

### Bottom panel

The bottom panel contains:

- Terminal: run commands in project-aware terminal sessions.
- Output: view relevant app or workflow output.
- Problems: inspect diagnostics from open files.
- Git Diff: review uncommitted changes.

## Keyboard shortcuts

Common shortcuts:

| Action | Shortcut |
|---|---|
| Toggle sidebar | Ctrl+B |
| Toggle terminal | Ctrl+` |
| Toggle AI panel | Ctrl+Shift+A |
| Save file | Ctrl+S |
| Open settings | Ctrl+, |

Shortcuts may vary by build or operating-system-level keyboard configuration.

## AI modes

NexCoder uses modes to control how much autonomy the AI has and which tools it
can use. Choose the mode that matches the risk and intent of your task.

| Mode | Best for | Can change files? |
|---|---|---|
| Ask | Questions, explanations, code reading, project guidance | No |
| Scan | Mapping a codebase and finding relevant files | No |
| Review | Finding bugs, risks, regressions, and missing tests | No |
| Plan | Creating an implementation plan for review | No |
| Edit | Focused code changes in a known area | Yes |
| Debug | Reproducing and fixing failures | Yes |
| Agent | General coding tasks with tool use and verification | Yes |
| Terminal | Command-heavy setup, validation, or environment work | Yes, command-focused |

Read-only modes are the right starting point when you are unsure. Use mutating
modes only when you are ready for NexCoder to propose or apply changes.

## Asking good questions

NexCoder works best when your prompt includes a clear goal, scope, and expected
verification.

Good examples:

```text
Scan this project and explain the main frontend entry points.
```

```text
Review the authentication flow for security risks. Do not make changes.
```

```text
Fix the failing checkout tests, keep the change scoped, and run the relevant
test command before summarizing.
```

```text
Create an implementation plan for adding OAuth login. Ask questions before
changing files.
```

Avoid vague prompts such as "fix everything" or "make it production ready"
unless you are intentionally asking NexCoder to start with a broad scan and
propose a staged plan.

## Adding context

### Active file and selection

NexCoder automatically uses the active editor file and selected text when
building AI context. If you want the AI to focus on a specific function or
error, select the relevant code before sending your prompt.

### File mentions

Type `@` in the AI prompt to mention project files. NexCoder shows matching
files and attaches the selected file as prompt context.

Examples:

```text
Explain how @nexcoder/bridge.py handles terminal sessions.
```

```text
Update @src/components/LoginForm.tsx to show a clearer rate-limit error.
```

If a path contains spaces, NexCoder can insert the mention with quotes.

### Text attachments

Large pasted text can be saved as a project-local prompt attachment. This keeps
the prompt manageable while still giving NexCoder a reference file.

### Image attachments

You can attach images to prompts when the selected model supports vision.

Supported image types:

- PNG
- JPEG
- WebP
- GIF

Limits:

- Up to 4 images per prompt.
- Up to 5 MB per image.
- Up to 10 MB total image size per prompt.

Use image attachments for UI screenshots, error screenshots, design references,
or visual bug reports. If the selected model does not support vision, switch to
a vision-capable model or describe the image in text.

## Working with plans

Plan mode is for changes that should be reviewed before implementation.

A typical planning workflow:

1. Select Plan mode.
2. Describe the change you want.
3. Let NexCoder inspect the project and draft a plan.
4. Answer any clarification questions.
5. Review the generated implementation plan.
6. Request revisions if something is wrong or missing.
7. Approve the plan only when you are ready for execution.
8. Review the implementation progress and final summary.

Planning is useful for large refactors, new features, risky changes, database
work, authentication changes, billing changes, and anything that should not be
started from a single vague instruction.

Plans can be saved as Markdown when you want a durable project document.

## Agent runs

Agent mode is the general autonomous coding mode. The agent may read files,
search the project, edit files, create checkpoints, run commands, update todos,
and summarize the result.

Use Agent mode for tasks such as:

- Add a small feature and verify it.
- Fix a test failure.
- Refactor a focused module.
- Update UI behavior across a few related files.
- Generate docs from existing code.
- Investigate an error and propose or apply a fix.

During a run, watch for:

- The files the agent reads.
- The commands it requests or runs.
- The changes it proposes.
- The tests or checks it uses for verification.
- The final summary and any stated limitations.

You can stop an active run if it is heading in the wrong direction.

## Follow-up prompts and steering

If an agent run is active, you can queue a follow-up prompt. NexCoder applies
queued prompts at safe points so the current run can be steered without
interrupting a partially completed tool action.

Useful steering prompts:

```text
Keep the change scoped to the settings panel.
```

```text
Do not touch the API client in this pass.
```

```text
After this edit, run only the focused test file.
```

You can also copy, edit, use, or delete queued prompts from the input area.

## Stop, revert, and prompt edit

### Stop

Use Stop when an AI run should halt. NexCoder attempts to stop both the agent
loop and the active model stream.

### Revert

When the agent changes files, NexCoder creates checkpoints. Revert options may
let you restore an entire run or individual changed files, depending on the
surface you are using.

Always review the diff after reverting. External tools, generated files, or
commands run outside NexCoder may not be fully represented by checkpoints.

### Edit and resend

Prompt edit/resend is useful when your original prompt was unclear. NexCoder can
rewind later conversation and later agent changes while preserving earlier work.

Use this when the agent followed your instruction correctly but your instruction
was incomplete or wrong.

## Agent Mesh

Agent Mesh is for larger goals that benefit from multiple roles, such as
exploration, implementation, testing, and review.

Use Agent Mesh when:

- The task spans multiple areas of the project.
- You want a broader investigation before implementation.
- You want separate review-style feedback after implementation.
- You are not sure which files matter.

Agent Mesh can take longer than normal Agent mode. Review the final status
carefully. A completed mesh run does not automatically mean every requested
behavior is fully verified.

## Diagnostics and problems

The Problems panel shows diagnostics for open files when language support is
available.

You can use Problems to:

- Jump to the affected file and line.
- Ask NexCoder to explain a diagnostic.
- Ask NexCoder to fix a diagnostic.
- Copy a diagnostic for external use.

Diagnostics depend on the language server and project setup. If a project is
missing dependencies or configuration, diagnostics may be incomplete.

## Terminal

The integrated terminal lets you run project commands without leaving
NexCoder.

Common uses:

- Install project dependencies.
- Run tests.
- Run build commands.
- Start local development servers.
- Inspect command output while asking the AI for help.

Terminal sessions are project-aware. When you switch projects, terminal state is
separate from the previous project.

If a terminal becomes unavailable, use Restart terminal or open a new terminal
session.

## Source control

NexCoder includes source-control surfaces for Git-backed projects.

Depending on your build and repository state, you can:

- View the current branch.
- Inspect changed files.
- Review diffs.
- Stage and unstage files.
- Create commits.
- View recent commit history.

Before committing AI-generated code:

1. Review the diff.
2. Run relevant tests or checks.
3. Confirm no secrets or local-only files are included.
4. Use a clear commit message.

## Generated artifacts

NexCoder may create project-local artifacts during AI workflows. Generated
artifact files are stored under the project's `.nexcoder` area and are treated
separately from normal source files when possible.

Use artifacts for drafts, summaries, generated documents, or intermediate AI
outputs that should not immediately become product code.

Review artifacts before moving their contents into source files.

## Project memory

Project memory stores durable facts that NexCoder can reuse in future runs.
Examples include project conventions, important commands, known constraints, or
architecture decisions.

Good memory entries:

- "Use npm.cmd on Windows for this project."
- "Authentication errors should use the shared ApiError component."
- "Do not change generated files under dist/."

Bad memory entries:

- API keys.
- Passwords.
- Private customer data.
- Temporary guesses.
- Large logs.

You can view and edit project memory from Settings when a project is open.

## Rules

NexCoder can read project rules from files such as `AGENTS.md`, `NEXCODER.md`,
or `.nexcoder/rules/*.md` when present.

Rules are useful for:

- Coding standards.
- Test requirements.
- Safety constraints.
- Product-specific expectations.
- Project conventions.

Keep rules concise and practical. Rules should guide the AI toward better work,
not bury it in generic advice.

## Model setup

NexCoder uses OpenAI-compatible model APIs. Your organization or local setup may
preconfigure the endpoint and model. If not, configure them from Settings.

Important model settings:

- Endpoint: the OpenAI-compatible API base URL.
- Model: the provider model ID.
- API key: the credential used for the provider.
- Adapter: the model/tool-call format used by the agent.
- Context window: the total context budget.
- Output reserve: tokens reserved for the model answer.
- Temperature: randomness level.
- Max turns: how long agent runs may continue.
- Disabled tools: tool categories the agent should not use.
- Memory: whether project memory is included.

Use Test Connection after changing provider settings. If the provider is
unreachable, check the endpoint, key, network connection, and provider status.

Do not paste API keys into prompts, project memory, issue descriptions, or
source files.

## Choosing a model

Use the model selector to switch between available provider models.

General guidance:

- Use faster models for quick questions, summaries, and small edits.
- Use stronger reasoning models for debugging, planning, refactoring, and
  multi-file work.
- Use a vision-capable model when attaching screenshots or design images.
- If a provider model is overloaded or rate-limited, switch models or retry
  later.

The model selector may show pinned models even when the provider's model list is
temporarily incomplete.

## Settings

Settings are grouped into editor and agent areas.

Editor settings include:

- Theme.
- UI scale.
- Font family and size.
- Sidebar and AI panel position.
- Tab size and indentation.
- Word wrap.
- Line numbers.
- Terminal font and scrollback.
- Language-server options.
- Privacy preferences.

Agent settings include:

- Model endpoint and model ID.
- AI modes and autonomy.
- Tool availability.
- Project rules.
- Validation behavior.
- Project memory.
- Command permissions.
- Advanced model/runtime options.

Change one or two settings at a time and test the result, especially when
adjusting model or tool settings.

## Permissions and safety

NexCoder is designed around explicit boundaries.

Important safety behaviors:

- Read-only modes should not receive file-mutation tools.
- File edits are checkpointed so they can be reviewed or reverted.
- Shell commands are controlled by command policy.
- Sensitive environment variables are redacted unless explicitly allowed.
- High-risk workflow actions should require explicit user approval.

Treat these actions as high risk:

- Sending messages or emails.
- Submitting forms.
- Making purchases.
- Deleting important data.
- Changing passwords or account settings.
- Financial, legal, medical, or account-impacting actions.

NexCoder should not perform high-risk actions silently. If a workflow asks for
something sensitive, pause and require clear confirmation.

## Privacy

NexCoder can work with local project files, chat prompts, diagnostics, terminal
output, images, and generated artifacts. Only provide the context needed for the
task.

Privacy practices:

- Do not include secrets in prompts.
- Do not store private credentials in project memory.
- Review terminal output before sending it to the AI if it may contain tokens.
- Avoid attaching private screenshots unless the selected provider and usage are
  approved for that data.
- Keep `.nexcoder` project state out of public commits unless your team
  intentionally shares it.

If your organization has a data policy, follow it when selecting model providers
and deciding what code or files can be sent to hosted AI services.

## Working with sensitive projects

For sensitive repositories:

1. Start in Ask, Scan, Review, or Plan mode.
2. Disable shell commands if command execution is not allowed.
3. Disable file modifications if you only want advice.
4. Avoid attaching screenshots or large pasted logs that may contain private
   data.
5. Review project memory before and after important runs.
6. Review every diff before saving or committing changes.

## Recommended daily workflow

For understanding a project:

1. Open the repository root.
2. Use Scan mode: "Map this project and explain the main entry points."
3. Open the files NexCoder identifies.
4. Ask focused follow-up questions with file mentions.

For a small code change:

1. Open the relevant files.
2. Use Edit mode with a focused prompt.
3. Review the diff.
4. Run the focused test or build command.
5. Commit only after reviewing the final changes.

For a risky or multi-file change:

1. Use Plan mode.
2. Review and revise the implementation plan.
3. Approve execution only when the plan is clear.
4. Monitor the agent run.
5. Review diffs, checkpoints, tests, and final summary.

For debugging:

1. Paste the exact error or select the failing diagnostic.
2. Use Debug mode.
3. Ask NexCoder to reproduce the failure before fixing it.
4. Run the relevant verification after the fix.

## Troubleshooting

### The AI does not answer

Check:

- The model endpoint is configured.
- The API key is valid.
- Test Connection succeeds in Settings.
- Your internet connection is working.
- The provider is not rate-limited or overloaded.

### The model list is empty

The provider may not expose a complete model list. You can enter a custom model
ID if you know the exact provider model name.

### Image attachment is rejected

Check:

- The file is PNG, JPEG, WebP, or GIF.
- The file is 5 MB or smaller.
- Total attached image size is 10 MB or less.
- You have attached no more than 4 images.
- The selected model supports vision.

### The agent changed the wrong file

Stop the run if it is still active. Then:

1. Review the diff.
2. Use checkpoint revert if available.
3. Edit and resend the prompt with clearer scope.
4. Mention exact files with `@`.

### Commands fail in the terminal

Check:

- The project dependencies are installed.
- The command is correct for Windows.
- The terminal is running in the expected project folder.
- Required environment variables are configured.
- The project itself can run outside NexCoder.

### Diagnostics are missing

Check:

- The file is saved.
- The language server is enabled.
- Project dependencies are installed.
- The file type is supported.
- The project has valid language configuration.

### Git features are unavailable

Check:

- Git is installed.
- The opened folder is a Git repository.
- You have access to the repository.
- The repository is not in the middle of an unresolved Git operation.

### NexCoder feels slow

Try:

- Use a faster model for simple tasks.
- Reduce the scope of the prompt.
- Mention only the files that matter.
- Close unrelated large files.
- Avoid attaching unnecessary images or logs.
- Use Plan mode before asking for broad implementation.

## Known limitations

NexCoder is a production-oriented product under active development. Depending on
your build and configuration, some features may be limited by model provider
behavior, project setup, or local environment.

Known practical limits:

- AI output can be wrong. Review changes before trusting them.
- Large repositories may require narrower prompts or planning first.
- Hosted model providers may rate-limit, return incomplete model lists, or
  reject long requests.
- Diagnostics depend on language-server configuration and project dependencies.
- Checkpoints cover NexCoder-managed file changes, but external commands may
  create side effects outside the checkpoint model.
- Agent Mesh can coordinate larger work, but completion status still requires
  human review and verification.

## Glossary

| Term | Meaning |
|---|---|
| Agent | NexCoder's AI workflow that can inspect context, use tools, edit files, and verify work. |
| Checkpoint | A saved file state used to review or revert AI changes. |
| Context | The information sent to the AI, such as prompts, files, diagnostics, memory, and selections. |
| Diagnostics | Errors, warnings, and hints from language tooling. |
| File mention | A prompt reference to a project file, usually inserted with `@`. |
| Model endpoint | The OpenAI-compatible API URL used by NexCoder. |
| Plan | A reviewable implementation proposal generated before changes are applied. |
| Project memory | Durable project facts that NexCoder can reuse in future runs. |
| Rules | Project instructions loaded from files such as `AGENTS.md` or `NEXCODER.md`. |
| Tool | A capability the AI can use, such as reading files, searching, editing, or running commands. |

## User checklist before trusting AI changes

Before accepting or committing AI-generated work:

1. Read the final summary.
2. Review every changed file.
3. Check whether any unrelated files changed.
4. Run the relevant tests, build, lint, or type checks.
5. Confirm no secrets or private data were added.
6. Confirm the behavior manually if the change affects UI, auth, billing, data,
   files, or user workflows.
7. Commit only the changes you intentionally want.

## Getting better results

Use clear, scoped prompts:

```text
In @src/auth/session.ts, fix the token refresh retry logic. Keep the public API
unchanged and run the session tests after editing.
```

Give constraints early:

```text
Do not change database schemas. If a schema change seems necessary, explain why
and stop for review.
```

Ask for verification:

```text
After the fix, run the smallest relevant test command and summarize the result.
```

Use planning for uncertainty:

```text
Create a plan for this migration first. Include risks, files likely to change,
and a rollback strategy.
```

NexCoder works best when it can see the real project, receives precise scope,
and has permission to run the checks that prove the work is done.
