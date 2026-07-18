import React from 'react';
import { X, SplitSquareHorizontal, PanelRightClose } from 'lucide-react';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { getFileIcon, getFileColor } from '../../utils/fileIcons';
import { OpenFile } from '../../types';

interface EditorTabsProps {
  groupId: string;
  openFiles: OpenFile[];
  activeFile: OpenFile | null;
}

export default function EditorTabs({ groupId, openFiles, activeFile }: EditorTabsProps) {
  const { setActiveFile, closeFile, splitEditor, closeGroup, editorGroups } = useEditorStateStore();
  if (openFiles.length === 0) return null;

  return (
    <div className="editor-tabs-bar">
      <div className="editor-tabs-list">
        {openFiles.map((file) => {
          const isDir = false;
          const ext = '.' + file.path.split('.').pop();
          const Icon = getFileIcon(ext, isDir, false, file.name);
          const color = getFileColor(ext, file.name);
          const isActive = activeFile?.path === file.path;

          return (
            <div
              key={file.path}
              className={`editor-tab-btn ${isActive ? 'active' : ''}`}
              onClick={() => setActiveFile(file.path, groupId)}
            >
              <span style={{ color, display: 'flex', alignItems: 'center' }}>
                <Icon size={14} />
              </span>
              <span>{file.name}</span>
              {file.isDirty && (
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: 'var(--accent-purple)',
                    display: 'inline-block',
                  }}
                />
              )}
              <button
                className="editor-tab-close"
                onClick={(e) => {
                  e.stopPropagation();
                  if (file.isDirty) {
                    const shouldClose = window.confirm(`${file.name} has unsaved changes. Close without saving?`);
                    if (!shouldClose) return;
                  }
                  closeFile(file.path, groupId);
                }}
              >
                <X size={10} />
              </button>
            </div>
          );
        })}
      </div>
      <div className="editor-tabs-actions">
        <button className="btn btn-ghost btn-icon tooltip" data-tooltip="Split editor" onClick={splitEditor}>
          <SplitSquareHorizontal size={13} />
        </button>
        {editorGroups.length > 1 && (
          <button className="btn btn-ghost btn-icon tooltip" data-tooltip="Close editor group" onClick={() => closeGroup(groupId)}>
            <PanelRightClose size={13} />
          </button>
        )}
      </div>
    </div>
  );
}
