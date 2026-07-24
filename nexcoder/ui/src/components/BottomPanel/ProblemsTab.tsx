import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, AlertTriangle, Bot, Copy, FileText, Info, MessageSquareText } from 'lucide-react';
import {
  countDiagnostics,
  flattenDiagnostics,
  useDiagnosticsStore,
  LspDiagnostic,
} from '../../store/useDiagnosticsStore';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useProjectStore } from '../../store/useProjectStore';
import { readFile } from '../../services/bridge';
import { getLanguageFromExtension } from '../../utils/languageMap';
import { buildDiagnosticFixPrompt, loadComposerPrompt } from '../../utils/diagnosticPrompt';

function severityIcon(severity?: number) {
  if (severity === 1) return <AlertCircle size={13} style={{ color: 'var(--accent-red, #ef4444)', flexShrink: 0 }} />;
  if (severity === 2) return <AlertTriangle size={13} style={{ color: 'var(--accent-yellow, #facc15)', flexShrink: 0 }} />;
  return <Info size={13} style={{ color: 'var(--accent-blue, #60a5fa)', flexShrink: 0 }} />;
}

function severityClass(severity?: number) {
  if (severity === 1) return 'error';
  if (severity === 2) return 'warning';
  if (severity === 4) return 'hint';
  return 'info';
}

function severityLabel(severity?: number) {
  if (severity === 1) return 'Error';
  if (severity === 2) return 'Warning';
  if (severity === 4) return 'Hint';
  return 'Info';
}

