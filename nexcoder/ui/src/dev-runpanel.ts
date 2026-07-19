/** Dev-only harness: mounts AgentRunPanel with a store driven by
 *  simulated events, so transcript rendering (diffs, command output,
 *  live tails) can be inspected in a plain browser. Not part of the
 *  app; loaded manually via `import('/src/dev-runpanel.ts')`. */
import React from 'react';
import ReactDOM from 'react-dom/client';
import AgentRunPanel from './components/AIPanel/AgentRunPanel';
import { useAgentRunStore } from './store/useAgentRunStore';

const store = useAgentRunStore.getState();
store.start('dev-run');
const feed = (type: string, payload: Record<string, unknown>) =>
  useAgentRunStore.getState().handleEvent({ type, payload });

// A finished command with mixed output.
feed('tool_started', { tool: 'run_command', args: { command: 'npm run build' } });
for (const line of [
  '> nexcoder-ui@0.1.0 build',
  '> tsc && vite build',
  'vite v6.4.3 building for production...',
  'warning: chunk size exceeds 500kB',
  'error TS2345: Argument of type string is not assignable',
  '✓ built in 6.02s',
]) feed('command_output', { line });
feed('tool_result', { tool: 'run_command', success: true, summary: 'ok' });

// A still-running command — should show the live tail without clicks.
feed('tool_started', { tool: 'run_command', args: { command: 'python -m pytest tests -q' } });
for (let i = 1; i <= 9; i++) feed('command_output', { line: `tests/core/test_case_${i}.py .. [${i * 11}%]` });

const el = document.createElement('div');
el.id = 'runpanel-dev-root';
el.style.cssText = 'max-width:420px;margin:20px auto;padding:12px;';
document.body.appendChild(el);
ReactDOM.createRoot(el).render(
  React.createElement(AgentRunPanel, { runId: 'dev-run' }),
);
