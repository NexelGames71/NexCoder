import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  CheckSquare,
  Columns2,
  FileText,
  FileArchive,
  FolderOpen,
  GitBranch,
  ListChecks,
  LogIn,
  LogOut,
  MessageSquareText,
  Network,
  PanelBottom,
  PanelLeft,
  PanelRight,
  Puzzle,
  Search,
  Settings,
  Terminal,
  type LucideIcon,
} from 'lucide-react';
import { useProjectStore } from '../../store/useProjectStore';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { openFileDialog, openFolderDialog, openProject, readFile } from '../../services/bridge';
import { getFileIcon, getFileColor, getFilePreviewKind } from '../../utils/fileIcons';
import { getLanguageFromExtension } from '../../utils/languageMap';
import type { FileNode } from '../../types';
import CloneRepositoryDialog from '../Editor/CloneRepositoryDialog';
import './QuickSearch.css';

interface FlatFile { name: string; path: string; extension: string; }
type PaletteKind = 'command' | 'file' | 'recent';

interface QuickSearchProps {
  onOpenEditorSettings: () => void;
  onOpenAgentSettings: () => void;
  onOpenAuth: () => void;
  onLogout: () => void;
  user: any;
}

interface PaletteEntry {
  id: string;
  kind: PaletteKind;
  title: string;
  subtitle: string;
  keywords: string;
  shortcut?: string;
  icon: LucideIcon | ReturnType<typeof getFileIcon>;
  iconColor?: string;
  disabled?: boolean;
  action: () => unknown | Promise<unknown>;
}

function flatten(nodes: FileNode[], out: FlatFile[] = []): FlatFile[] {
  for (const node of nodes) {
    if (node.type === 'directory') {
      if (node.children) flatten(node.children, out);
    } else {
      out.push({ name: node.name, path: node.path, extension: node.extension || '' });
    }
  }
  return out;
}

function extensionFromName(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot) : '';
}

function scoreText(query: string, title: string, subtitle: string, keywords: string): number {
  if (!query) return 1;
  const q = query.toLowerCase();
  const lowerTitle = title.toLowerCase();
  const lowerSubtitle = subtitle.toLowerCase();
  const haystack = `${lowerTitle} ${lowerSubtitle} ${keywords.toLowerCase()}`;
  if (lowerTitle === q) return 150;
  if (lowerTitle.startsWith(q)) return 120;
  if (lowerTitle.split(/\s+/).some((word) => word.startsWith(q))) return 95;
  if (lowerTitle.includes(q)) return 80;
  if (lowerSubtitle.includes(q)) return 55;
  if (haystack.includes(q)) return 45;
  let offset = 0;
  for (const char of q) {
    const next = haystack.indexOf(char, offset);
    if (next === -1) return 0;
    offset = next + 1;
  }
  return 20;
}

