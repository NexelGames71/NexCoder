import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  FileCode2,
  FolderTree,
  Loader2,
  Pencil,
  Search,
  ShieldAlert,
  Terminal,
  Wrench,
  ListChecks,
} from 'lucide-react';
import { AgentTask, AgentTaskStep } from '../../types';

interface AgentTurnPanelProps {
  task: AgentTask;
  isActive: boolean;
  scanSteps?: string[];
}

function toolIcon(tool?: string) {
  switch (tool) {
    case 'read_file':
      return FileCode2;
    case 'search_grep':
    case 'search_code':
      return Search;
    case 'write_file':
      return Pencil;
    case 'run_command':
    case 'run_terminal_command':
    case 'run_tests':
      return Terminal;
    case 'list_directory':
    case 'list_project_tree':
      return FolderTree;
    default:
      return Wrench;
  }
}

function StepIcon({ status }: { status: AgentTaskStep['status'] }) {
  if (status === 'running') return <Loader2 size={12} className="spin agent-step-icon-running" />;
  if (status === 'completed') return <CheckCircle size={12} className="agent-step-icon-done" />;
  if (status === 'failed' || status === 'blocked') return <AlertCircle size={12} className="agent-step-icon-error" />;
  if (status === 'approval_required') return <ShieldAlert size={12} className="agent-step-icon-warn" />;
  return <ChevronRight size={10} className="agent-step-icon-pending" />;
}

