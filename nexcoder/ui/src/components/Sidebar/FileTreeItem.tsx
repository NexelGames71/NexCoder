import React, { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { FileNode } from '../../types';
import { getFileIcon, getFileColor } from '../../utils/fileIcons';
import { selectActiveFile, useEditorStateStore } from '../../store/useEditorStateStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import { createDirectory, createFile, deleteFile, readFile, renameFile, spawnTerminal, writeFile, writeFileBase64 } from '../../services/bridge';
import { getLanguageFromExtension } from '../../utils/languageMap';
import { useProjectStore } from '../../store/useProjectStore';
import ExplorerContextMenu, { ExplorerMenuAction } from './ExplorerContextMenu';
import ExplorerNameDialog from './ExplorerNameDialog';

interface FileTreeItemProps {
  node: FileNode;
  depth: number;
  onRefresh?: () => Promise<void> | void;
  forceOpenPaths?: Set<string>;
}

const parentDir = (p: string) => p.replace(/[\\/]+$/, '').replace(/[\\/][^\\/]*$/, '') || p;
const isImageName = (name: string) => /\.(png|jpg|jpeg|gif|webp|ico|bmp|avif)$/i.test(name);

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.slice(result.indexOf(',') + 1)); // strip data: prefix
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function FileTreeItem({ node, depth, onRefresh, forceOpenPaths }: FileTreeItemProps) {
  const [manualOpen, setManualOpen] = useState(false);
  const [dropActive, setDropActive] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [nameDialog, setNameDialog] = useState<{
    title: string;
    label: string;
    initialValue: string;
    confirmLabel: string;
    onConfirm: (value: string) => Promise<void> | void;
  } | null>(null);
  const activeFile = useEditorStateStore(selectActiveFile);
  const { openFile, closeFile } = useEditorStateStore();
  const { projectPath } = useProjectStore();

  const isDirectory = node.type === 'directory';
  const isForcedOpen = !!forceOpenPaths?.has(node.path);
  const isOpen = manualOpen || isForcedOpen;
  const Icon = getFileIcon(node.extension, isDirectory, isOpen, node.name);
  const color = isDirectory ? 'var(--accent-purple)' : getFileColor(node.extension, node.name);
  const isActive = activeFile?.path === node.path;

  const openNode = async () => {
    if (isDirectory) {
      setManualOpen(!isOpen);
      return;
    }

    try {
      const res: any = await readFile(node.path);
      if (res && res.success) {
        openFile({
          path: node.path,
          name: node.name,
          content: res.content,
          language: getLanguageFromExtension(node.extension || ''),
          isDirty: false,
        });
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await openNode();
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  const parentPath = () => node.path.replace(/[/\\][^/\\]+$/, '');
  const joinPath = (base: string, child: string) => `${base.replace(/[\\/]+$/, '')}/${child.replace(/^[\\/]+/, '')}`;
  const relativePath = () => {
    if (!projectPath) return node.path;
    const normalizedRoot = projectPath.replace(/\\/g, '/').replace(/\/$/, '');
    const normalizedPath = node.path.replace(/\\/g, '/');
    return normalizedPath.startsWith(`${normalizedRoot}/`)
      ? normalizedPath.slice(normalizedRoot.length + 1)
      : normalizedPath;
  };

  const showNameDialog = (
    title: string,
    label: string,
    initialValue: string,
    confirmLabel: string,
    onConfirm: (value: string) => Promise<void> | void,
  ) => {
    setNameDialog({ title, label, initialValue, confirmLabel, onConfirm });
  };

  const handleMenuAction = async (action: ExplorerMenuAction) => {
    if (action === 'open') {
      await openNode();
      return;
    }
    if (action === 'copy-path') {
      await navigator.clipboard?.writeText(node.path);
      return;
    }
    if (action === 'copy-relative-path') {
      await navigator.clipboard?.writeText(relativePath());
      return;
    }
    if (action === 'open-terminal') {
      await spawnTerminal(isDirectory ? node.path : parentPath());
      return;
    }
    if (action === 'refresh') {
      await onRefresh?.();
      return;
    }
    if (action === 'rename') {
      showNameDialog('Rename', 'Name', node.name, 'Rename', async (nextName) => {
        if (nextName === node.name) return;
        const nextPath = joinPath(parentPath(), nextName);
        const res = await renameFile(node.path, nextPath);
        if (!res?.success) {
          window.alert(res?.error || 'Rename failed');
          return;
        }
        closeFile(node.path);
        await onRefresh?.();
      });
      return;
    }
    if (action === 'delete') {
      const { confirmFileDelete } = useEditorSettingsStore.getState().settings;
      if (confirmFileDelete
          && !window.confirm(`Delete ${node.name}? This cannot be undone.`)) {
        return;
      }
      const res = await deleteFile(node.path);
      if (!res?.success) {
        if (res?.details?.reason !== 'user_cancelled') {
          window.alert(res?.error || 'Delete failed');
        }
        return;
      }
      closeFile(node.path);
      await onRefresh?.();
      return;
    }
    if (action === 'new-file' || action === 'new-folder') {
      const kind = action === 'new-file' ? 'file' : 'folder';
      const basePath = isDirectory ? node.path : parentPath();
      showNameDialog(
        kind === 'file' ? 'New File' : 'New Folder',
        kind === 'file' ? 'File name' : 'Folder name',
        kind === 'file' ? 'untitled.txt' : 'new-folder',
        'Create',
        async (name) => {
          const targetPath = joinPath(basePath, name);
          const res = kind === 'file'
            ? await createFile(targetPath, '')
            : await createDirectory(targetPath);
          if (!res?.success) {
            window.alert(res?.error || `Create ${kind} failed`);
            return;
          }
          if (isDirectory) setManualOpen(true);
          await onRefresh?.();
          if (kind === 'file') {
            openFile({
              path: res.path || targetPath,
              name: targetPath.split(/[\\/]/).pop() || name,
              content: '',
              language: getLanguageFromExtension(name.split('.').pop() || ''),
              isDirty: false,
            });
          }
        },
      );
    }
  };

  // ── Drag & drop ──────────────────────────────────────────────────
  const dropFolder = () => isDirectory ? node.path : parentDir(node.path);

  const handleDragStart = (e: React.DragEvent) => {
    e.stopPropagation();
    e.dataTransfer.setData('application/x-nexcoder-path', node.path);
    e.dataTransfer.setData('text/plain', node.path);
    e.dataTransfer.effectAllowed = 'copyMove';
  };

  const handleDragOver = (e: React.DragEvent) => {
    // Accept internal moves and OS file drops onto folders.
    if (!isDirectory && !e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = e.dataTransfer.types.includes('Files') ? 'copy' : 'move';
    if (!dropActive) setDropActive(true);
  };

  const handleDragLeave = () => setDropActive(false);

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDropActive(false);
    const target = dropFolder();

    // OS files dragged in from outside the IDE.
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      for (const file of Array.from(e.dataTransfer.files)) {
        const dest = joinPath(target, file.name);
        try {
          if (isImageName(file.name) || file.type.startsWith('image/')
              || /\.(png|jpg|jpeg|gif|webp|ico|bmp|pdf|zip|exe|dll|wasm|gguf|bin)$/i.test(file.name)) {
            const b64 = await fileToBase64(file);
            await writeFileBase64(dest, b64);
          } else {
            await writeFile(dest, await file.text());
          }
        } catch (err) { console.error('Import failed', err); }
      }
      if (isDirectory) setManualOpen(true);
      await onRefresh?.();
      return;
    }

    // Internal move: reparent the dragged path into this folder.
    const src = e.dataTransfer.getData('application/x-nexcoder-path');
    if (!src || src === node.path) return;
    const srcName = src.split(/[\\/]/).pop() || src;
    const dest = joinPath(target, srcName);
    if (dest === src || parentDir(src) === target) return;
    if (isDirectory && (target + '/').startsWith(src.replace(/\\/g, '/') + '/')) return; // no folder into itself
    try {
      const res = await renameFile(src, dest);
      if (!res?.success) { window.alert(res?.error || 'Move failed'); return; }
      if (isDirectory) setManualOpen(true);
      await onRefresh?.();
    } catch (err) { console.error('Move failed', err); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div
        className={`file-tree-item ${isActive ? 'active' : ''} ${dropActive ? 'drop-target' : ''}`}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        draggable
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{ paddingLeft: `${depth * 12 + 12}px` }}
      >
        {isDirectory ? (
          <span className={`file-tree-item-chevron ${isOpen ? 'open' : ''}`}>
            <ChevronRight size={14} />
          </span>
        ) : (
          <span style={{ width: '14px' }} />
        )}
        <span className="file-tree-item-icon" style={{ color }}>
          <Icon size={14} />
        </span>
        <span className="truncate" style={{ fontSize: 'var(--font-size-sm)' }}>
          {node.name}
        </span>
      </div>

      {isDirectory && isOpen && node.children && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {node.children.map((child) => (
            <FileTreeItem key={child.path} node={child} depth={depth + 1} onRefresh={onRefresh} forceOpenPaths={forceOpenPaths} />
          ))}
        </div>
      )}

      {contextMenu && (
        <ExplorerContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          node={node}
          onClose={() => setContextMenu(null)}
          onSelect={handleMenuAction}
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
