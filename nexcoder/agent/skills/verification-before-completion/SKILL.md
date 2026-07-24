---
name: verification-before-completion
description: Run the relevant verification and read its output before claiming any work is done
category: quality
---
# Verification Before Completion

Evidence before assertions. Never claim success without running proof.

## Process
1. Identify the verification for the work just done: the test suite for code changes, the build for config changes, reading the file back for generated files, running the app for behavior changes.
2. Run it with run_command and READ the output — exit code alone is not enough.
3. If it fails: the task is not done. Fix and re-verify. Report failures honestly if you cannot fix them.
4. Only after a passing verification, summarize: what changed, what command proved it, and the relevant output line.

## Rules
- "Should work" is banned. Either you ran it and saw it pass, or the task is unfinished.
- Partial completion must be reported as partial, with what remains.
