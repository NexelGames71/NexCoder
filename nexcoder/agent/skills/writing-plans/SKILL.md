---
name: writing-plans
description: Break a multi-step task into ordered, verifiable todo items before touching code
category: workflow
---
# Writing Plans

Plan before implementing anything non-trivial.

## Process
1. Restate the goal in one sentence.
2. Inspect enough of the project (glob, grep, read_file) to know which files each step touches.
3. Call todo_write with ordered steps. Each step must be:
   - Small: one coherent change.
   - Verifiable: name the command or check that proves it done.
   - Ordered: earlier steps unblock later ones.
4. Execute steps in order. Mark each in_progress when started, completed only after its verification passes. Update the list when reality diverges from the plan.
5. Finish with every item completed or explicitly reported as blocked.

## Rules
- No implementation before the todo list exists (for tasks with 3+ steps).
- Never mark an item completed without having run its verification.
