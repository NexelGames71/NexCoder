import React, { useMemo, useState } from 'react';
import {
  Bot,
  Check,
  Copy,
  ExternalLink,
  FileArchive,
  FileText,
  FolderOpen,
  RefreshCw,
  Save,
  Search,
  Trash2,
} from 'lucide-react';
import { useArtifactStore } from '../../store/useArtifactStore';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { readFile, writeFile } from '../../services/bridge';
import { serializeArtifactMarkdown, suggestedArtifactPath } from '../../services/artifactRepository';
import { loadComposerPrompt } from '../../utils/diagnosticPrompt';
import type { AgentArtifact } from '../../types';

function artifactTypeLabel(type: AgentArtifact['type']): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value: number): string {
  return new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default function ArtifactsPanel() {
  const artifacts = useArtifactStore((state) => state.artifacts);
  const isHydrating = useArtifactStore((state) => state.isHydrating);
  const lastError = useArtifactStore((state) => state.lastError);
  const activeProjectPath = useArtifactStore((state) => state.activeProjectPath);
  const hydrateProject = useArtifactStore((state) => state.hydrateProject);
  const markSaved = useArtifactStore((state) => state.markSaved);
  const removeArtifact = useArtifactStore((state) => state.removeArtifact);
  const clearProjectArtifacts = useArtifactStore((state) => state.clearProjectArtifacts);
  const openFile = useEditorStateStore((state) => state.openFile);
  const [query, setQuery] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [panelError, setPanelError] = useState<string | null>(null);

  const visible = useMemo(() => {
    const lower = query.trim().toLowerCase();
    if (!lower) return artifacts;
    return artifacts.filter((artifact) => [
      artifact.title,
      artifact.summary,
      artifact.type,
      artifact.files.join(' '),
      artifact.savedPath || '',
      artifact.sourcePrompt || '',
    ].join(' ').toLowerCase().includes(lower));
  }, [artifacts, query]);

  const active = visible.find((artifact) => artifact.id === activeId) || visible[0] || null;

  const openArtifact = (artifact: AgentArtifact) => {
    openFile({
      path: `__nexcoder_artifacts__/${artifact.id}.md`,
      name: `${artifact.title}.md`,
      content: artifact.content,
      language: 'markdown',
      isDirty: false,
      kind: 'artifact',
      resourceId: artifact.id,
    });
  };

  const saveArtifact = async (artifact: AgentArtifact) => {
    setSavingId(artifact.id);
    setPanelError(null);
    try {
      const path = artifact.savedPath || suggestedArtifactPath(artifact);
      const result = await writeFile(path, serializeArtifactMarkdown(artifact));
      if (result?.success) {
        markSaved(artifact.id, result.path || path);
      } else {
        setPanelError(result?.error || 'Could not save artifact.');
      }
    } finally {
      setSavingId(null);
    }
  };

  const openSavedArtifact = async (artifact: AgentArtifact) => {
    const path = artifact.savedPath || suggestedArtifactPath(artifact);
    setPanelError(null);
    const result = await readFile(path);
    if (!result?.success) {
      setPanelError(result?.error || 'Could not open saved artifact file.');
      return;
    }
    openFile({
      path,
      name: path.split(/[\\/]/).pop() || `${artifact.title}.md`,
      content: result.content || '',
      language: 'markdown',
      isDirty: false,
      kind: 'file',
    });
  };

  const copyArtifact = async (artifact: AgentArtifact) => {
    await navigator.clipboard?.writeText(artifact.content);
    setCopiedId(artifact.id);
    window.setTimeout(() => setCopiedId(null), 1200);
  };

  const sendToAgent = (artifact: AgentArtifact) => {
    loadComposerPrompt({
      mode: 'agent',
      content: [
        'Use this artifact as context and continue from it.',
        '',
        artifact.content,
      ].join('\n'),
    });
  };

  return (
    <div className="artifacts-panel">
      <div className="artifacts-toolbar">
        <div className="artifacts-search">
          <Search size={12} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search artifacts"
          />
        </div>
        <div className="artifacts-toolbar-actions">
          <button
            type="button"
            title="Reload artifacts from .nexcoder/artifacts"
            aria-label="Reload artifacts"
            disabled={isHydrating}
            onClick={() => void hydrateProject(activeProjectPath)}
          >
            <RefreshCw size={12} className={isHydrating ? 'spinning' : ''} />
          </button>
          <button
            type="button"
            title="Clear artifact index for this project"
            aria-label="Clear artifacts"
            disabled={!artifacts.length}
            onClick={clearProjectArtifacts}
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {(lastError || panelError) && (
        <div className="artifacts-error">{panelError || lastError}</div>
      )}

      {visible.length === 0 ? (
        <div className="artifacts-empty">
          <FileArchive size={24} />
          <p>{isHydrating ? 'Loading artifacts...' : 'No artifacts yet.'}</p>
          <span>Completed agent runs create project-backed summaries and patch reports here.</span>
        </div>
      ) : (
        <div className="artifacts-layout">
          <div className="artifacts-list">
            {visible.map((artifact) => (
              <button
                key={artifact.id}
                type="button"
                className={`artifact-list-item ${active?.id === artifact.id ? 'active' : ''}`}
                onClick={() => setActiveId(artifact.id)}
              >
                <FileText size={13} />
                <span>
                  <strong>{artifact.title}</strong>
                  <small>{artifactTypeLabel(artifact.type)} - {formatDate(artifact.updatedAt)}</small>
                </span>
              </button>
            ))}
          </div>

          {active && (
            <div className="artifact-detail">
              <div className="artifact-detail-head">
                <div>
                  <div className="artifact-detail-type">{artifactTypeLabel(active.type)}</div>
                  <h3>{active.title}</h3>
                </div>
                <span className={`artifact-status ${active.status}`}>{active.status}</span>
              </div>

              <p className="artifact-detail-summary">{active.summary}</p>
              <div className="artifact-detail-meta">
                <span>Created {formatDate(active.createdAt)}</span>
                <span>Updated {formatDate(active.updatedAt)}</span>
                <span>{active.savedPath || suggestedArtifactPath(active)}</span>
              </div>

              <div className="artifact-detail-actions">
                <button type="button" onClick={() => openArtifact(active)}>
                  <ExternalLink size={11} /> Open
                </button>
                <button type="button" onClick={() => void openSavedArtifact(active)}>
                  <FolderOpen size={11} /> File
                </button>
                <button type="button" onClick={() => void saveArtifact(active)} disabled={savingId === active.id}>
                  <Save size={11} /> {savingId === active.id ? 'Saving' : 'Save'}
                </button>
                <button type="button" onClick={() => void copyArtifact(active)}>
                  {copiedId === active.id ? <Check size={11} /> : <Copy size={11} />} Copy
                </button>
                <button type="button" onClick={() => sendToAgent(active)}>
                  <Bot size={11} /> Agent
                </button>
                <button type="button" className="danger" onClick={() => removeArtifact(active.id)}>
                  <Trash2 size={11} /> Delete
                </button>
              </div>

              {active.files.length > 0 && (
                <div className="artifact-file-chips">
                  {active.files.slice(0, 8).map((file) => <span key={file}>{file}</span>)}
                  {active.files.length > 8 && <span>+{active.files.length - 8} more</span>}
                </div>
              )}

              <pre className="artifact-preview">{active.content}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
