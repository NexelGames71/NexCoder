import React, { useCallback, useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { AlertCircle, LoaderCircle, Plus, Terminal as TerminalIcon, X } from 'lucide-react';
import '@xterm/xterm/css/xterm.css';
import {
  getTerminalSnapshot,
  killTerminal,
  onTerminalExited,
  onTerminalOutput,
  resizeTerminal,
  writeTerminal,
} from '../../services/bridge';
import { useTerminalStore } from '../../store/useTerminalStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';

interface TerminalTabProps {
  visible: boolean;
  isSpawning: boolean;
  spawnError: string | null;
  onSpawnNew: () => void | Promise<void>;
  onRestart: (sessionId: string) => void | Promise<void>;
}

interface TerminalRuntime {
  term: Terminal;
  fitAddon: FitAddon;
  hydrated: boolean;
  sequence: number;
  queued: Map<number, string>;
  exitRendered: boolean;
  exitCode: number | null;
}

const WINDOWS_CONTROL_C_EXIT = -1073741510;

function exitMessage(code: number): string {
  if (code === WINDOWS_CONTROL_C_EXIT || code === 3221225786) {
    return '\r\n\x1b[90mThe terminal was interrupted by a Windows control event. Restart it to continue.\x1b[0m\r\n';
  }
  return `\r\n\x1b[90mThe shell exited with code ${code}. Restart it to continue.\x1b[0m\r\n`;
}

export default function TerminalTab({
  visible,
  isSpawning,
  spawnError,
  onSpawnNew,
  onRestart,
}: TerminalTabProps) {
  const runtimesRef = useRef<Record<string, TerminalRuntime>>({});
  const wrapperRef = useRef<HTMLDivElement>(null);
  const visibleRef = useRef(visible);
  const focusedSessionRef = useRef<string | null>(null);

  const {
    sessions,
    activeSessionId,
    removeSession,
    setActiveSession,
    updateSession,
  } = useTerminalStore();

  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  const renderExit = useCallback((runtime: TerminalRuntime, code: number) => {
    if (runtime.exitRendered) return;
    runtime.exitRendered = true;
    runtime.term.write(exitMessage(code));
  }, []);

  const applyOutput = useCallback((runtime: TerminalRuntime, data: string, sequence: number) => {
    if (sequence <= runtime.sequence) return;
    runtime.term.write(data);
    runtime.sequence = sequence;
  }, []);

  const hydrateTerminal = useCallback(async (sessionId: string, runtime: TerminalRuntime) => {
    const snapshot = await getTerminalSnapshot(sessionId);
    const current = runtimesRef.current[sessionId];
    if (!current || current !== runtime) return;

    if (!snapshot?.success) {
      runtime.hydrated = true;
      runtime.term.write(
        `\r\n\x1b[31mUnable to reconnect to this terminal: ${snapshot?.error || 'session unavailable'}\x1b[0m\r\n`,
      );
      updateSession(sessionId, {
        status: 'error',
        error: snapshot?.error || 'Terminal session unavailable',
      });
      return;
    }

    const chunks = Array.isArray(snapshot.chunks) ? snapshot.chunks : [];
    chunks
      .slice()
      .sort((a: any, b: any) => Number(a.sequence) - Number(b.sequence))
      .forEach((chunk: any) => {
        applyOutput(runtime, String(chunk.data || ''), Number(chunk.sequence || 0));
      });

    runtime.hydrated = true;
    Array.from(runtime.queued.entries())
      .sort(([a], [b]) => a - b)
      .forEach(([sequence, data]) => applyOutput(runtime, data, sequence));
    runtime.queued.clear();

    const status = snapshot.status === 'exited' ? 'exited' : 'running';
    const exitCode = typeof snapshot.exitCode === 'number' ? snapshot.exitCode : null;
    updateSession(sessionId, {
      cwd: snapshot.cwd || '',
      shell: snapshot.shell || '',
      name: snapshot.shell || undefined,
      status,
      exitCode,
      error: undefined,
    });
    if (status === 'exited' && exitCode !== null) {
      renderExit(runtime, exitCode);
    } else if (runtime.exitCode !== null) {
      renderExit(runtime, runtime.exitCode);
    }
  }, [applyOutput, renderExit, updateSession]);

  // Subscribe once per mount and always disconnect on panel teardown.
  useEffect(() => {
    const disconnectOutput = onTerminalOutput((sessionId, data, sequence) => {
      const runtime = runtimesRef.current[sessionId];
      if (!runtime) return;
      if (!runtime.hydrated) {
        runtime.queued.set(sequence, data);
        return;
      }
      applyOutput(runtime, data, sequence);
    });

    const disconnectExit = onTerminalExited((sessionId, exitCode) => {
      updateSession(sessionId, { status: 'exited', exitCode });
      const runtime = runtimesRef.current[sessionId];
      if (!runtime) return;
      runtime.exitCode = exitCode;
      if (runtime.hydrated) renderExit(runtime, exitCode);
    });

    return () => {
      disconnectOutput();
      disconnectExit();
    };
  }, [applyOutput, renderExit, updateSession]);

  // Dispose only removed sessions. Switching panel tabs keeps xterm alive.
  useEffect(() => {
    const sessionIds = new Set(sessions.map((session) => session.id));
    Object.keys(runtimesRef.current).forEach((sessionId) => {
      if (sessionIds.has(sessionId)) return;
      runtimesRef.current[sessionId].term.dispose();
      delete runtimesRef.current[sessionId];
      if (focusedSessionRef.current === sessionId) {
        focusedSessionRef.current = null;
      }
    });
  }, [sessions]);

  useEffect(() => () => {
    Object.values(runtimesRef.current).forEach(({ term }) => term.dispose());
    runtimesRef.current = {};
  }, []);

  const fitSession = useCallback((sessionId: string) => {
    const runtime = runtimesRef.current[sessionId];
    const element = runtime?.term.element?.parentElement;
    if (!runtime || !element || element.clientWidth < 40 || element.clientHeight < 30) return;
    try {
      runtime.fitAddon.fit();
    } catch {
      // The panel can become hidden between measurement and fitting.
    }
  }, []);

  useEffect(() => {
    if (!visible || !activeSessionId) return;
    const frame = requestAnimationFrame(() => fitSession(activeSessionId));
    return () => cancelAnimationFrame(frame);
  }, [activeSessionId, fitSession, visible]);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    const observer = new ResizeObserver(() => {
      if (!visibleRef.current) return;
      const sessionId = useTerminalStore.getState().activeSessionId;
      if (sessionId) requestAnimationFrame(() => fitSession(sessionId));
    });
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, [fitSession]);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (wrapperRef.current?.contains(event.target as Node)) return;
      const focused = focusedSessionRef.current;
      if (focused) runtimesRef.current[focused]?.term.blur();
      focusedSessionRef.current = null;
    };
    document.addEventListener('pointerdown', handlePointerDown, true);
    return () => document.removeEventListener('pointerdown', handlePointerDown, true);
  }, []);

  const initializeTerminal = useCallback((sessionId: string, container: HTMLDivElement) => {
    if (runtimesRef.current[sessionId]) return;
    const prefs = useEditorSettingsStore.getState().settings;
    const term = new Terminal({
      allowTransparency: false,
      convertEol: false,
      cursorBlink: true,
      cursorStyle: 'block',
      fontFamily: "'Cascadia Code', 'Consolas', 'Courier New', monospace",
      fontSize: prefs.terminalFontSize || 13,
      lineHeight: 1.2,
      scrollback: Math.max(200, prefs.terminalScrollback || 5000),
      theme: {
        background: '#111117',
        foreground: '#e6e6eb',
        cursor: '#a991ff',
        cursorAccent: '#111117',
        selectionBackground: '#5946a866',
        black: '#101014', red: '#f06a6a', green: '#52d6a3', yellow: '#e5c76b',
        blue: '#72a5ff', magenta: '#c58cff', cyan: '#5ed4d4', white: '#e6e6eb',
        brightBlack: '#777785', brightRed: '#ff8585', brightGreen: '#72e7bb',
        brightYellow: '#f2d98c', brightBlue: '#91b9ff', brightMagenta: '#d8aaff',
        brightCyan: '#82e5e5', brightWhite: '#ffffff',
      },
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(container);

    const runtime: TerminalRuntime = {
      term,
      fitAddon,
      hydrated: false,
      sequence: 0,
      queued: new Map(),
      exitRendered: false,
      exitCode: null,
    };
    runtimesRef.current[sessionId] = runtime;

    term.onData((data) => {
      void writeTerminal(sessionId, data);
    });
    term.onResize(({ cols, rows }) => {
      if (cols > 1 && rows > 1) void resizeTerminal(sessionId, cols, rows);
    });

    void hydrateTerminal(sessionId, runtime);
    requestAnimationFrame(() => {
      fitSession(sessionId);
      if (term.cols > 1 && term.rows > 1) {
        void resizeTerminal(sessionId, term.cols, term.rows);
      }
    });
  }, [fitSession, hydrateTerminal]);

  const focusTerminal = useCallback((sessionId: string) => {
    const previous = focusedSessionRef.current;
    if (previous && previous !== sessionId) runtimesRef.current[previous]?.term.blur();
    setActiveSession(sessionId);
    focusedSessionRef.current = sessionId;
    requestAnimationFrame(() => {
      fitSession(sessionId);
      runtimesRef.current[sessionId]?.term.focus();
    });
  }, [fitSession, setActiveSession]);

  const blurFocusedTerminal = useCallback(() => {
    const focused = focusedSessionRef.current;
    if (focused) runtimesRef.current[focused]?.term.blur();
    focusedSessionRef.current = null;
  }, []);

  const closeSession = useCallback(async (sessionId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    await killTerminal(sessionId);
    removeSession(sessionId);
  }, [removeSession]);

  return (
    <div className="terminal-surface" ref={wrapperRef} aria-hidden={!visible}>
      <div className="terminal-viewports">
        {sessions.map((session) => (
          <div
            key={session.id}
            ref={(element) => {
              if (element) initializeTerminal(session.id, element);
            }}
            className="terminal-viewport-container"
            onMouseDown={() => focusTerminal(session.id)}
            style={{ display: session.id === activeSessionId ? 'block' : 'none' }}
          />
        ))}

        {sessions.length === 0 && (
          <div className="terminal-empty-state">
            {isSpawning ? <LoaderCircle size={20} className="terminal-spinner" /> : <TerminalIcon size={22} />}
            <span>{isSpawning ? 'Starting terminal…' : 'No terminal sessions'}</span>
            {!isSpawning && (
              <button type="button" onClick={() => void onSpawnNew()}>
                <Plus size={13} /> New terminal
              </button>
            )}
          </div>
        )}

        {spawnError && (
          <div className="terminal-error-banner" role="alert">
            <AlertCircle size={14} />
            <span>{spawnError}</span>
            <button type="button" onClick={() => void onSpawnNew()}>Retry</button>
          </div>
        )}

        {sessions.map((session) => (
          session.id === activeSessionId && ['exited', 'error'].includes(session.status) ? (
            <div className="terminal-restart-banner" role="status" key={`${session.id}-restart`}>
              <AlertCircle size={15} />
              <span>{session.status === 'error' ? 'Terminal unavailable' : 'Terminal stopped'}</span>
              <button type="button" onClick={() => void onRestart(session.id)} disabled={isSpawning}>
                {isSpawning ? 'Restarting…' : 'Restart terminal'}
              </button>
            </div>
          ) : null
        ))}
      </div>

      <div className="terminal-sidebar" onMouseDown={blurFocusedTerminal}>
        <div className="terminal-sidebar-header">
          <span>TERMINALS</span>
          <button
            type="button"
            className="terminal-sidebar-add-btn"
            onClick={() => void onSpawnNew()}
            title="New Terminal"
            disabled={isSpawning}
          >
            {isSpawning ? <LoaderCircle size={12} className="terminal-spinner" /> : <Plus size={12} />}
          </button>
        </div>
        <div className="terminal-sidebar-list">
          {sessions.map((session) => (
            <div
              key={session.id}
              className={`terminal-sidebar-item ${session.id === activeSessionId ? 'active' : ''}`}
              onClick={() => focusTerminal(session.id)}
            >
              <span className={`terminal-status-dot ${session.status}`} title={session.status} />
              <TerminalIcon size={12} className="ts-icon" />
              <span className="ts-name">{session.name || session.shell || 'Terminal'}</span>
              <button
                type="button"
                className="ts-close-btn"
                onClick={(event) => void closeSession(session.id, event)}
                title="Close Terminal"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
