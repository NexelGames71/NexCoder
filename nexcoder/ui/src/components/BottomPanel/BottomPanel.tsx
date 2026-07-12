import React, { useEffect, useRef, useState } from 'react';
import { Terminal as TerminalIcon, Code, AlertCircle, GitBranch, Plus, SplitSquareHorizontal, Trash2, ChevronDown, Maximize2, X } from 'lucide-react';
import TerminalTab from './TerminalTab';
import OutputTab from './OutputTab';
import ProblemsTab from './ProblemsTab';
import GitDiffTab from './GitDiffTab';
import { useTerminalStore } from '../../store/useTerminalStore';
import { useProjectStore } from '../../store/useProjectStore';
import { spawnTerminal, killTerminal } from '../../services/bridge';
import './BottomPanel.css';

interface BottomPanelProps {
  isCollapsed: boolean;
  onClose: () => void;
}

export default function BottomPanel({ isCollapsed, onClose }: BottomPanelProps) {
  const [activeTab, setActiveTab] = useState<'terminal' | 'output' | 'problems' | 'gitDiff'>('terminal');
  const [showDropdown, setShowDropdown] = useState(false);

  const { projectPath } = useProjectStore();
  const { sessions, activeSessionId, addSession, removeSession, setActiveSession, clearSessions } = useTerminalStore();
  const previousProjectRef = useRef(projectPath);

  useEffect(() => {
    const previousProject = previousProjectRef.current;
    previousProjectRef.current = projectPath;
    if (!previousProject || !projectPath || previousProject === projectPath || sessions.length === 0) {
      return;
    }

    const staleSessionIds = sessions.map((session) => session.id);
    Promise.allSettled(staleSessionIds.map((sessionId) => killTerminal(sessionId)))
      .finally(() => clearSessions());
  }, [projectPath, sessions, clearSessions]);

  if (isCollapsed) return null;

  const activeSession = sessions.find(s => s.id === activeSessionId);

  const handleNewTerminal = async () => {
    const workingDir = projectPath || '';
    try {
      const res: any = await spawnTerminal(workingDir);
      if (res) {
        // Handle both object and JSON string response formats
        let parsed = res;
        if (typeof res === 'string') {
          parsed = JSON.parse(res);
        }
        if (parsed.success && parsed.sessionId) {
          const nextIndex = sessions.length + 1;
          const name = `powershell <${nextIndex}>`;
          addSession({
            id: parsed.sessionId,
            cwd: workingDir,
            isActive: true,
            name: name,
          });
        }
      }
    } catch (e) {
      console.error('Failed to spawn terminal:', e);
    }
  };

  const handleKillTerminal = async () => {
    if (activeSessionId) {
      try {
        await killTerminal(activeSessionId);
        removeSession(activeSessionId);
      } catch (e) {
        console.error('Failed to kill terminal:', e);
      }
    }
  };

  const renderActiveTab = () => {
    switch (activeTab) {
      case 'terminal':
        return <TerminalTab onSpawnNew={handleNewTerminal} />;
      case 'output':
        return <OutputTab />;
      case 'problems':
        return <ProblemsTab />;
      case 'gitDiff':
        return <GitDiffTab />;
      default:
        return <TerminalTab onSpawnNew={handleNewTerminal} />;
    }
  };

  return (
    <div className="bp-container">
      {/* VS Code style header */}
      <div className="bp-header">
        {/* Left: panel type tabs */}
        <div className="bp-tabs">
          <button
            className={`bp-tab ${activeTab === 'problems' ? 'active' : ''}`}
            onClick={() => setActiveTab('problems')}
          >
            PROBLEMS
          </button>
          <button
            className={`bp-tab ${activeTab === 'output' ? 'active' : ''}`}
            onClick={() => setActiveTab('output')}
          >
            OUTPUT
          </button>
          <button
            className={`bp-tab ${activeTab === 'terminal' ? 'active' : ''}`}
            onClick={() => setActiveTab('terminal')}
          >
            TERMINAL
          </button>
          <button
            className={`bp-tab ${activeTab === 'gitDiff' ? 'active' : ''}`}
            onClick={() => setActiveTab('gitDiff')}
          >
            GIT DIFF
          </button>
        </div>

        {/* Right: terminal session controls (only when terminal tab active) */}
        <div className="bp-right-controls">
          {activeTab === 'terminal' && (
            <>
              <div 
                className="bp-session-selector" 
                onClick={() => setShowDropdown(!showDropdown)}
              >
                <TerminalIcon size={12} className="bp-session-icon" />
                <span className="bp-session-name">{activeSession?.name || 'powershell'}</span>
                <ChevronDown size={12} className="bp-session-arrow" />

                {showDropdown && sessions.length > 0 && (
                  <div className="bp-dropdown-menu">
                    {sessions.map(s => (
                      <div 
                        key={s.id} 
                        className={`bp-dropdown-item ${s.id === activeSessionId ? 'active' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveSession(s.id);
                          setShowDropdown(false);
                        }}
                      >
                        <TerminalIcon size={12} className="bp-session-icon" />
                        <span>{s.name}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="bp-icon-group">
                <button 
                  className="bp-icon-btn" 
                  title="New Terminal (Ctrl+Shift+`)" 
                  onClick={handleNewTerminal}
                >
                  <Plus size={14} />
                </button>
                <button 
                  className="bp-icon-btn" 
                  title="Split Terminal" 
                  onClick={handleNewTerminal}
                >
                  <SplitSquareHorizontal size={14} />
                </button>
                <button 
                  className="bp-icon-btn" 
                  title="Kill Active Terminal" 
                  onClick={handleKillTerminal}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </>
          )}
          <div className="bp-icon-group bp-panel-actions">
            <button className="bp-icon-btn" title="Maximize Panel">
              <Maximize2 size={14} />
            </button>
            <button 
              className="bp-icon-btn" 
              title="Close Panel" 
              onClick={onClose}
            >
              <X size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Tab content */}
      <div className="bp-content">
        {renderActiveTab()}
      </div>
    </div>
  );
}
