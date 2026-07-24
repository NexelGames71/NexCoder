---
name: code-review
description: Structured severity-tagged review of the working diff or named files, citing file and line
category: quality
---
# Code Review

Review code and report findings; do not change code unless explicitly asked.

## Process
1. Determine scope: the files the user named, or `git diff` (working tree) if none.
2. Read every file in scope fully before judging any of it.
3. Check in order: correctness bugs, security issues (injection, secrets, unsafe input), error handling gaps, performance traps, then clarity/simplification.
4. Report findings grouped by severity:
   - 🔴 Critical — bugs, security holes, data loss. Must fix.
   - 🟡 Warning — error-handling gaps, risky patterns, perf problems.
   - 🔵 Info — style, naming, simplification opportunities.
5. Cite every finding as `path/to/file.py:LINE` with a one-sentence defect statement and a concrete failure scenario.
6. End with a one-paragraph verdict: is this safe to merge?

## Rules
- Verify each finding by reading surrounding code; no speculation.
- No findings is a valid result — say the code looks correct and why.