/** VS Code-style command center: run commands or quick-open project files. */
export default function QuickSearch({
  onOpenEditorSettings,
  onOpenAgentSettings,
  onOpenAuth,
  onLogout,
  user,
}: QuickSearchProps) {
  const { fileTree, projectName, projectInfo, recentProjects } = useProjectStore();
  const { openFile, splitEditor } = useEditorStateStore();
  const activeFile = useEditorStateStore((s) => {
    const group = s.editorGroups.find((item) => item.id === s.activeGroupId);
    return group?.openFiles.find((file) => file.path === group.activeFilePath) || null;
  });
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [showCloneDialog, setShowCloneDialog] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const allFiles = useMemo(() => flatten(fileTree), [fileTree]);

  const openPath = useCallback(async (path: string, name?: string, extension?: string) => {
    const fileName = name || path.split(/[\\/]/).pop() || 'file';
    const ext = extension || extensionFromName(fileName);
    if (getFilePreviewKind(path) !== 'text') {
      openFile({
        path,
        name: fileName,
        content: '',
        language: 'plaintext',
        isDirty: false,
      });
      return;
    }

    const res: any = await readFile(path);
    if (res?.success) {
      openFile({
        path,
        name: fileName,
        content: res.content,
        language: getLanguageFromExtension(ext),
        isDirty: false,
      });
    }
  }, [openFile]);

  const showSidebarTab = useCallback((tabId: string) => {
    window.nexcoder?.showSidebarTab?.(tabId);
  }, []);

  const showBottomPanel = useCallback((tabId: string) => {
    window.nexcoder?.showBottomPanel?.(tabId);
  }, []);

  const commandEntries = useMemo<PaletteEntry[]>(() => {
    const commands: PaletteEntry[] = [
      {
        id: 'open-folder',
        kind: 'command',
        title: 'Open Folder',
        subtitle: 'Choose a folder and open it as the workspace',
        keywords: 'project workspace directory',
        icon: FolderOpen,
        action: () => openFolderDialog(),
      },
      {
        id: 'open-file',
        kind: 'command',
        title: 'Open File',
        subtitle: 'Open a file from disk, including media previews',
        keywords: 'image audio video preview external',
        icon: FileText,
        action: async () => {
          const path = await openFileDialog();
          if (typeof path === 'string' && path) await openPath(path);
        },
      },
      {
        id: 'clone-repository',
        kind: 'command',
        title: 'Clone Repository',
        subtitle: 'Clone a Git repository and open it',
        keywords: 'git github repo repository checkout',
        icon: GitBranch,
        action: () => setShowCloneDialog(true),
      },
      {
        id: 'new-terminal',
        kind: 'command',
        title: 'New Terminal',
        subtitle: 'Start a terminal in the current project',
        keywords: 'shell powershell command prompt',
        shortcut: 'Ctrl+Shift+`',
        icon: Terminal,
        action: () => window.nexcoder?.newTerminal(),
      },
      {
        id: 'show-terminal',
        kind: 'command',
        title: 'Show Terminal',
        subtitle: 'Open the bottom panel terminal',
        keywords: 'panel shell console',
        icon: PanelBottom,
        action: () => showBottomPanel('terminal'),
      },
      {
        id: 'show-problems',
        kind: 'command',
        title: 'Show Problems',
        subtitle: 'Open diagnostics and problem count',
        keywords: 'errors warnings diagnostics lsp',
        icon: CheckSquare,
        action: () => showBottomPanel('problems'),
      },
      {
        id: 'show-output',
        kind: 'command',
        title: 'Show Output',
        subtitle: 'Open the output panel',
        keywords: 'logs build output',
        icon: PanelBottom,
        action: () => showBottomPanel('output'),
      },
      {
        id: 'show-git-diff',
        kind: 'command',
        title: 'Show Git Diff',
        subtitle: 'Open the bottom panel Git diff',
        keywords: 'source control changes patch',
        icon: GitBranch,
        action: () => showBottomPanel('gitDiff'),
      },
      {
        id: 'show-explorer',
        kind: 'command',
        title: 'Show Explorer',
        subtitle: 'Open the file explorer',
        keywords: 'files sidebar',
        icon: PanelLeft,
        action: () => showSidebarTab('explorer'),
      },
      {
        id: 'search-project',
        kind: 'command',
        title: 'Search Project',
        subtitle: 'Open project-wide text search',
        keywords: 'grep find sidebar',
        icon: Search,
        action: () => showSidebarTab('search'),
      },
      {
        id: 'source-control',
        kind: 'command',
        title: 'Source Control',
        subtitle: 'Open Git status and commits',
        keywords: 'git changes scm',
        icon: GitBranch,
        action: () => showSidebarTab('git'),
      },
      {
        id: 'extensions-marketplace',
        kind: 'command',
        title: 'Extensions Marketplace',
        subtitle: 'Install languages, tools, workflows, templates, and agent capabilities',
        keywords: 'marketplace plugins extensions install agent skills templates',
        icon: Puzzle,
        action: () => showSidebarTab('extensions'),
      },
      {
        id: 'agent-tasks',
        kind: 'command',
        title: 'Agent Tasks',
        subtitle: 'Open running and past agent tasks',
        keywords: 'runs history jobs',
        icon: ListChecks,
        action: () => showSidebarTab('tasks'),
      },
      {
        id: 'agent-chats',
        kind: 'command',
        title: 'Agent Chats',
        subtitle: 'Show saved chats above the agent panel',
        keywords: 'chat history sessions ai panel',
        icon: MessageSquareText,
        action: () => {
          window.nexcoder?.showAIPanel?.();
          window.dispatchEvent(new CustomEvent('nexcoder:toggle-agent-chats'));
        },
      },
      {
        id: 'agent-artifacts',
        kind: 'command',
        title: 'Agent Artifacts',
        subtitle: 'Show generated reports, patch summaries, and run artifacts',
        keywords: 'artifacts reports summaries validation patches ai panel',
        icon: FileArchive,
        action: () => {
          window.nexcoder?.showAIPanel?.();
          window.dispatchEvent(new CustomEvent('nexcoder:toggle-agent-artifacts'));
        },
      },
      {
        id: 'agent-mesh',
        kind: 'command',
        title: 'Agent Mesh',
        subtitle: 'Open specialist agent orchestration',
        keywords: 'orchestrator multi agent network',
        icon: Network,
        action: () => showSidebarTab('mesh'),
      },
      {
        id: 'toggle-sidebar',
        kind: 'command',
        title: 'Toggle Sidebar',
        subtitle: 'Show or hide the left panel',
        keywords: 'explorer panels layout',
        icon: PanelLeft,
        action: () => window.nexcoder?.toggleSidebar(),
      },
      {
        id: 'toggle-ai-panel',
        kind: 'command',
        title: 'Toggle AI Panel',
        subtitle: 'Show or hide NexCoder AI',
        keywords: 'assistant chat agent',
        icon: PanelRight,
        action: () => window.nexcoder?.toggleAIPanel(),
      },
      {
        id: 'split-editor',
        kind: 'command',
        title: 'Split Editor',
        subtitle: 'Create another editor group',
        keywords: 'layout column pane',
        icon: Columns2,
        action: splitEditor,
      },
      {
        id: 'save-file',
        kind: 'command',
        title: 'Save File',
        subtitle: activeFile ? activeFile.name : 'No active file',
        keywords: 'write persist',
        shortcut: 'Ctrl+S',
        icon: FileText,
        disabled: !activeFile,
        action: () => window.nexcoder?.saveActiveFile(),
      },
      {
        id: 'save-all',
        kind: 'command',
        title: 'Save All Files',
        subtitle: 'Persist every dirty editor tab',
        keywords: 'write persist all',
        icon: FileText,
        action: () => window.nexcoder?.saveAllFiles(),
      },
      {
        id: 'save-as',
        kind: 'command',
        title: 'Save File As',
        subtitle: activeFile ? `Save ${activeFile.name} to another path` : 'No active file',
        keywords: 'copy export',
        icon: FileText,
        disabled: !activeFile,
        action: () => window.nexcoder?.saveActiveFileAs(),
      },
      {
        id: 'editor-settings',
        kind: 'command',
        title: 'Editor Settings',
        subtitle: 'Open editor appearance and behavior settings',
        keywords: 'preferences theme font',
        shortcut: 'Ctrl+,',
        icon: Settings,
        action: onOpenEditorSettings,
      },
      {
        id: 'agent-settings',
        kind: 'command',
        title: 'Agent Settings',
        subtitle: 'Open model, autonomy, and tool settings',
        keywords: 'ai model permissions',
        shortcut: 'Ctrl+Shift+,',
        icon: Bot,
        action: onOpenAgentSettings,
      },
      user ? {
        id: 'logout',
        kind: 'command',
        title: 'Logout',
        subtitle: user.name || user.email || 'Sign out of sync',
        keywords: 'account web auth',
        icon: LogOut,
        action: onLogout,
      } : {
        id: 'login',
        kind: 'command',
        title: 'Login',
        subtitle: 'Sign in with NexCoder Web',
        keywords: 'account web auth',
        icon: LogIn,
        action: onOpenAuth,
      },
    ];

    if (projectInfo?.hasGit) {
      commands.splice(11, 0, {
        id: 'open-git-panel',
        kind: 'command',
        title: 'Open Source Control',
        subtitle: 'Inspect repository changes',
        keywords: 'git commit branch scm',
        icon: GitBranch,
        action: () => showSidebarTab('git'),
      });
    }
    return commands;
  }, [
    activeFile,
    onLogout,
    onOpenAgentSettings,
    onOpenAuth,
    onOpenEditorSettings,
    openPath,
    projectInfo?.hasGit,
    showBottomPanel,
    showSidebarTab,
    splitEditor,
    user,
  ]);

  const entries = useMemo<PaletteEntry[]>(() => {
    const rawQuery = query.trim();
    const commandMode = rawQuery.startsWith('>');
    const q = (commandMode ? rawQuery.slice(1) : rawQuery).trim();
    const recentEntries: PaletteEntry[] = recentProjects.slice(0, 8).map((project) => ({
      id: `recent:${project.path}`,
      kind: 'recent',
      title: `Open Recent: ${project.name}`,
      subtitle: project.path,
      keywords: 'recent project workspace folder',
      icon: FolderOpen,
      action: () => openProject(project.path),
    }));

    const commandResults = [...commandEntries, ...recentEntries]
      .map((entry, index) => ({
        entry,
        score: q ? scoreText(q, entry.title, entry.subtitle, entry.keywords) : 80 - index,
      }))
      .filter((item) => item.score > 0);

    const fileResults = commandMode ? [] : allFiles
      .map((file) => {
        const score = scoreText(q, file.name, file.path, 'file quick open');
        const Icon = getFileIcon(file.extension || extensionFromName(file.name), false, false, file.name);
        return {
          entry: {
            id: `file:${file.path}`,
            kind: 'file',
            title: file.name,
            subtitle: file.path,
            keywords: 'file quick open',
            icon: Icon,
            iconColor: getFileColor(file.extension || extensionFromName(file.name), file.name),
            action: () => openPath(file.path, file.name, file.extension || extensionFromName(file.name)),
          } satisfies PaletteEntry,
          score,
        };
      })
      .filter((item) => q && item.score > 0);

    return [...commandResults, ...fileResults]
      .sort((a, b) => b.score - a.score || a.entry.title.localeCompare(b.entry.title))
      .slice(0, q ? 14 : 10)
      .map((item) => item.entry);
  }, [allFiles, commandEntries, openPath, query, recentProjects]);

  useEffect(() => { setActive(0); }, [query]);

  // Ctrl+P focuses quick-open; Ctrl+Shift+P opens commands.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P')) {
        e.preventDefault();
        setQuery(e.shiftKey ? '>' : '');
        inputRef.current?.focus();
        setOpen(true);
      }
      if (e.key === 'F1') {
        e.preventDefault();
        setQuery('>');
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Close on outside click.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  const runEntry = async (entry: PaletteEntry) => {
    if (entry.disabled) return;
    try {
      await entry.action();
    } catch (error) {
      console.error('Command palette action failed:', error);
    }
    setOpen(false);
    setQuery('');
    inputRef.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, Math.max(entries.length - 1, 0))); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter' && entries[active]) { e.preventDefault(); void runEntry(entries[active]); }
    else if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur(); }
  };

  const placeholder = projectName ? `Search ${projectName} or run command` : 'Search files or run command';

  return (
    <div className="quick-search" ref={wrapRef}>
      <div className="quick-search-bar">
        <Search size={12} className="quick-search-icon" />
        <input
          ref={inputRef}
          className="quick-search-input"
          value={query}
          placeholder={placeholder}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && (
        <div className="quick-search-results">
          {entries.length === 0 ? (
            <div className="quick-search-empty">No matching commands or files</div>
          ) : (
            entries.map((entry, i) => {
              const Icon = entry.icon;
              return (
                <div
                  key={entry.id}
                  className={`quick-search-item ${entry.kind} ${i === active ? 'active' : ''} ${entry.disabled ? 'disabled' : ''}`}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => { e.preventDefault(); void runEntry(entry); }}
                >
                  <Icon size={13} style={{ color: entry.iconColor, flexShrink: 0 }} />
                  <div className="quick-search-copy">
                    <span className="quick-search-name">{entry.title}</span>
                    <span className="quick-search-path">{entry.subtitle}</span>
                  </div>
                  <span className="quick-search-kind">{entry.shortcut || entry.kind}</span>
                </div>
              );
            })
          )}
        </div>
      )}
      {showCloneDialog && (
        <CloneRepositoryDialog onClose={() => setShowCloneDialog(false)} />
      )}
    </div>
  );
}

