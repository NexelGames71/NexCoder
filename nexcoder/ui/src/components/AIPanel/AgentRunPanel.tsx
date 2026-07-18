import { useEffect, useState } from 'react';

const WORKING_WORDS = ['Thinking', 'Working', 'Reasoning'];

function WorkingIndicator() {
  const [word, setWord] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setWord((w) => (w + 1) % WORKING_WORDS.length), 4000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="agent-working">
      <span className="working-dot" />
      <span className="working-dot" />
      <span className="working-dot" />
      <span className="working-word">{WORKING_WORDS[word]}…</span>
    </div>
  );
}
import { Terminal, FilePenLine, FilePlus2, FileText, Search, FolderOpen, BookOpen, ListChecks, Wrench, ChevronRight, ChevronDown } from 'lucide-react';
import { useAgentRunStore, TranscriptItem } from '../../store/useAgentRunStore';
import { agentPermissionResponse, agentRevertFile, agentRevertRun } from '../../services/bridge';

interface DiffRow { type: 'add' | 'del' | 'ctx' | 'hunk'; text: string; oldNo?: number; newNo?: number; }

// Parse a unified diff into rendered rows with gutter line numbers,
// dropping the ---/+++ file headers (the row already names the file).
function parseDiffRows(diff: string): DiffRow[] {
  const rows: DiffRow[] = [];
  let oldNo = 0, newNo = 0;
  for (const line of diff.split('\n')) {
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ')) continue;
    if (line.startsWith('@@')) {
      const m = /@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line);
      if (m) { oldNo = parseInt(m[1], 10); newNo = parseInt(m[2], 10); }
      rows.push({ type: 'hunk', text: line.replace(/@@.*@@/, '').trim() || '⋯' });
      continue;
    }
    if (line.startsWith('+')) { rows.push({ type: 'add', text: line.slice(1), newNo }); newNo++; }
    else if (line.startsWith('-')) { rows.push({ type: 'del', text: line.slice(1), oldNo }); oldNo++; }
    else { rows.push({ type: 'ctx', text: line.slice(1), oldNo, newNo }); oldNo++; newNo++; }
  }
  return rows;
}

function DiffView({ diff }: { diff: string }) {
  const rows = parseDiffRows(diff);
  return (
    <div className="diff-view">
      {rows.map((row, i) => (
        <div key={i} className={`diff-row diff-${row.type}`}>
          <span className="diff-gutter">{row.type === 'add' ? '' : row.oldNo ?? ''}</span>
          <span className="diff-gutter">{row.type === 'del' ? '' : row.newNo ?? ''}</span>
          <span className="diff-sign">{row.type === 'add' ? '+' : row.type === 'del' ? '−' : ' '}</span>
          <span className="diff-code">{row.text || ' '}</span>
        </div>
      ))}
    </div>
  );
}

// Codex-style row: quiet verb phrase describing the action, not raw tool IO.
function describeStep(item: Extract<TranscriptItem, { kind: 'step' }>): { icon: any; label: string; detail: string } {
  const args = item.args ?? {};
  switch (item.tool) {
    case 'run_command': return { icon: Terminal, label: 'Ran command', detail: String(args.command ?? '') };
    case 'edit_file': return { icon: FilePenLine, label: 'Edited file', detail: String(args.path ?? '') };
    case 'write_file': return { icon: FilePlus2, label: 'Created file', detail: String(args.path ?? '') };
    case 'read_file': return { icon: FileText, label: 'Read file', detail: String(args.path ?? '') };
    case 'grep': return { icon: Search, label: 'Searched code', detail: String(args.pattern ?? '') };
    case 'glob': return { icon: Search, label: 'Found files', detail: String(args.pattern ?? '') };
    case 'list_directory': return { icon: FolderOpen, label: 'Listed directory', detail: String(args.path ?? '.') };
    case 'create_directory': return { icon: FolderOpen, label: 'Created directory', detail: String(args.path ?? '') };
    case 'load_skill': return { icon: BookOpen, label: 'Loaded skill', detail: String(args.id ?? '') };
    case 'todo_write': return { icon: ListChecks, label: 'Updated plan', detail: '' };
    default: return { icon: Wrench, label: item.tool, detail: '' };
  }
}

