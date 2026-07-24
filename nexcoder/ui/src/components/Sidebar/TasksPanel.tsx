import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  ExternalLink,
  FileEdit,
  ListChecks,
  Loader2,
  MessageSquareText,
  Play,
  Terminal,
} from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { AgentRun, useAgentRunStore } from '../../store/useAgentRunStore';

function statusIcon(run: AgentRun) {
  if (run.runActive) return <Loader2 size={14} className="spin" style={{ color: 'var(--accent-purple)' }} />;
  switch (run.status) {
    case 'completed': return <CheckCircle size={14} style={{ color: 'var(--accent-green)' }} />;
    case 'error': return <AlertTriangle size={14} style={{ color: 'var(--accent-red)' }} />;
    case 'cancelled': return <Ban size={14} style={{ color: 'var(--text-tertiary)' }} />;
    default: return <Play size={14} style={{ color: 'var(--text-secondary)' }} />;
  }
}

function statusLabel(run: AgentRun): string {
  if (run.runActive) return 'Running';
  if (run.status === 'completed') return 'Completed';
  if (run.status === 'error') return 'Error';
  if (run.status === 'cancelled') return 'Cancelled';
  return run.status || 'Done';
}

function runTitle(runId: string, run: AgentRun, prompts: Record<string, string>): string {
  if (prompts[runId]) return prompts[runId];
  const firstText = run.transcript.find((item) => item.kind === 'text');
  if (firstText && firstText.kind === 'text' && firstText.text.trim()) {
    return firstText.text.trim().slice(0, 120);
  }
  return run.finalText.slice(0, 120) || 'Agent run';
}

function runMetrics(run: AgentRun) {
  const toolSteps = run.transcript.filter((item) => item.kind === 'step');
  const completedTodos = run.todos.filter((todo) => todo.status === 'completed').length;
  const activeTodo = run.todos.find((todo) => todo.status === 'in_progress');
  return {
    toolSteps,
    completedTodos,
    activeTodo,
    progress: run.todos.length > 0 ? Math.round((completedTodos / run.todos.length) * 100) : null,
  };
}