function formatDuration(startMs: number, endMs?: number | null) {
  const end = endMs ?? Date.now();
  const sec = Math.max(0, Math.floor((end - startMs) / 1000));
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

function statusText(status: AgentTask['status']) {
  switch (status) {
    case 'running':
      return 'Working';
    case 'complete':
      return 'Done';
    case 'error':
      return 'Failed';
    case 'awaiting_approval':
      return 'Needs review';
    default:
      return 'Pending';
  }
}

export default function AgentTurnPanel({ task, isActive, scanSteps = [] }: AgentTurnPanelProps) {
  const [, setClock] = useState(0);
  const toolSteps = useMemo(
    () => (task.steps || []).filter((step) => step.type === 'tool_call' || step.tool),
    [task.steps],
  );
  const systemSteps = useMemo(
    () => (task.steps || []).filter((step) => step.type !== 'tool_call' && !step.tool),
    [task.steps],
  );

  const isRunning = task.status === 'running' && isActive;
  useEffect(() => {
    if (!isRunning) return;
    const timer = window.setInterval(() => setClock((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [isRunning]);
  const isDone = task.status === 'complete' || task.status === 'error' || task.status === 'awaiting_approval';
  const [expanded, setExpanded] = useState(isRunning);

  const completedTools = toolSteps.filter((s) => s.status === 'completed').length;
  const summaryLabel = isRunning
    ? toolSteps.length > 0
      ? `Working · ${completedTools}/${toolSteps.length} tools`
      : 'Working…'
    : toolSteps.length > 0
      ? `Used ${toolSteps.length} tool${toolSteps.length !== 1 ? 's' : ''}`
      : systemSteps.length > 0
        ? `${systemSteps.length} step${systemSteps.length !== 1 ? 's' : ''}`
        : 'Agent activity';

  const changedFiles = task.changedFiles || [];
  const showDetails = expanded || isRunning;

  return (
    <div className={`agent-turn ${isRunning ? 'agent-turn-active' : ''} agent-turn-${task.status}`}>
      <button
        type="button"
        className="agent-turn-header"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={showDetails}
      >
        <div className="agent-turn-header-left">
          {isRunning ? (
            <Loader2 size={13} className="spin agent-turn-spinner" />
          ) : task.status === 'complete' ? (
            <CheckCircle size={13} className="agent-turn-icon-done" />
          ) : task.status === 'error' ? (
            <AlertCircle size={13} className="agent-turn-icon-error" />
          ) : (
            <ShieldAlert size={13} className="agent-turn-icon-warn" />
          )}
          <span className="agent-turn-summary">{summaryLabel}</span>
          <span className="agent-turn-duration">{formatDuration(task.timestamp)}</span>
        </div>
        <div className="agent-turn-header-right">
          <span className={`agent-turn-status agent-turn-status-${task.status}`}>
            {statusText(task.status)}
          </span>
          {!isRunning && (showDetails ? <ChevronDown size={12} /> : <ChevronRight size={12} />)}
        </div>
      </button>

      {showDetails && (
        <div className="agent-turn-body">
          {task.plan && task.plan.items.length > 0 && (
            <div className="agent-task-plan">
              <div className="agent-task-plan-heading">
                <ListChecks size={11} />
                <span>Task plan</span>
              </div>
              <div className="agent-task-plan-items">
                {task.plan.items.map((item) => (
                  <div key={item.id} className={`agent-task-plan-item agent-task-plan-item-${item.status}`}>
                    <StepIcon status={
                      item.status === 'in_progress' ? 'running'
                        : item.status === 'completed' ? 'completed'
                          : item.status === 'approval_required' ? 'approval_required'
                            : item.status === 'failed' ? 'failed'
                              : item.status === 'blocked' ? 'blocked'
                                : item.status === 'skipped' ? 'skipped'
                                  : 'pending'
                    } />
                    <div className="agent-task-plan-copy">
                      <span>{item.title}</span>
                      {item.detail && <small>{item.detail}</small>}
                      {item.error && <small className="agent-step-error">{item.error}</small>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {toolSteps.length > 0 && (
            <div className="agent-turn-steps">
              {toolSteps.map((step) => {
                const Icon = toolIcon(step.tool);
                return (
                  <div key={step.id} className={`agent-turn-step agent-turn-step-${step.status}`}>
                    <StepIcon status={step.status} />
                    <Icon size={11} className="agent-turn-step-tool-icon" />
                    <div className="agent-turn-step-content">
                      <span className="agent-turn-step-label">{step.label}</span>
                      {step.target && (
                        <code className="agent-turn-step-target" title={step.target}>
                          {step.target}
                        </code>
                      )}
                      {step.result_summary && step.status === 'completed' && (
                        <span className="agent-turn-step-result">{step.result_summary}</span>
                      )}
                      {step.error && (
                        <span className="agent-turn-step-error">{step.error}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {scanSteps.length > 0 && (
            <div className="agent-turn-scan">
              <div className="agent-turn-scan-label">Indexed files</div>
              <div className="agent-turn-scan-list">
                {scanSteps.slice(-8).map((step, i) => (
                  <div key={`${step}-${i}`} className="agent-turn-scan-item">
                    <CheckCircle size={9} className="agent-turn-icon-done" />
                    <span>{step.replace(/^Reading\s+/i, '').replace(/\.\.\.$/, '')}</span>
                  </div>
                ))}
                {scanSteps.length > 8 && (
                  <div className="agent-turn-scan-more">+{scanSteps.length - 8} more files</div>
                )}
              </div>
            </div>
          )}

          {systemSteps.length > 0 && toolSteps.length === 0 && (
            <div className="agent-turn-steps">
              {systemSteps.map((step) => (
                <div key={step.id} className={`agent-turn-step agent-turn-step-${step.status}`}>
                  <StepIcon status={step.status} />
                  <div className="agent-turn-step-content">
                    <span className="agent-turn-step-label">{step.label}</span>
                    {step.result_summary && (
                      <span className="agent-turn-step-result">{step.result_summary}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {changedFiles.length > 0 && (
            <div className="agent-turn-files">
              {changedFiles.map((file) => (
                <div key={`${file.action}:${file.path}`} className="agent-turn-file">
                  <span className={`agent-turn-file-action agent-turn-file-${file.action}`}>
                    {file.action}
                  </span>
                  <FileCode2 size={10} />
                  <span className="agent-turn-file-path" title={file.path}>
                    {file.path.split(/[\\/]/).pop() || file.path}
                  </span>
                </div>
              ))}
            </div>
          )}

          {task.status === 'awaiting_approval' && (
            <div className="agent-turn-approval">
              <ShieldAlert size={12} />
              Review proposed changes before applying
            </div>
          )}
        </div>
      )}

      {isDone && !expanded && changedFiles.length > 0 && (
        <div className="agent-turn-collapsed-files">
          {changedFiles.slice(0, 3).map((file) => (
            <span key={`${file.action}:${file.path}`} className="agent-turn-file-chip">
              {file.path.split(/[\\/]/).pop()}
            </span>
          ))}
          {changedFiles.length > 3 && (
            <span className="agent-turn-file-chip">+{changedFiles.length - 3}</span>
          )}
        </div>
      )}
    </div>
  );
}
