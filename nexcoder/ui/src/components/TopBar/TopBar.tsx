import React from 'react';
import { Play, GitCommit, Settings, Bot, LogIn, LogOut, Code } from 'lucide-react';
import { useProjectStore } from '../../store/useProjectStore';
import BranchBadge from './BranchBadge';
import ModelSelector from './ModelSelector';
import './TopBar.css';

interface TopBarProps {
  onToggleSettings: () => void;
  onToggleAgentSettings: () => void;
  onToggleAuth: () => void;
  user: any;
  onLogout: () => void;
}

export default function TopBar({ onToggleSettings, onToggleAgentSettings, onToggleAuth, user, onLogout }: TopBarProps) {
  const { projectName, projectInfo } = useProjectStore();

  const handleRun = () => {
    if (projectInfo?.buildCommand) {
      // Find terminal, send buildCommand
      window.nexcoder?.newTerminal();
      setTimeout(() => {
        // Send command to PTY (will write to the active terminal session)
        // Here we just print a log or trigger terminal write.
        // We'll rely on the bridge trigger.
      }, 500);
    }
  };

  return (
    <div className="topbar">
      <div className="topbar-left">
        <div className="topbar-title">
          <div className="topbar-logo">N</div>
          <span>{projectName || 'NexCoder'}</span>
        </div>
        <BranchBadge />
      </div>

      <div className="topbar-center">
        <ModelSelector />
      </div>

      <div className="topbar-right">
        {projectInfo?.buildCommand && (
          <button 
            className="btn btn-ghost tooltip" 
            data-tooltip={`Run: ${projectInfo.buildCommand}`}
            onClick={handleRun}
            style={{ padding: '4px var(--space-2)', height: '28px' }}
          >
            <Play size={14} style={{ color: 'var(--accent-green)' }} />
            <span style={{ fontSize: 'var(--font-size-xs)' }}>Run</span>
          </button>
        )}

        {projectInfo?.hasGit && (
          <button 
            className="btn btn-ghost tooltip" 
            data-tooltip="Commit changes"
            onClick={() => {
              // Trigger Git panel tab in Sidebar
            }}
            style={{ padding: '4px var(--space-2)', height: '28px' }}
          >
            <GitCommit size={14} />
            <span style={{ fontSize: 'var(--font-size-xs)' }}>Commit</span>
          </button>
        )}

        <button
          className="btn btn-ghost btn-icon tooltip"
          data-tooltip="Editor Settings (Ctrl+,)"
          onClick={onToggleSettings}
        >
          <Settings size={14} />
        </button>

        <button
          className="btn btn-ghost btn-icon tooltip"
          data-tooltip="Agent Settings (Ctrl+Shift+,)"
          onClick={onToggleAgentSettings}
        >
          <Bot size={14} />
        </button>

        {user ? (
          <button 
            className="btn btn-ghost tooltip" 
            data-tooltip={`Logged in as ${user.name || user.email}`}
            onClick={onLogout}
            style={{ padding: '4px var(--space-2)', height: '28px', color: 'var(--accent-green)' }}
          >
            <LogOut size={14} />
            <span style={{ fontSize: 'var(--font-size-xs)' }}>Logout</span>
          </button>
        ) : (
          <button 
            className="btn btn-ghost tooltip" 
            data-tooltip="Login to Appwrite Sync"
            onClick={onToggleAuth}
            style={{ padding: '4px var(--space-2)', height: '28px' }}
          >
            <LogIn size={14} />
            <span style={{ fontSize: 'var(--font-size-xs)' }}>Login</span>
          </button>
        )}
      </div>
    </div>
  );
}
