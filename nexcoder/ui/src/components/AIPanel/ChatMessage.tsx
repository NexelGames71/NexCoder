import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { ChatMessage as MessageType, DiffHunk } from '../../types';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useChatStore } from '../../store/useChatStore';
import { agentApprovePatchset, agentRejectDiff, readFile } from '../../services/bridge';
import AgentTurnPanel from './AgentTurnPanel';
import FinalAnswerCard from './FinalAnswerCard';
import {
  Check, ChevronDown, ChevronRight, FileCode2, FileText, FolderMinus, FolderPlus,
  ImageIcon, MoveRight, RotateCcw, Timer
} from 'lucide-react';

interface ChatMessageProps {
  message: MessageType;
  isLatest?: boolean;
}

function getLanguageFromExtension(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'py': return 'python';
    case 'js': case 'jsx': return 'javascript';
    case 'ts': case 'tsx': return 'typescript';
    case 'html': return 'html';
    case 'css': return 'css';
    case 'json': return 'json';
    case 'md': return 'markdown';
    default: return 'plaintext';
  }
}

function ActiveTimer({ startedAt }: { startedAt: number }) {
  const [seconds, setSeconds] = React.useState(0);

  React.useEffect(() => {
    setSeconds(Math.floor((Date.now() - startedAt) / 1000));
    const timer = setInterval(() => {
      setSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  const label = seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;

  return (
    <div className="console-timer-row">
      <Timer size={11} className="spin-slow" />
      <span>Working · {label}</span>
    </div>
  );
}

function CreatedFileCard({ diff, onOpen }: { diff: DiffHunk; onOpen: (path: string) => void }) {
  const name = diff.file.split(/[\\/]/).pop() || '';
  const ext = name.split('.').pop()?.toUpperCase() || 'FILE';
  const isImage = ['PNG', 'JPG', 'JPEG', 'GIF', 'WEBP', 'SVG'].includes(ext);

  return (
    <div className="console-artifact-card">
      <div className="artifact-icon-box">
        {isImage ? (
          <ImageIcon size={14} style={{ color: 'var(--accent-blue)' }} />
        ) : (
          <FileText size={14} style={{ color: 'var(--accent-purple)' }} />
        )}
      </div>
      <div className="artifact-info">
        <div className="artifact-name">{name}</div>
        <div className="artifact-type">{isImage ? 'Image' : 'File'} · {ext}</div>
      </div>
      <button type="button" className="btn btn-ghost artifact-open-btn" onClick={() => onOpen(diff.file)}>
        Open <ChevronRight size={10} />
      </button>
    </div>
  );
}

function DiffsCard({ diffs, onReview, taskId }: { diffs: DiffHunk[]; onReview: (id: string) => void; taskId?: string }) {
  const {
    removePendingDiff,
    clearPendingDiffs,
    updateTaskStatus,
    addTaskStepItem,
  } = useChatStore();
  const { replaceFileContent } = useEditorStateStore();
  const [expanded, setExpanded] = React.useState(false);
  const [applying, setApplying] = React.useState(false);

  const getLineCounts = (diffDisplay?: string) => {
    let added = 0;
    let deleted = 0;
    if (diffDisplay) {
      for (const line of diffDisplay.split('\n')) {
        if (line.startsWith('+') && !line.startsWith('+++')) added++;
        else if (line.startsWith('-') && !line.startsWith('---')) deleted++;
      }
    }
    return { added, deleted };
  };

  const handleUndo = async () => {
    for (const diff of diffs) {
      try {
        const res = await agentRejectDiff(diff.id);
        if (res?.success) removePendingDiff(diff.id);
      } catch (e) {
        console.error(e);
      }
    }
  };

  const handleApplyAll = async () => {
    if (applying) return;
    setApplying(true);
    try {
      const result = await agentApprovePatchset(diffs.map((diff) => diff.id));
      if (!result?.success) return;

      for (const diff of diffs) {
        if (diff.action === 'delete' || diff.action === 'mkdir' || diff.action === 'rmdir') continue;
        const readResult = await readFile(diff.file);
        if (!readResult?.success) continue;
        replaceFileContent({
          path: diff.file,
          name: diff.file.split(/[\\/]/).pop() || diff.file,
          content: readResult.content || '',
          language: getLanguageFromExtension(diff.file),
          isDirty: false,
        }, diff.operation === 'move' ? diff.source : undefined);
      }

      clearPendingDiffs();
      if (taskId) {
        updateTaskStatus(taskId, 'complete', `Applied and verified ${diffs.length} file change(s)`);
        addTaskStepItem(taskId, {
          id: `${taskId}-validation-${Date.now()}`,
          type: 'validation',
          tool: 'apply_patchset',
          label: 'Apply and verify changes',
          target: `${diffs.length} file(s)`,
          status: 'completed',
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          result_summary: 'All reviewed files were written and verified',
          error: null,
          timestamp: Date.now(),
        });
      }
    } finally {
      setApplying(false);
    }
  };

  const visibleDiffs = expanded ? diffs : diffs.slice(0, 3);

  return (
    <div className="console-diffs-card">
      <div className="diffs-card-header">
        <div className="diffs-card-title">
          Prepared {diffs.length} change{diffs.length !== 1 ? 's' : ''}
        </div>
        <div className="diffs-card-actions">
          <button type="button" className="btn btn-ghost diffs-undo-btn" onClick={handleUndo}>
            <RotateCcw size={11} />
            Undo
          </button>
          <button type="button" className="btn btn-primary diffs-review-btn" onClick={() => onReview(diffs[0].id)}>
            Review
          </button>
          <button type="button" className="btn btn-primary diffs-review-btn" onClick={handleApplyAll} disabled={applying}>
            <Check size={11} />
            {applying ? 'Applying' : 'Apply all'}
          </button>
        </div>
      </div>
      <div className="divider" style={{ margin: '8px 0', opacity: 0.05 }} />
      <div className="diffs-card-list">
        {visibleDiffs.map((diff) => {
          const name = diff.file.split(/[\\/]/).pop() || '';
          const { added, deleted } = getLineCounts(diff.diff_display);
          const operationLabel = diff.operation === 'move'
            ? `${diff.source || 'File'} -> ${diff.file}`
            : diff.action === 'mkdir'
              ? `Create ${diff.file}`
              : diff.action === 'rmdir'
                ? `Remove ${diff.file}`
                : diff.file;
          const OperationIcon = diff.operation === 'move'
            ? MoveRight
            : diff.action === 'mkdir'
              ? FolderPlus
              : diff.action === 'rmdir'
                ? FolderMinus
                : FileCode2;
          return (
            <button
              type="button"
              key={diff.id}
              className="diffs-list-item"
              onClick={() => onReview(diff.id)}
            >
              <OperationIcon size={11} />
              <span className="diff-item-name" title={operationLabel}>
                {diff.operation === 'move' ? operationLabel : name}
              </span>
              <div className="diff-item-stats">
                {added > 0 && <span className="diff-stat-add">+{added}</span>}
                {deleted > 0 && <span className="diff-stat-del">-{deleted}</span>}
              </div>
            </button>
          );
        })}
      </div>
      {diffs.length > 3 && (
        <button type="button" className="diffs-toggle-link" onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Show less' : `Show ${diffs.length - 3} more`}
          {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        </button>
      )}
    </div>
  );
}

function stripToolCalls(text: string) {
  return text
    .replace(/<tool_call\s+name="[^"]+">[\s\S]*?<\/tool_call>/g, '')
    .trim();
}

function normalizeText(text: string) {
  return text.replace(/\s+/g, ' ').trim();
}

export default function ChatMessage({ message, isLatest = false }: ChatMessageProps) {
  const isUser = message.role === 'user';
  const { pendingDiffs, tasks, scanStepsByTask, setActiveDiffId } = useChatStore();

  const task = useMemo(
    () => tasks.find((t) => t.id === message.id),
    [tasks, message.id],
  );

  const scanSteps = task ? scanStepsByTask[task.id] || [] : [];

  const handleReviewDiff = (diffId: string) => {
    setActiveDiffId(diffId);
  };

  if (isUser) {
    return (
      <div className="chat-turn chat-turn-user">
        <div className="chat-bubble chat-bubble-user">
          {message.content}
        </div>
      </div>
    );
  }

  const rawVisibleText = stripToolCalls(message.content);
  const finalSummary = task?.finalAnswer?.summary || '';
  const isStructuredOnlyTask = !!task?.finalAnswer && ['scan', 'question', 'review'].includes(String(task.taskType || task.mode));
  const isDuplicateFinalSummary = !!finalSummary && normalizeText(rawVisibleText) === normalizeText(finalSummary);
  const visibleText = (isStructuredOnlyTask || isDuplicateFinalSummary) ? '' : rawVisibleText;
  const showThinking = isLatest && message.isStreaming && !visibleText && !task;

  return (
    <div className="chat-turn chat-turn-assistant">
      {task && (
        <AgentTurnPanel
          task={task}
          isActive={isLatest && !!message.isStreaming}
          scanSteps={scanSteps}
        />
      )}

      {showThinking && (
        <div className="chat-thinking">
          <span className="chat-thinking-dot" />
          <span className="chat-thinking-dot" />
          <span className="chat-thinking-dot" />
          <span>Thinking…</span>
        </div>
      )}

      {isLatest && message.isStreaming && !task && (
        <ActiveTimer startedAt={message.timestamp} />
      )}

      {visibleText && (
        <div className="chat-bubble-assistant chat-markdown">
          <ReactMarkdown>{visibleText}</ReactMarkdown>
          {message.isStreaming && (
            <span className="streaming-cursor" aria-hidden="true">▌</span>
          )}
        </div>
      )}

      {isLatest && pendingDiffs.length > 0 && (
        <div className="console-artifacts-area">
          <DiffsCard diffs={pendingDiffs} onReview={handleReviewDiff} taskId={task?.id} />
        </div>
      )}

      {task?.finalAnswer && (
        <FinalAnswerCard answer={task.finalAnswer} taskType={task.taskType} />
      )}
    </div>
  );
}
