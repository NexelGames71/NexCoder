import React, { useEffect, useMemo, useRef } from 'react';
import {
  Copy,
  FilePlus,
  FolderPlus,
  Pencil,
  RefreshCw,
  Terminal,
  Trash2,
  FileText,
} from 'lucide-react';
import { FileNode } from '../../types';

export type ExplorerMenuAction =
  | 'open'
  | 'new-file'
  | 'new-folder'
  | 'rename'
  | 'delete'
  | 'copy-path'
  | 'copy-relative-path'
  | 'open-terminal'
  | 'refresh';

interface ExplorerContextMenuProps {
  x: number;
  y: number;
  node?: FileNode;
  onClose: () => void;
  onSelect: (action: ExplorerMenuAction) => void;
}

interface MenuItem {
  action: ExplorerMenuAction;
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  danger?: boolean;
  separatorBefore?: boolean;
}

export default function ExplorerContextMenu({ x, y, node, onClose, onSelect }: ExplorerContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const isDirectory = !node || node.type === 'directory';

  const items = useMemo<MenuItem[]>(() => {
    const folderItems: MenuItem[] = isDirectory
      ? [
          { action: 'new-file', label: 'New File', icon: FilePlus },
          { action: 'new-folder', label: 'New Folder', icon: FolderPlus },
          { action: 'open-terminal', label: 'Open in Terminal', icon: Terminal, separatorBefore: true },
        ]
      : [
          { action: 'open', label: 'Open', icon: FileText },
          { action: 'open-terminal', label: 'Open Containing Folder in Terminal', icon: Terminal },
        ];

    return [
      ...folderItems,
      { action: 'copy-path', label: 'Copy Path', icon: Copy, separatorBefore: true },
      { action: 'copy-relative-path', label: 'Copy Relative Path', icon: Copy },
      ...(node ? [{ action: 'rename' as const, label: 'Rename', icon: Pencil, separatorBefore: true }] : []),
      ...(node ? [{ action: 'delete' as const, label: 'Delete', icon: Trash2, danger: true }] : []),
      { action: 'refresh', label: 'Refresh Explorer', icon: RefreshCw, separatorBefore: true },
    ];
  }, [isDirectory, node]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        onClose();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  const style = useMemo<React.CSSProperties>(() => {
    const menuWidth = 240;
    const rowHeight = 32;
    const menuHeight = items.length * rowHeight + 14;
    return {
      left: Math.min(x, window.innerWidth - menuWidth - 8),
      top: Math.min(y, window.innerHeight - menuHeight - 8),
    };
  }, [items.length, x, y]);

  return (
    <div ref={menuRef} className="explorer-context-menu" style={style} role="menu">
      {node && (
        <div className="explorer-context-menu-title" title={node.path}>
          {node.name}
        </div>
      )}
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <button
            key={item.action}
            type="button"
            role="menuitem"
            className={`explorer-context-menu-item ${item.danger ? 'danger' : ''} ${item.separatorBefore ? 'with-separator' : ''}`}
            onClick={() => {
              onSelect(item.action);
              onClose();
            }}
          >
            <Icon size={14} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </div>
  );
}
