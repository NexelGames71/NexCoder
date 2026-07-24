import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  Maximize2,
  Minimize2,
  Plus,
  Terminal as TerminalIcon,
  Trash2,
  X,
} from 'lucide-react';
import TerminalTab from './TerminalTab';
import OutputTab from './OutputTab';
import ProblemsTab from './ProblemsTab';
import GitDiffTab from './GitDiffTab';
import { useTerminalStore } from '../../store/useTerminalStore';
import { useProjectStore } from '../../store/useProjectStore';
import { countDiagnostics, useDiagnosticsStore } from '../../store/useDiagnosticsStore';
import { killTerminal, spawnTerminal } from '../../services/bridge';
import './BottomPanel.css';

interface BottomPanelProps {
  isCollapsed: boolean;
  onClose: () => void;
}

type PanelTab = 'terminal' | 'output' | 'problems' | 'gitDiff';

function shellLabel(shell: string | undefined, index: number): string {
  const normalized = (shell || '').toLowerCase();
  if (normalized.includes('pwsh')) return `PowerShell ${index}`;
  if (normalized.includes('powershell')) return `Windows PowerShell ${index}`;
  if (normalized.includes('cmd')) return `Command Prompt ${index}`;
  if (shell) return `${shell.replace(/\.exe$/i, '')} ${index}`;
  return `Terminal ${index}`;
}

