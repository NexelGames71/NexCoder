import React from 'react';
import { DiffEditor } from '@monaco-editor/react';
import { Check, FolderMinus, FolderPlus, MoveRight, X } from 'lucide-react';
import { DiffHunk } from '../../types';
import { agentApproveDiff, agentRejectDiff, readFile } from '../../services/bridge';
import { useChatStore } from '../../store/useChatStore';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import { toMonacoTheme } from '../../services/monacoSetup';
import { getLanguageFromExtension } from '../../utils/languageMap';

interface DiffViewerProps {
  diff: DiffHunk;
}

export default function DiffViewer({ diff }: DiffViewerProps) {
  const { removePendingDiff } = useChatStore();
  const { replaceFileContent } = useEditorStateStore();

  const refreshAcceptedFile = async () => {
    if (diff.action === 'mkdir' || diff.action === 'rmdir' || diff.action === 'delete') return;
    const readResult = await readFile(diff.file);
    if (!readResult?.success) return;

    const extension = diff.file.includes('.') ? diff.file.split('.').pop() || '' : '';
    replaceFileContent({
      path: diff.file,
      name: diff.file.split(/[\\/]/).pop() || diff.file,
      content: readResult.content || '',
      language: getLanguageFromExtension(extension),
      isDirty: false,
    }, diff.operation === 'move' ? diff.source : undefined);
  };

  const structuralChange = diff.operation === 'move'
    || diff.action === 'mkdir'
    || diff.action === 'rmdir';

  const structuralDetails = diff.operation === 'move'
    ? {
        icon: <MoveRight size={24} />,
        title: 'Move file',
        description: `${diff.source || 'Unknown source'} -> ${diff.file}`,
      }
    : diff.action === 'mkdir'
      ? {
          icon: <FolderPlus size={24} />,
          title: 'Create folder',
          description: diff.file,
        }
      : {
          icon: <FolderMinus size={24} />,
          title: 'Remove empty folder',
          description: diff.file,
        };

  const handleApprove = async () => {
    try {
      const res = await agentApproveDiff(diff.id);
      if (res && res.success) {
        await refreshAcceptedFile();
        removePendingDiff(diff.id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleReject = async () => {
    try {
      const res = await agentRejectDiff(diff.id);
      if (res && res.success) {
        removePendingDiff(diff.id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 'var(--space-2) var(--space-4)', background: 'var(--bg-panel)', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontSize: 'var(--font-size-sm)', fontWeight: '600' }}>
          Review Changes: {diff.file}
        </span>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button className="btn btn-ghost" onClick={handleReject} style={{ color: 'var(--accent-red)' }}>
            <X size={14} /> Reject
          </button>
          <button className="btn btn-primary" onClick={handleApprove}>
            <Check size={14} /> Accept
          </button>
        </div>
      </div>

      <div style={{ flex: 1 }}>
        {structuralChange ? (
          <div className="structural-review">
            <div className="structural-review-icon">{structuralDetails.icon}</div>
            <div>
              <div className="structural-review-title">{structuralDetails.title}</div>
              <div className="structural-review-path">{structuralDetails.description}</div>
              <div className="structural-review-note">
                This filesystem operation will run only after approval.
              </div>
            </div>
          </div>
        ) : (
        <DiffEditor
          height="100%"
          theme={toMonacoTheme(useEditorSettingsStore.getState().settings.theme)}
          original={diff.original_content || ''}
          modified={diff.content || diff.diff_display || ''}
          language={diff.language || 'plaintext'}
          options={{
            renderSideBySide: true,
            readOnly: true,
            originalEditable: false,
            automaticLayout: true,
          }}
        />
        )}
      </div>
    </div>
  );
}

