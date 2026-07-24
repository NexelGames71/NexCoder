---
name: systematic-debugging
description: Hypothesis-driven debugging - reproduce, isolate the root cause, fix, verify; never patch blind
category: quality
---
# Systematic Debugging

Find the root cause before changing any code.

## Process
1. Reproduce: run the failing command/test with run_command and read the ACTUAL error output. Never work from a paraphrase.
2. Read the error carefully: exact exception, file, line. Read that code and the code that calls it.
3. Form ONE hypothesis about the root cause. State it explicitly.
4. Test the hypothesis with evidence (read the code path, add a focused check, or run a narrower command) before editing.
5. Fix the root cause with edit_file — the smallest change that addresses the cause, not the symptom.
6. Re-run the original failing command. If still failing, the hypothesis was wrong: return to step 2 with the new output. Do not stack speculative fixes.
7. Run the broader test suite to check for regressions.

## Rules
- One hypothesis at a time. Revert speculative edits that did not help.
- If three hypotheses fail, step back and re-read the whole failing path before continuing.