export default function BottomPanel({ isCollapsed, onClose }: BottomPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>('terminal');
  const [showDropdown, setShowDropdown] = useState(false);
  const [isSpawning, setIsSpawning] = useState(false);
  const [spawnError, setSpawnError] = useState<string | null>(null);
  const [isMaximized, setIsMaximized] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const spawnInFlightRef = useRef(false);
  const initialSpawnAttemptedRef = useRef(false);
  const previousProjectRef = useRef<string | null>(null);
  const projectGenerationRef = useRef(0);
  const sessionNumberRef = useRef(0);

  const { projectPath } = useProjectStore();
  const {
    sessions,
    activeSessionId,
    addSession,
    removeSession,
    setActiveSession,
  } = useTerminalStore();
  // Select the stable store slice, then derive counts via useMemo.
  // countDiagnostics() returns a new object on every call, which would
  // trip useSyncExternalStore's "getSnapshot should be cached" guard.
  const diagnosticsByPath = useDiagnosticsStore((state) => state.byPath);
  const diagnosticCounts = useMemo(
    () => countDiagnostics(diagnosticsByPath), [diagnosticsByPath]);

  const handleNewTerminal = useCallback(async (workingDirectory?: string) => {
    if (spawnInFlightRef.current) return;
    const generation = projectGenerationRef.current;
    spawnInFlightRef.current = true;
    setIsSpawning(true);
    setSpawnError(null);
    try {
      const result = await spawnTerminal(workingDirectory || projectPath || '');
      if (!result?.success || !result?.sessionId) {
        throw new Error(result?.error || 'The terminal backend did not create a session.');
      }
      if (generation !== projectGenerationRef.current) {
        await killTerminal(result.sessionId);
        return;
      }
      sessionNumberRef.current += 1;
      addSession({
        id: result.sessionId,
        cwd: result.cwd || projectPath || '',
        shell: result.shell || '',
        name: shellLabel(result.shell, sessionNumberRef.current),
        status: result.status === 'exited' ? 'exited' : 'running',
        exitCode: result.exitCode ?? null,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setSpawnError(`Could not start the terminal. ${message}`);
    } finally {
      spawnInFlightRef.current = false;
      setIsSpawning(false);
    }
  }, [addSession, projectPath]);

  useEffect(() => {
    const handleExternalSpawn = (event: Event) => {
      const cwd = (event as CustomEvent<{ cwd?: string }>).detail?.cwd;
      void handleNewTerminal(cwd);
    };
    window.addEventListener('nexcoder:new-terminal', handleExternalSpawn);
    return () => window.removeEventListener('nexcoder:new-terminal', handleExternalSpawn);
  }, [handleNewTerminal]);

  useEffect(() => {
    const validTabs = new Set<PanelTab>(['terminal', 'output', 'problems', 'gitDiff']);
    const handleShowTab = (event: Event) => {
      const tabId = String((event as CustomEvent<{ tabId?: string }>).detail?.tabId || 'terminal') as PanelTab;
      if (validTabs.has(tabId)) {
        setActiveTab(tabId);
      }
    };
    window.addEventListener('nexcoder:show-bottom-tab', handleShowTab);
    return () => window.removeEventListener('nexcoder:show-bottom-tab', handleShowTab);
  }, []);

  // A project switch owns a separate terminal lifetime.
  useEffect(() => {
    const previousProject = previousProjectRef.current;
    previousProjectRef.current = projectPath;
    if (previousProject === projectPath) return;

    projectGenerationRef.current += 1;
    initialSpawnAttemptedRef.current = false;
    sessionNumberRef.current = 0;
    setSpawnError(null);
    const staleSessions = useTerminalStore.getState().sessions;
    if (staleSessions.length === 0) return;
    void Promise.allSettled(staleSessions.map((session) => killTerminal(session.id)))
      .finally(() => {
        // A new session may have been requested while the old project was
        // shutting down. Remove only sessions captured for the old project.
        staleSessions.forEach((session) => removeSession(session.id));
      });
  }, [projectPath, removeSession]);

  // Start exactly one initial terminal when the panel first becomes visible.
  useEffect(() => {
    if (isCollapsed || isSpawning || sessions.length > 0 || initialSpawnAttemptedRef.current) return;
    initialSpawnAttemptedRef.current = true;
    void handleNewTerminal();
  }, [handleNewTerminal, isCollapsed, isSpawning, sessions.length]);

  useEffect(() => {
    const closeDropdown = (event: PointerEvent) => {
      if (!dropdownRef.current?.contains(event.target as Node)) setShowDropdown(false);
    };
    document.addEventListener('pointerdown', closeDropdown, true);
    return () => document.removeEventListener('pointerdown', closeDropdown, true);
  }, []);

  const handleKillTerminal = useCallback(async () => {
    if (!activeSessionId) return;
    await killTerminal(activeSessionId);
    removeSession(activeSessionId);
  }, [activeSessionId, removeSession]);

  const handleRestartTerminal = useCallback(async (sessionId: string) => {
    const session = useTerminalStore.getState().sessions.find((item) => item.id === sessionId);
    if (!session || spawnInFlightRef.current) return;
    await killTerminal(sessionId);
    removeSession(sessionId);
    await handleNewTerminal(session.cwd || projectPath || '');
  }, [handleNewTerminal, projectPath, removeSession]);

  if (isCollapsed) return null;

  const activeSession = sessions.find((session) => session.id === activeSessionId);

  return (
    <div className={`bp-container ${isMaximized ? 'maximized' : ''}`}>
      <div className="bp-header">
        <div className="bp-tabs" role="tablist" aria-label="Bottom panel">
          {([
            ['problems', 'PROBLEMS'],
            ['output', 'OUTPUT'],
            ['terminal', 'TERMINAL'],
            ['gitDiff', 'GIT DIFF'],
          ] as const).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={activeTab === id}
              className={`bp-tab ${activeTab === id ? 'active' : ''}`}
              onClick={() => setActiveTab(id)}
            >
              <span>{label}</span>
              {id === 'problems' && diagnosticCounts.total > 0 && (
                <span
                  className={`bp-tab-badge ${diagnosticCounts.errors > 0 ? 'error' : diagnosticCounts.warnings > 0 ? 'warning' : ''}`}
                  title={`${diagnosticCounts.total} problems`}
                >
                  {diagnosticCounts.total}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="bp-right-controls">
          {activeTab === 'terminal' && (
            <>
              <div className="bp-session-selector" ref={dropdownRef}>
                <button
                  type="button"
                  className="bp-session-trigger"
                  onClick={() => setShowDropdown((open) => !open)}
                  aria-expanded={showDropdown}
                >
                  <TerminalIcon size={12} className="bp-session-icon" />
                  <span className="bp-session-name">{activeSession?.name || 'No terminal'}</span>
                  <ChevronDown size={12} className="bp-session-arrow" />
                </button>
                {showDropdown && sessions.length > 0 && (
                  <div className="bp-dropdown-menu" role="menu">
                    {sessions.map((session) => (
                      <button
                        type="button"
                        role="menuitem"
                        key={session.id}
                        className={`bp-dropdown-item ${session.id === activeSessionId ? 'active' : ''}`}
                        onClick={() => {
                          setActiveSession(session.id);
                          setShowDropdown(false);
                        }}
                      >
                        <span className={`terminal-status-dot ${session.status}`} />
                        <TerminalIcon size={12} className="bp-session-icon" />
                        <span>{session.name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="bp-icon-group">
                <button
                  type="button"
                  className="bp-icon-btn"
                  title="New Terminal (Ctrl+Shift+`)"
                  onClick={() => void handleNewTerminal()}
                  disabled={isSpawning}
                >
                  <Plus size={14} />
                </button>
                <button
                  type="button"
                  className="bp-icon-btn"
                  title="Close Active Terminal"
                  onClick={() => void handleKillTerminal()}
                  disabled={!activeSessionId}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </>
          )}
          <div className="bp-icon-group bp-panel-actions">
            <button
              type="button"
              className="bp-icon-btn"
              title={isMaximized ? 'Restore Panel' : 'Maximize Panel'}
              onClick={() => setIsMaximized((value) => !value)}
            >
              {isMaximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button type="button" className="bp-icon-btn" title="Close Panel" onClick={onClose}>
              <X size={14} />
            </button>
          </div>
        </div>
      </div>

      <div className="bp-content">
        <div className={`bp-pane ${activeTab === 'terminal' ? 'active' : ''}`}>
          <TerminalTab
            visible={activeTab === 'terminal'}
            isSpawning={isSpawning}
            spawnError={spawnError}
            onSpawnNew={handleNewTerminal}
            onRestart={handleRestartTerminal}
          />
        </div>
        {activeTab === 'output' && <div className="bp-pane active"><OutputTab /></div>}
        {activeTab === 'problems' && <div className="bp-pane active"><ProblemsTab /></div>}
        {activeTab === 'gitDiff' && <div className="bp-pane active"><GitDiffTab /></div>}
      </div>
    </div>
  );
}