export default function ProblemsTab() {
  const byPath = useDiagnosticsStore((s) => s.byPath);
  const { projectPath } = useProjectStore();
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    path: string;
    shortPath: string;
    diagnostic: LspDiagnostic;
  } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const entries = useMemo(() => flattenDiagnostics(byPath, projectPath), [byPath, projectPath]);
  const counts = useMemo(() => countDiagnostics(byPath), [byPath]);
  const grouped = useMemo(() => {
    const groups = new Map<string, typeof entries>();
    for (const entry of entries) {
      const existing = groups.get(entry.shortPath) || [];
      existing.push(entry);
      groups.set(entry.shortPath, existing);
    }
    return Array.from(groups.entries());
  }, [entries]);

  useEffect(() => {
    const closeMenu = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenu(null);
    };
    document.addEventListener('pointerdown', closeMenu, true);
    return () => document.removeEventListener('pointerdown', closeMenu, true);
  }, []);

  const handleClick = async (path: string, diagnostic: LspDiagnostic) => {
    const state = useEditorStateStore.getState();
    const line = (diagnostic.range?.start?.line ?? 0) + 1;
    const column = (diagnostic.range?.start?.character ?? 0) + 1;
    state.setPendingReveal({ path, line, column });
    const alreadyOpen = state.editorGroups.some(
      (g) => g.openFiles.some((f) => f.path === path));
    if (!alreadyOpen) {
      const res: any = await readFile(path);
      if (res?.success) {
        const name = path.split(/[\\/]/).pop() || path;
        const extension = name.includes('.') ? name.split('.').pop() || '' : '';
        state.openFile({
          path, name, content: res.content,
          language: getLanguageFromExtension(extension ? `.${extension}` : ''),
          isDirty: false,
        });
      }
    } else {
      state.setActiveFile(path);
    }
  };

  const getPromptForProblem = async (
    path: string,
    shortPath: string,
    diagnostic: LspDiagnostic,
  ) => {
    let lineText = '';
    try {
      const res: any = await readFile(path);
      if (res?.success && typeof res.content === 'string') {
        lineText = res.content.split(/\r\n|\r|\n/)[diagnostic.range?.start?.line ?? 0] || '';
      }
    } catch {
      lineText = '';
    }
    return buildDiagnosticFixPrompt({ path, shortPath, diagnostic, lineText });
  };

  const sendProblemToComposer = async (
    path: string,
    shortPath: string,
    diagnostic: LspDiagnostic,
    send = false,
  ) => {
    const prompt = await getPromptForProblem(path, shortPath, diagnostic);
    window.nexcoder?.showAIPanel?.();
    loadComposerPrompt({ content: prompt, mode: 'agent', send });
    setMenu(null);
  };

  const copyProblem = async (
    path: string,
    shortPath: string,
    diagnostic: LspDiagnostic,
  ) => {
    const prompt = await getPromptForProblem(path, shortPath, diagnostic);
    await navigator.clipboard?.writeText(prompt);
    setMenu(null);
  };

  if (entries.length === 0) {
    return (
      <div className="overflow-auto h-full" style={{ padding: 'var(--space-3)' }}>
        <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)', padding: 'var(--space-4)' }}>
          No problems detected in open files
        </p>
      </div>
    );
  }

  return (
    <div className="problems-panel">
      <div className="problems-topline" aria-label={`${counts.total} problems`}>
        <div>
          <span className="problems-title">Problems</span>
          <span className="problems-subtitle">{grouped.length} files affected</span>
        </div>
        <div className="problems-count-pills">
          <span className="problem-pill total">{counts.total}</span>
          {counts.errors > 0 && <span className="problem-pill error">{counts.errors} errors</span>}
          {counts.warnings > 0 && <span className="problem-pill warning">{counts.warnings} warnings</span>}
          {(counts.infos + counts.hints) > 0 && <span className="problem-pill info">{counts.infos + counts.hints} info</span>}
        </div>
      </div>
      <div className="problems-list redesigned">
        {grouped.map(([shortPath, fileEntries]) => (
          <section className="problem-file-group" key={shortPath}>
            <div className="problem-file-header">
              <FileText size={13} />
              <span className="problem-file-name">{shortPath}</span>
              <span className="problem-file-count">{fileEntries.length}</span>
            </div>
            {fileEntries.map(({ path, diagnostic }, index) => {
              const line = (diagnostic.range?.start?.line ?? 0) + 1;
              const column = (diagnostic.range?.start?.character ?? 0) + 1;
              const sev = severityClass(diagnostic.severity);
              return (
                <div
                  key={`${path}:${index}`}
                  onClick={() => handleClick(path, diagnostic)}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    setMenu({ x: event.clientX, y: event.clientY, path, shortPath, diagnostic });
                  }}
                  className={`problems-row ${sev}`}
                  title={diagnostic.message}
                >
                  <div className="problem-row-main">
                    {severityIcon(diagnostic.severity)}
                    <div className="problem-row-copy">
                      <div className="problem-message">{diagnostic.message}</div>
                      <div className="problem-meta">
                        <span className={`problem-severity ${sev}`}>{severityLabel(diagnostic.severity)}</span>
                        <span>Ln {line}, Col {column}</span>
                        {diagnostic.source && <span>{diagnostic.source}</span>}
                        {diagnostic.code !== undefined && diagnostic.code !== null && <span>{diagnostic.code}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="problem-row-actions">
                    <button
                      type="button"
                      title="Send to Chat"
                      aria-label="Send problem to chat"
                      onClick={(event) => {
                        event.stopPropagation();
                        void sendProblemToComposer(path, shortPath, diagnostic, false);
                      }}
                    >
                      <MessageSquareText size={12} />
                    </button>
                    <button
                      type="button"
                      title="Fix with Agent"
                      aria-label="Fix problem with agent"
                      onClick={(event) => {
                        event.stopPropagation();
                        void sendProblemToComposer(path, shortPath, diagnostic, true);
                      }}
                    >
                      <Bot size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </section>
        ))}
      </div>
      {menu && (
        <div
          ref={menuRef}
          className="problems-context-menu"
          style={{ left: menu.x, top: menu.y }}
          role="menu"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => void sendProblemToComposer(menu.path, menu.shortPath, menu.diagnostic, false)}
          >
            <MessageSquareText size={13} />
            <span>Send to Chat</span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => void sendProblemToComposer(menu.path, menu.shortPath, menu.diagnostic, true)}
          >
            <Bot size={13} />
            <span>Fix with Agent</span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => void copyProblem(menu.path, menu.shortPath, menu.diagnostic)}
          >
            <Copy size={13} />
            <span>Copy Problem Prompt</span>
          </button>
        </div>
      )}
    </div>
  );
}
