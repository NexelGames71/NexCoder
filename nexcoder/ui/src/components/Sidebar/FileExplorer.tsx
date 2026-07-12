import React from 'react';
import { FolderOpen, Plus, FolderPlus, RefreshCw, LocateFixed } from 'lucide-react';
import { useProjectStore } from '../../store/useProjectStore';
import { createDirectory, createFile, getFileTree, openFolderDialog, spawnTerminal } from '../../services/bridge';
import FileTreeItem from './FileTreeItem';
import { selectActiveFile, useEditorStateStore } from '../../store/useEditorStateStore';
import { FileNode } from '../../types';
import ExplorerContextMenu, { ExplorerMenuAction } from './ExplorerContextMenu';
import ExplorerNameDialog from './ExplorerNameDialog';
import { getLanguageFromExtension } from '../../utils/languageMap';

export default function FileExplorer() {
  const { fileTree, projectPath, setFileTree, setLoading } = useProjectStore();
  const activeFile = useEditorStateStore(selectActiveFile);
  const { openFile } = useEditorStateStore();
  const [filter, setFilter] = React.useState('');
  const [revealedPaths, setRevealedPaths] = React.useState<Set<string>>(new Set());
  const [contextMenu, setContextMenu] = React.useState<{ x: number; y: number } | null>(null);
  const [nameDialog, setNameDialog] = React.useState<{
    title: string;
    label: string;
    initialValue: string;
    confirmLabel: string;
    onConfirm: (value: string) => Promise<void> | void;
  } | null>(null);

  const handleOpenFolder = async () => {
    setLoading(true);
    try {
      await openFolderDialog();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (projectPath) {
      try {
        const res = await getFileTree(projectPath);
        if (res && res.success && res.tree) {
          setFileTree(res.tree);
        }
      } catch (err) {
        console.error(err);
      }
    }
  };

  const rootName = projectPath ? projectPath.split(/[\\/]/).pop() || 'project' : 'project';
  const joinPath = (base: string, child: string) => `${base.replace(/[\\/]+$/, '')}/${child.replace(/^[\\/]+/, '')}`;

  const showNameDialog = (
    title: string,
    label: string,
    initialValue: string,
    confirmLabel: string,
    onConfirm: (value: string) => Promise<void> | void,
  ) => {
    setNameDialog({ title, label, initialValue, confirmLabel, onConfirm });
  };

  const createAtRoot = (kind: 'file' | 'folder') => {
    if (!projectPath) return;
    showNameDialog(
      kind === 'file' ? 'New File' : 'New Folder',
      kind === 'file' ? 'File name' : 'Folder name',
      kind === 'file' ? 'untitled.txt' : 'new-folder',
      'Create',
      async (value) => {
        const targetPath = value.includes(':') ? value : joinPath(projectPath, value);
        const res = kind === 'file'
          ? await createFile(targetPath, '')
          : await createDirectory(targetPath);
        if (!res?.success) {
          window.alert(res?.error || `Could not create ${kind}`);
          return;
        }
        await handleRefresh();
        if (kind === 'file') {
          const fileName = targetPath.split(/[\\/]/).pop() || 'untitled.txt';
          openFile({
            path: res.path || targetPath,
            name: fileName,
            content: '',
            language: getLanguageFromExtension(fileName.includes('.') ? `.${fileName.split('.').pop()}` : ''),
            isDirty: false,
          });
        }
      },
    );
  };

  const handleRootContextMenu = (event: React.MouseEvent) => {
    if ((event.target as HTMLElement).closest('.file-tree-item')) return;
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY });
  };

  const handleRootMenuAction = async (action: ExplorerMenuAction) => {
    if (!projectPath) return;
    if (action === 'new-file') {
      createAtRoot('file');
      return;
    }
    if (action === 'new-folder') {
      createAtRoot('folder');
      return;
    }
    if (action === 'copy-path' || action === 'copy-relative-path') {
      await navigator.clipboard?.writeText(projectPath);
      return;
    }
    if (action === 'open-terminal') {
      await spawnTerminal(projectPath);
      return;
    }
    if (action === 'refresh') {
      await handleRefresh();
    }
  };

  const revealActive = () => {
    if (!activeFile) return;
    const next = new Set<string>();
    const normalized = activeFile.path.replace(/\\/g, '/');
    let current = '';
    for (const part of normalized.split('/').slice(0, -1)) {
      current = current ? `${current}/${part}` : part;
      next.add(current);
    }
    setRevealedPaths(next);
  };

  const filterTree = (nodes: FileNode[]): FileNode[] => {
    const query = filter.trim().toLowerCase();
    if (!query) return nodes;
    return nodes
      .map((node) => {
        if (node.type === 'directory') {
          const children = filterTree(node.children || []);
          if (children.length || node.name.toLowerCase().includes(query)) {
            return { ...node, children };
          }
          return null;
        }
        return node.name.toLowerCase().includes(query) || node.path.toLowerCase().includes(query) ? node : null;
      })
      .filter(Boolean) as FileNode[];
  };

  const visibleTree = filterTree(fileTree);

  if (!projectPath) {
    return (
      <div className="empty-state" style={{ height: '100%' }}>
        <FolderOpen size={36} />
        <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>No folder open</p>
        <button className="btn btn-primary" onClick={handleOpenFolder}>
          Open Folder
        </button>
      </div>
    );
  }

  return (
    <div className="sidebar-panel">
      <div className="sidebar-header">
        <span>Files</span>
        <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
          <button className="btn btn-ghost btn-icon tooltip" data-tooltip="Refresh tree" onClick={handleRefresh}>
            <RefreshCw size={12} />
          </button>
          <button className="btn btn-ghost btn-icon tooltip" data-tooltip="Reveal active file" onClick={revealActive} disabled={!activeFile}>
            <LocateFixed size={12} />
          </button>
          <button className="btn btn-ghost btn-icon tooltip" data-tooltip="New File" onClick={() => createAtRoot('file')}>
            <Plus size={12} />
          </button>
          <button className="btn btn-ghost btn-icon tooltip" data-tooltip="New Folder" onClick={() => createAtRoot('folder')}>
            <FolderPlus size={12} />
          </button>
        </div>
      </div>

      <div className="file-tree-filter">
        <input
          className="input"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={`Jump in ${rootName}`}
        />
      </div>

      <div className="file-tree" onContextMenu={handleRootContextMenu}>
        {visibleTree.length === 0 ? (
          <p style={{ padding: 'var(--space-3)', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)' }}>
            Empty folder
          </p>
        ) : (
          visibleTree.map((node) => <FileTreeItem key={node.path} node={node} depth={0} onRefresh={handleRefresh} forceOpenPaths={revealedPaths} />)
        )}
      </div>

      {contextMenu && (
        <ExplorerContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          onClose={() => setContextMenu(null)}
          onSelect={handleRootMenuAction}
        />
      )}

      {nameDialog && (
        <ExplorerNameDialog
          title={nameDialog.title}
          label={nameDialog.label}
          initialValue={nameDialog.initialValue}
          confirmLabel={nameDialog.confirmLabel}
          onCancel={() => setNameDialog(null)}
          onConfirm={async (value) => {
            await nameDialog.onConfirm(value);
            setNameDialog(null);
          }}
        />
      )}
    </div>
  );
}