export default function AgentRunPanel({ runId }: { runId: string }) {
  const run = useAgentRunStore((state) => state.runs[runId]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (!run) return null;
  const { transcript, todos, permission, checkpointId, mutatedFiles,
          finalText, status, runActive } = run;

  const toggle = (index: number) => setExpanded((prev) => {
    const next = new Set(prev);
    if (next.has(index)) { next.delete(index); } else { next.add(index); }
    return next;
  });

  // The live plan renders pinned above the composer (AIPanel) while the
  // run is active; inline it only afterwards so finished transcripts
  // still show what the plan was.
  const showInlineTodos = !runActive && todos.length > 0;

  return (
    <div className="agent-run">
      {showInlineTodos && (
        <div className="agent-run-todos">
          {todos.map((todo) => (
            <div key={todo.id} className={`agent-run-todo agent-run-todo-${todo.status}`}>
              <span className="todo-mark">
                {todo.status === 'completed' ? '✓' : todo.status === 'in_progress' ? '›' : '○'}
              </span>
              <span>{todo.content}</span>
            </div>
          ))}
        </div>
      )}

      {transcript.map((item, index) => {
        if (item.kind === 'text') {
          return item.text.trim()
            ? <p key={index} className="agent-run-prose">{item.text}</p>
            : null;
        }
        if (item.kind === 'notice') {
          return <div key={index} className="agent-run-notice">{item.text}</div>;
        }
        const { icon: Icon, label, detail } = describeStep(item);
        const streaming = !item.done && item.streamingChars !== undefined;
        const expandable = Boolean((item.output && item.output.length) || item.diff);
        const isOpen = expanded.has(index);
        return (
          <div key={index}>
            <div
              className={`agent-run-step ${item.done ? (item.success ? 'ok' : 'fail') : 'running'} ${expandable ? 'expandable' : ''}`}
              onClick={expandable ? () => toggle(index) : undefined}
            >
              {expandable
                ? (isOpen ? <ChevronDown size={12} className="step-chevron" /> : <ChevronRight size={12} className="step-chevron" />)
                : <span className="step-chevron-spacer" />}
              <Icon size={13} className={`step-icon ${streaming ? 'streaming' : ''}`} />
              <span className="step-label">{streaming ? 'Writing' : label}</span>
              {detail && <code className="step-detail">{detail}</code>}
              {streaming && (
                <span className="step-streaming">
                  {(item.streamingChars! / 1000).toFixed(1)}k chars…
                </span>
              )}
              {(typeof item.added === 'number' || typeof item.removed === 'number') && (
                <span className="step-diffstat">
                  <span className="diffstat-add">+{item.added ?? 0}</span>
                  <span className="diffstat-del">−{item.removed ?? 0}</span>
                </span>
              )}
              {item.done && !item.success && item.summary && (
                <span className="step-error">{item.summary}</span>
              )}
              {!item.done && !streaming && <span className="step-spinner">…</span>}
            </div>
            {isOpen && item.diff && <DiffView diff={item.diff} />}
            {isOpen && !item.diff && item.output && (
              <pre className="step-expand">{item.output.join('\n')}</pre>
            )}
          </div>
        );
      })}

      {permission && (
        <div className="agent-run-permission">
          <div className="perm-title">Allow this command?</div>
          <code className="perm-command">{permission.command}</code>
          <div className="perm-actions">
            <button className="btn" onClick={() => agentPermissionResponse(permission.id, 'allow')}>Allow</button>
            <button className="btn" onClick={() => agentPermissionResponse(permission.id, 'allow_always')}>Always allow</button>
            <button className="btn" onClick={() => agentPermissionResponse(permission.id, 'deny')}>Deny</button>
          </div>
        </div>
      )}

      {runActive && !permission && <WorkingIndicator />}

      {!runActive && status && (
        <div className="agent-run-footer">
          {finalText && <p className="agent-run-prose">{finalText}</p>}
          {status !== 'completed' && <div className={`run-status run-status-${status}`}>{status}</div>}
          {mutatedFiles.length > 0 && checkpointId && (
            <div className="agent-run-files">
              <div className="files-header">{mutatedFiles.length} file{mutatedFiles.length > 1 ? 's' : ''} changed</div>
              {mutatedFiles.map((file) => (
                <div key={file} className="changed-file">
                  <span>{file}</span>
                  <button className="btn btn-ghost" onClick={() => agentRevertFile(checkpointId, file)}>Revert</button>
                </div>
              ))}
              <button className="btn btn-ghost revert-all" onClick={() => agentRevertRun(checkpointId)}>Revert all</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
