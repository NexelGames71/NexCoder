---
name: commit
description: Inspect staged and unstaged changes, group them logically, and write a conventional commit
category: quality
---
# Commit

Create well-formed git commits from the current working tree.

## Process
1. Run `git status` and `git diff` (and `git diff --cached`) with run_command to see every change.
2. Group related changes. If unrelated changes are mixed, commit them separately (`git add <specific files>` per group).
3. Write the message in conventional-commit form: `type(scope): summary` where type is one of feat, fix, docs, refactor, test, chore. The summary is imperative, under 72 chars. Add a body only when the why is not obvious from the diff.
4. Commit with `git commit -m "..."`. For multi-line messages, use multiple `-m` flags.
5. Confirm with `git log -1 --stat` and report the commit hash and message.

## Rules
- Never push. Never use --no-verify, --amend (unless asked), or force flags.
- Never commit secrets, .env files, or large binaries; if staged, warn and unstage them instead.
- If there are no changes, say so and stop.
