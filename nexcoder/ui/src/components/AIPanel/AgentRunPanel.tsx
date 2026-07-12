import { useState } from 'react';
import { Terminal, FilePenLine, FilePlus2, FileText, Search, FolderOpen, BookOpen, ListChecks, Wrench, ChevronRight, ChevronDown } from 'lucide-react';
import { useAgentRunStore, TranscriptItem } from '../../store/useAgentRunStore';
import { agentPermissionResponse, agentRevertFile, agentRevertRun } from '../../services/bridge';

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="step-expand diff-view">
      {diff.split('\n').map((line, i) => {
        const cls = line.startsWith('+') && !line.startsWith('+++') ? 'diff-add'
          : line.startsWith('-') && !line.startsWith('---') ? 'diff-del'
          : line.startsWith('@@') ? 'diff-hunk' : 'diff-ctx';
        return <div key={i} className={cls}>{line || ' '}</div>;
      })}
    </pre>
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

export default function AgentRunPanel() {
  const { transcript, todos, permission, checkpointId, mutatedFiles,
          finalText, status, runActive } = useAgentRunStore();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  if (!runActive && !status) return null;

  const toggle = (index: number) => setExpanded((prev) => {
    const next = new Set(prev);
    if (next.has(index)) { next.delete(index); } else { next.add(index); }
    return next;
  });

  return (
    <div className="agent-run">
      {todos.length > 0 && (
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
        const { icon: Icon, label, detail } = describeStep(item);
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
              <Icon size={13} className="step-icon" />
              <span className="step-label">{label}</span>
              {detail && <code className="step-detail">{detail}</code>}
              {item.done && !item.success && item.summary && (
                <span className="step-error">{item.summary}</span>
              )}
              {!item.done && <span className="step-spinner">…</span>}
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
