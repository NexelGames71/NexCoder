import React from 'react';
import { Play, CheckCircle, AlertTriangle, Loader2, FileEdit, Ban } from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { useAgentRunStore, AgentRun } from '../../store/useAgentRunStore';

function statusIcon(run: AgentRun) {
  if (run.runActive) return <Loader2 size={14} className="spin" style={{ color: 'var(--accent-purple)' }} />;
  switch (run.status) {
    case 'completed': return <CheckCircle size={14} style={{ color: 'var(--accent-green)' }} />;
    case 'error': return <AlertTriangle size={14} style={{ color: 'var(--accent-red)' }} />;
    case 'cancelled': return <Ban size={14} style={{ color: 'var(--text-tertiary)' }} />;
    default: return <Play size={14} style={{ color: 'var(--text-secondary)' }} />;
  }
}

// A run's title is the prompt that started it (chat message with the same
// id), falling back to the first prose line or the final text.
function runTitle(runId: string, run: AgentRun, prompts: Record<string, string>): string {
  if (prompts[runId]) return prompts[runId];
  const firstText = run.transcript.find((t) => t.kind === 'text');
  if (firstText && firstText.kind === 'text' && firstText.text.trim()) {
    return firstText.text.trim().slice(0, 100);
  }
  return run.finalText.slice(0, 100) || 'Agent run';
}

export default function TasksPanel() {
  const runs = useAgentRunStore((s) => s.runs);
  const messages = useChatStore((s) => s.messages);

  // Map runId (user message id) → prompt text.
  const prompts: Record<string, string> = {};
  for (const m of messages) {
    if (m.role === 'user') prompts[m.id] = m.content;
  }

  // Newest first; runs are inserted in start() order (object key order).
  const entries = Object.entries(runs).reverse();

  return (
    <div className="sidebar-panel">
      <div className="sidebar-header">
        <span>Agent Tasks</span>
      </div>

      <div className="overflow-auto flex-1" style={{ padding: 'var(--space-3)' }}>
        {entries.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)', paddingTop: 'var(--space-6)' }}>
            No agent tasks yet. Give the agent a task in the AI panel and it will appear here.
          </p>
        ) : (
          entries.map(([runId, run]) => {
            const steps = run.transcript.filter((t) => t.kind === 'step').length;
            return (
              <div key={runId} className="task-card">
                <div className="task-card-head">
                  {statusIcon(run)}
                  <span className="task-card-status">
                    {run.runActive ? 'running' : run.status || 'done'}
                  </span>
                  {run.mutatedFiles.length > 0 && (
                    <span className="task-card-files">
                      <FileEdit size={11} /> {run.mutatedFiles.length}
                    </span>
                  )}
                </div>
                <p className="task-card-title">{runTitle(runId, run, prompts)}</p>
                {(steps > 0 || run.todos.length > 0) && (
                  <div className="task-card-meta">
                    {steps > 0 && <span>{steps} action{steps > 1 ? 's' : ''}</span>}
                    {run.todos.length > 0 && (
                      <span>
                        {run.todos.filter((t) => t.status === 'completed').length}/{run.todos.length} plan
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
