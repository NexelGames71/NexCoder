import React, { useEffect, useState } from 'react';
import { FolderOpen, GitBranch, LoaderCircle, X } from 'lucide-react';
import { cloneRepository, onCloneCompleted, selectFolderDialog } from '../../services/bridge';
import './CloneRepositoryDialog.css';

interface CloneRepositoryDialogProps {
  onClose: () => void;
}

export default function CloneRepositoryDialog({ onClose }: CloneRepositoryDialogProps) {
  const [repositoryUrl, setRepositoryUrl] = useState('');
  const [destinationParent, setDestinationParent] = useState('');
  const [directoryName, setDirectoryName] = useState('');
  const [cloneId, setCloneId] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!cloneId) return undefined;
    const disconnect = onCloneCompleted((payload) => {
      try {
        const result = JSON.parse(payload);
        const completedCloneId = result.clone_id || result?.error_envelope?.details?.clone_id;
        if (completedCloneId && completedCloneId !== cloneId) return;
        if (!result.success) {
          setError(result.error || 'Repository clone failed.');
          setStatus('');
          setCloneId('');
          return;
        }
        setStatus('Repository cloned. Opening project...');
        window.setTimeout(onClose, 450);
      } catch (parseError) {
        setError(String(parseError));
        setStatus('');
        setCloneId('');
      }
    });
    return disconnect;
  }, [cloneId, onClose]);

  const handleBrowse = async () => {
    const folder = await selectFolderDialog('Clone Repository Into');
    if (typeof folder === 'string' && folder) {
      setDestinationParent(folder);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!repositoryUrl.trim() || cloneId) return;
    setError('');
    setStatus('Starting clone...');
    const result = await cloneRepository(
      repositoryUrl.trim(),
      destinationParent.trim(),
      directoryName.trim(),
    );
    if (!result?.success) {
      setError(result?.error || 'Repository clone could not start.');
      setStatus('');
      return;
    }
    setCloneId(result.clone_id || '');
    setStatus(`Cloning into ${result.target || 'selected folder'}...`);
  };

  const busy = Boolean(cloneId);

  return (
    <div className="clone-dialog-backdrop" role="presentation">
      <form className="clone-dialog" onSubmit={handleSubmit}>
        <div className="clone-dialog-header">
          <div>
            <GitBranch size={16} />
            <span>Clone Repository</span>
          </div>
          <button type="button" onClick={onClose} disabled={busy} title="Close" aria-label="Close">
            <X size={15} />
          </button>
        </div>

        <label className="clone-field">
          <span>Repository URL</span>
          <input
            autoFocus
            value={repositoryUrl}
            onChange={(event) => setRepositoryUrl(event.target.value)}
            placeholder="https://github.com/org/repo.git"
            disabled={busy}
          />
        </label>

        <label className="clone-field">
          <span>Destination Folder</span>
          <div className="clone-destination-row">
            <input
              value={destinationParent}
              onChange={(event) => setDestinationParent(event.target.value)}
              placeholder="Default: ~/NexCoder Projects"
              disabled={busy}
            />
            <button type="button" onClick={handleBrowse} disabled={busy} title="Browse">
              <FolderOpen size={14} />
            </button>
          </div>
        </label>

        <label className="clone-field">
          <span>Folder Name</span>
          <input
            value={directoryName}
            onChange={(event) => setDirectoryName(event.target.value)}
            placeholder="Auto-detected from repository"
            disabled={busy}
          />
        </label>

        {error && <div className="clone-error" role="alert">{error}</div>}
        {status && (
          <div className="clone-status" role="status">
            {busy && <LoaderCircle size={13} />}
            <span>{status}</span>
          </div>
        )}

        <div className="clone-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || !repositoryUrl.trim()}>
            {busy ? 'Cloning...' : 'Clone and Open'}
          </button>
        </div>
      </form>
    </div>
  );
}
