import React, { useEffect, useState } from 'react';
import { GitBranch, Plus, Minus, RefreshCw, Loader2, Check } from 'lucide-react';
import { useGitStore } from '../../store/useGitStore';
import { useProjectStore } from '../../store/useProjectStore';
import { gitStatus, gitStage, gitCommit } from '../../services/bridge';

export default function GitPanel() {
  const { status, setStatus, isLoading, setLoading } = useGitStore();
  const { projectPath } = useProjectStore();
  const [message, setMessage] = useState('');
  const [isCommitting, setIsCommitting] = useState(false);

  const fetchStatus = async () => {
    if (!projectPath) return;
    setLoading(true);
    try {
      const res = await gitStatus(projectPath);
      if (res && res.success) {
        setStatus(res.status);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, [projectPath]);

  const handleStage = async (file: string, stage: boolean) => {
    if (!projectPath) return;
    try {
      await gitStage(projectPath, [file]);
      await fetchStatus();
    } catch (err) {
      console.error(err);
    }
  };

  const handleCommit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || !projectPath) return;

    setIsCommitting(true);
    try {
      const res = await gitCommit(projectPath, message);
      if (res && res.success) {
        setMessage('');
        await fetchStatus();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsCommitting(false);
    }
  };

  if (!projectPath) {
    return (
      <div className="empty-state" style={{ height: '100%' }}>
        <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>Open a project to see git status</p>
      </div>
    );
  }

  if (status && !status.isRepo) {
    return (
      <div className="empty-state" style={{ height: '100%' }}>
        <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>Not a git repository</p>
      </div>
    );
  }

  return (
    <div className="sidebar-panel">
      <div className="sidebar-header">
        <span>Source Control</span>
        <button className="btn btn-ghost btn-icon tooltip" data-tooltip="Refresh git" onClick={fetchStatus}>
          {isLoading ? <Loader2 size={12} className="spin" /> : <RefreshCw size={12} />}
        </button>
      </div>

      <div style={{ padding: 'var(--space-3)', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
          <GitBranch size={14} />
          <span>Branch: {status?.branch || 'none'}</span>
        </div>
      </div>

      <div className="git-changes-list flex-1 overflow-auto" style={{ padding: 'var(--space-3)' }}>
        {/* Staged Changes */}
        {status && status.staged.length > 0 && (
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <h4 style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
              Staged Changes
            </h4>
            {status.staged.map((c: any) => (
              <div key={c.path} className="git-change-item">
                <span className="truncate" style={{ flex: 1 }}>{c.path}</span>
                <button
                  className="btn btn-ghost btn-icon tooltip"
                  data-tooltip="Unstage"
                  onClick={() => handleStage(c.path, false)}
                >
                  <Minus size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Changes */}
        {status && status.changed.length > 0 && (
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <h4 style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
              Changes
            </h4>
            {status.changed.map((c: any) => (
              <div key={c.path} className="git-change-item">
                <span className="truncate" style={{ flex: 1 }}>{c.path}</span>
                <button
                  className="btn btn-ghost btn-icon tooltip"
                  data-tooltip="Stage file"
                  onClick={() => handleStage(c.path, true)}
                >
                  <Plus size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Untracked */}
        {status && status.untracked.length > 0 && (
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <h4 style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 'var(--space-2)' }}>
              Untracked Files
            </h4>
            {status.untracked.map((file: string) => (
              <div key={file} className="git-change-item">
                <span className="truncate" style={{ flex: 1 }}>{file}</span>
                <button
                  className="btn btn-ghost btn-icon tooltip"
                  data-tooltip="Stage file"
                  onClick={() => handleStage(file, true)}
                >
                  <Plus size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {status && status.changed.length === 0 && status.staged.length === 0 && status.untracked.length === 0 && (
          <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)', paddingTop: 'var(--space-6)' }}>
            No changes detected
          </p>
        )}
      </div>

      {/* Commit Input */}
      {status && (status.staged.length > 0 || status.changed.length > 0 || status.untracked.length > 0) && (
        <form onSubmit={handleCommit} style={{ padding: 'var(--space-3)', borderTop: '1px solid var(--border)', background: 'var(--bg-deep)' }}>
          <textarea
            className="input"
            placeholder="Commit message... (Ctrl+Enter to commit)"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            style={{ minHeight: '60px', resize: 'none', marginBottom: 'var(--space-2)', fontFamily: 'var(--font-ui)', fontSize: 'var(--font-size-xs)' }}
          />
          <button className="btn btn-primary w-full" type="submit" disabled={isCommitting || !message.trim()}>
            {isCommitting ? <Loader2 size={12} className="spin" /> : <><Check size={12} /> Commit</>}
          </button>
        </form>
      )}
    </div>
  );
}
