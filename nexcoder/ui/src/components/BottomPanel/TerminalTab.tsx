import React, { useEffect, useRef, useCallback, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { Terminal as TerminalIcon, X, Plus } from 'lucide-react';
import '@xterm/xterm/css/xterm.css';
import { 
  writeTerminal, 
  resizeTerminal, 
  killTerminal, 
  onTerminalOutput, 
  onTerminalExited 
} from '../../services/bridge';
import { useTerminalStore } from '../../store/useTerminalStore';
import { useProjectStore } from '../../store/useProjectStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';

interface TerminalTabProps {
  onSpawnNew: () => void;
}

export default function TerminalTab({ onSpawnNew }: TerminalTabProps) {
  const xtermsRef = useRef<Record<string, { term: Terminal; fitAddon: FitAddon }>>({});
  const wrapperRef = useRef<HTMLDivElement>(null);
  const focusedSessionRef = useRef<string | null>(null);
  const [focusedSessionId, setFocusedSessionId] = useState<string | null>(null);
  
  const { projectPath } = useProjectStore();
  const { sessions, activeSessionId, removeSession, setActiveSession } = useTerminalStore();

  // Spawns a default session if there are none
  useEffect(() => {
    if (sessions.length === 0) {
      onSpawnNew();
    }
  }, [sessions.length, onSpawnNew]);

  // Global I/O signal routing
  useEffect(() => {
    const handleOutput = (sid: string, data: string) => {
      const termObj = xtermsRef.current[sid];
      if (termObj) {
        termObj.term.write(data);
      }
    };

    onTerminalOutput(handleOutput);

    const handleExit = (sid: string, code: number) => {
      const termObj = xtermsRef.current[sid];
      if (termObj) {
        termObj.term.write(`\r\n\x1b[90mTerminal process terminated with exit code: ${code}\x1b[0m\r\n`);
      }
      removeSession(sid);
    };

    onTerminalExited(handleExit);
  }, [removeSession]);

  // Clean up terminal instances when they are removed from the store
  useEffect(() => {
    const sessionIds = new Set(sessions.map(s => s.id));
    Object.keys(xtermsRef.current).forEach(id => {
      if (!sessionIds.has(id)) {
        xtermsRef.current[id].term.dispose();
        delete xtermsRef.current[id];
        if (focusedSessionRef.current === id) {
          focusedSessionRef.current = null;
          setFocusedSessionId(null);
        }
      }
    });
  }, [sessions]);

  // Fit active terminal without stealing keyboard focus.
  useEffect(() => {
    if (activeSessionId) {
      const termObj = xtermsRef.current[activeSessionId];
      if (termObj) {
        requestAnimationFrame(() => {
          termObj.fitAddon.fit();
        });
      }
    }
  }, [activeSessionId]);

  // Blur xterm when the user clicks outside the terminal surface.
  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        const focused = focusedSessionRef.current;
        if (focused && xtermsRef.current[focused]) {
          xtermsRef.current[focused].term.blur();
        }
        focusedSessionRef.current = null;
        setFocusedSessionId(null);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown, true);
    return () => document.removeEventListener('pointerdown', handlePointerDown, true);
  }, []);

  // Handle panel resizing
  useEffect(() => {
    if (!wrapperRef.current) return;

    const observer = new ResizeObserver(() => {
      if (activeSessionId) {
        const termObj = xtermsRef.current[activeSessionId];
        if (termObj) {
          requestAnimationFrame(() => {
            termObj.fitAddon.fit();
          });
        }
      }
    });

    observer.observe(wrapperRef.current);
    return () => observer.disconnect();
  }, [activeSessionId]);

  // Callback ref to initialize terminals when their container mounts
  const initializeTerminal = useCallback((sessionId: string, container: HTMLDivElement) => {
    if (xtermsRef.current[sessionId]) return;

    const prefs = useEditorSettingsStore.getState().settings;
    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: 'block',
      fontSize: prefs.terminalFontSize || 14,
      fontFamily: "'Cascadia Code', 'Consolas', 'Courier New', monospace",
      fontWeight: '400',
      lineHeight: 1.2,
      letterSpacing: 0,
      scrollback: Math.max(200, prefs.terminalScrollback || 5000),
      allowTransparency: false,
      theme: {
        background: '#1e1e1e',
        foreground: '#cccccc',
        cursor: '#aeafad',
        cursorAccent: '#1e1e1e',
        selectionBackground: '#264f78',
        black:   '#000000',
        red:     '#cd3131',
        green:   '#0dbc79',
        yellow:  '#e5e510',
        blue:    '#2472c8',
        magenta: '#bc3fbc',
        cyan:    '#11a8cd',
        white:   '#e5e5e5',
        brightBlack:   '#666666',
        brightRed:     '#f14c4c',
        brightGreen:   '#23d18b',
        brightYellow:  '#f5f543',
        brightBlue:    '#3b8eea',
        brightMagenta: '#d670d6',
        brightCyan:    '#29b8db',
        brightWhite:   '#e5e5e5',
      },
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(container);

    term.onData((data) => {
      if (focusedSessionRef.current === sessionId) {
        writeTerminal(sessionId, data);
      }
    });

    term.onResize((size) => {
      resizeTerminal(sessionId, size.cols, size.rows);
    });

    xtermsRef.current[sessionId] = { term, fitAddon };

    requestAnimationFrame(() => {
      fitAddon.fit();
      resizeTerminal(sessionId, term.cols, term.rows);
    });
  }, [activeSessionId]);

  const focusTerminal = useCallback((sessionId: string) => {
    const previousFocused = focusedSessionRef.current;
    if (previousFocused && previousFocused !== sessionId && xtermsRef.current[previousFocused]) {
      xtermsRef.current[previousFocused].term.blur();
    }

    setActiveSession(sessionId);
    focusedSessionRef.current = sessionId;
    setFocusedSessionId(sessionId);

    const termObj = xtermsRef.current[sessionId];
    if (termObj) {
      requestAnimationFrame(() => {
        termObj.fitAddon.fit();
        termObj.term.focus();
      });
    }
  }, [setActiveSession]);

  const blurFocusedTerminal = useCallback(() => {
    const focused = focusedSessionRef.current;
    if (focused && xtermsRef.current[focused]) {
      xtermsRef.current[focused].term.blur();
    }
    focusedSessionRef.current = null;
    setFocusedSessionId(null);
  }, []);

  const handleCloseSession = async (sid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await killTerminal(sid);
      removeSession(sid);
    } catch (err) {
      console.error('Failed to close terminal session:', err);
    }
  };

  return (
    <div className="terminal-surface" ref={wrapperRef}>
      {/* Left: Terminal viewports (stacked, only active is displayed) */}
      <div className="terminal-viewports">
        {sessions.map(s => (
          <div
            key={s.id}
            ref={(el) => {
              if (el) initializeTerminal(s.id, el);
            }}
            className={`terminal-viewport-container ${s.id === focusedSessionId ? 'focused' : ''}`}
            onMouseDown={() => focusTerminal(s.id)}
            style={{ display: s.id === activeSessionId ? 'block' : 'none' }}
          />
        ))}
      </div>

      {/* Right: Terminal tab selection sidebar (VS Code style) */}
      <div className="terminal-sidebar" onMouseDown={blurFocusedTerminal}>
        <div className="terminal-sidebar-header">
          <span>TERMINALS</span>
          <button className="terminal-sidebar-add-btn" onClick={onSpawnNew} title="New Terminal">
            <Plus size={12} />
          </button>
        </div>
        <div className="terminal-sidebar-list">
          {sessions.map(s => (
            <div
              key={s.id}
              className={`terminal-sidebar-item ${s.id === activeSessionId ? 'active' : ''}`}
              onClick={() => setActiveSession(s.id)}
            >
              <TerminalIcon size={12} className="ts-icon" />
              <span className="ts-name">{s.name}</span>
              <button 
                className="ts-close-btn" 
                onClick={(e) => handleCloseSession(s.id, e)}
                title="Kill Terminal"
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
