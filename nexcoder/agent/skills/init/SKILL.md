---
name: init
description: Scan the project and generate an AGENTS.md guide with architecture, commands, and conventions
category: workflow
---
# Init

Generate a concise AGENTS.md so agents and new developers can work in this repo.

## Process
1. Inspect the project: list_directory the root, read the README, manifest files (package.json / pyproject.toml / etc.), and one or two core source files. Use the project map if provided.
2. Identify: what the project is, the language/framework, how to build, how to run tests, how to start the app, directory layout, and any conventions visible in the code.
3. Write AGENTS.md at the project root with exactly these sections:
   - `# <Project name>` — one-paragraph purpose.
   - `## Commands` — build, test, run, lint as copy-pasteable commands.
   - `## Architecture` — key directories and what lives in each; main entry points.
   - `## Conventions` — style, naming, and patterns observed in the code.
4. Verify the file exists by reading it back.

## Rules
- Only document what you verified in files; never guess commands.
- Keep it under 100 lines. If AGENTS.md already exists, update rather than replace it.