export default function TasksPanel() {
  const runs = useAgentRunStore((state) => state.runs);
  const activeRunId = useAgentRunStore((state) => state.activeRunId);
  const messages = useChatStore((state) => state.messages);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const prompts: Record<string, string> = {};
  for (const message of messages) {
    if (message.role === 'user') prompts[message.id] = message.content;
  }

  const entries = Object.entries(runs).reverse();
  const summary = useMemo(() => {
    const values = Object.values(runs);
    return {
      total: values.length,
      running: values.filter((run) => run.runActive).length,
      changedFiles: values.reduce((sum, run) => sum + run.mutatedFiles.length, 0),
      errors: values.filter((run) => run.status === 'error').length,
    };
  }, [runs]);

  const openRun = (runId: string) => {
    window.nexcoder?.showAIPanel?.();
    window.dispatchEvent(new CustomEvent('nexcoder:focus-agent-run', {
      detail: { runId },
    }));
  };

  const copySummary = async (runId: string, run: AgentRun) => {
    const metrics = runMetrics(run);
    const lines = [
      runTitle(runId, run, prompts),
      `Status: ${statusLabel(run)}`,
      `Actions: ${metrics.toolSteps.length}`,
      `Files changed: ${run.mutatedFiles.length}`,
    ];
    if (run.finalText.trim()) lines.push('', run.finalText.trim());
    if (run.mutatedFiles.length) {
      lines.push('', 'Changed files:', ...run.mutatedFiles.map((file) => `- ${file}`));
    }
    await navigator.clipboard?.writeText(lines.join('\n'));
  };

  const toggleExpanded = (runId: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  };

  return (
    <div className="sidebar-panel">
      <div className="sidebar-header">
        <span>Agent Tasks</span>
      </div>

      <div className="tasks-panel-body">
        <div className="tasks-summary-grid">
          <div><strong>{summary.total}</strong><span>Total</span></div>
          <div><strong>{summary.running}</strong><span>Running</span></div>
          <div><strong>{summary.changedFiles}</strong><span>Files</span></div>
          <div><strong>{summary.errors}</strong><span>Errors</span></div>
        </div>

        {entries.length === 0 ? (
          <div className="tasks-empty">
            <MessageSquareText size={24} />
            <p>No agent tasks yet.</p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                window.nexcoder?.showAIPanel?.();
                window.setTimeout(() => document.getElementById('ai-chat-input')?.focus(), 0);
              }}
            >
              Start in AI Panel
            </button>
          </div>
        ) : entries.map(([runId, run]) => {
          const metrics = runMetrics(run);
          const isExpanded = expanded.has(runId) || run.runActive || runId === activeRunId;
          const latestStep = [...metrics.toolSteps].reverse()[0];
          const latestDetail = latestStep?.kind === 'step'
            ? String(latestStep.summary || latestStep.args?.command || latestStep.args?.path || latestStep.tool || '')
            : '';
          const preview = run.finalText.trim() || latestDetail || metrics.activeTodo?.content || '';
          return (
            <div key={runId} className={`task-card task-card-${run.status || 'running'} ${run.runActive ? 'active-run' : ''}`}>
              <div className="task-card-head">
                {statusIcon(run)}
                <span className="task-card-status">{statusLabel(run)}</span>
                {run.contextUsage && (
                  <span className={`task-context ${run.contextUsage.percent > 85 ? 'hot' : run.contextUsage.percent > 60 ? 'warm' : ''}`}>
                    {run.contextUsage.percent}%
                  </span>
                )}
                {run.mutatedFiles.length > 0 && (
                  <span className="task-card-files">
                    <FileEdit size={11} /> {run.mutatedFiles.length}
                  </span>
                )}
              </div>

              <p className="task-card-title">{runTitle(runId, run, prompts)}</p>

              {metrics.progress !== null && (
                <div className="task-progress" title={`${metrics.completedTodos}/${run.todos.length} plan items complete`}>
                  <span style={{ width: `${metrics.progress}%` }} />
                </div>
              )}

              <div className="task-card-meta">
                <span><Terminal size={10} /> {metrics.toolSteps.length} actions</span>
                {run.todos.length > 0 && (
                  <span><ListChecks size={10} /> {metrics.completedTodos}/{run.todos.length} plan</span>
                )}
                {run.runActive && <span><Clock size={10} /> live</span>}
              </div>

              {preview && <p className="task-card-preview">{preview}</p>}

              <div className="task-card-actions">
                <button type="button" onClick={() => openRun(runId)}>
                  <ExternalLink size={11} /> Open
                </button>
                <button type="button" onClick={() => void copySummary(runId, run)}>
                  <Copy size={11} /> Copy
                </button>
                {(run.mutatedFiles.length > 0 || metrics.toolSteps.length > 0 || run.todos.length > 0) && (
                  <button type="button" onClick={() => toggleExpanded(runId)}>
                    {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                    Details
                  </button>
                )}
              </div>

              {isExpanded && (
                <div className="task-card-details">
                  {metrics.activeTodo && (
                    <div className="task-detail-line">
                      <ListChecks size={11} />
                      <span>{metrics.activeTodo.content}</span>
                    </div>
                  )}
                  {latestStep && latestStep.kind === 'step' && (
                    <div className="task-detail-line">
                      <Terminal size={11} />
                      <span>{latestStep.tool}{latestDetail ? `: ${latestDetail}` : ''}</span>
                    </div>
                  )}
                  {run.mutatedFiles.slice(0, 5).map((file) => (
                    <div className="task-detail-line" key={file}>
                      <FileEdit size={11} />
                      <span>{file}</span>
                    </div>
                  ))}
                  {run.mutatedFiles.length > 5 && (
                    <div className="task-detail-line muted">
                      <span>+{run.mutatedFiles.length - 5} more files</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
