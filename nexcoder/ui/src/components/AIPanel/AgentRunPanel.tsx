import { useAgentRunStore } from '../../store/useAgentRunStore';
import { agentPermissionResponse, agentRevertFile, agentRevertRun } from '../../services/bridge';

export default function AgentRunPanel() {
  const {
    steps, todos, permission, checkpointId, mutatedFiles,
    streamText, finalText, status, runActive,
  } = useAgentRunStore();

  if (!runActive && !status) return null;

  return (
    <div className="agent-run-panel">
      {todos.length > 0 && (
        <div className="agent-todos">
          {todos.map((todo) => (
            <div key={todo.id} className={`agent-todo agent-todo-${todo.status}`}>
              <span className="agent-todo-mark">
                {todo.status === 'completed' ? '☑' : todo.status === 'in_progress' ? '▸' : '☐'}
              </span>
              <span>{todo.content}</span>
            </div>
          ))}
        </div>
      )}
      {steps.map((step, index) => (
        <div key={index} className="agent-step">
          <span className={step.done ? (step.success ? 'step-ok' : 'step-fail') : 'step-running'}>
            {step.done ? (step.success ? '✓' : '✗') : '…'}
          </span>
          <span className="step-tool">{step.tool}</span>
          <span className="step-summary">{step.summary ?? ''}</span>
        </div>
      ))}
      {streamText && <div className="agent-stream-text">{streamText}</div>}
      {permission && (
        <div className="agent-permission-card">
          <div className="perm-title">Run command?</div>
          <code className="perm-command">{permission.command}</code>
          <div className="perm-actions">
            <button className="btn" onClick={() => agentPermissionResponse(permission.id, 'allow')}>Allow</button>
            <button className="btn" onClick={() => agentPermissionResponse(permission.id, 'allow_always')}>Always allow</button>
            <button className="btn" onClick={() => agentPermissionResponse(permission.id, 'deny')}>Deny</button>
          </div>
        </div>
      )}
      {!runActive && status && (
        <div className="agent-run-result">
          <div className={`run-status run-status-${status}`}>{status}</div>
          {finalText && <div className="run-final-text">{finalText}</div>}
          {mutatedFiles.length > 0 && checkpointId && (
            <div className="run-changed-files">
              {mutatedFiles.map((file) => (
                <div key={file} className="changed-file">
                  <span>{file}</span>
                  <button className="btn btn-ghost" onClick={() => agentRevertFile(checkpointId, file)}>Revert</button>
                </div>
              ))}
              <button className="btn revert-all" onClick={() => agentRevertRun(checkpointId)}>Revert all</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
