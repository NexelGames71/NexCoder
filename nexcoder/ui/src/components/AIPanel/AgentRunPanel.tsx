import { Terminal, FilePenLine, FilePlus2, FileText, Search, FolderOpen, BookOpen, ListChecks, Wrench } from 'lucide-react';
import { useAgentRunStore, TranscriptItem } from '../../store/useAgentRunStore';
import { agentPermissionResponse, agentRevertFile, agentRevertRun } from '../../services/bridge';

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

  if (!runActive && !status) return null;

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
        return (
          <div key={index} className={`agent-run-step ${item.done ? (item.success ? 'ok' : 'fail') : 'running'}`}>
            <Icon size={13} className="step-icon" />
            <span className="step-label">{label}</span>
            {detail && <code className="step-detail">{detail}</code>}
            {item.done && !item.success && item.summary && (
              <span className="step-error">{item.summary}</span>
            )}
            {!item.done && <span className="step-spinner">…</span>}
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
