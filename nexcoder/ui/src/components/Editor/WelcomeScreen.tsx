import React, { useEffect, useState } from 'react';
import { FolderOpen, Code, Cpu, Terminal, GitBranch, Settings } from 'lucide-react';
import { openFolderDialog, getRecentProjects, openProject } from '../../services/bridge';
import { useProjectStore } from '../../store/useProjectStore';

export default function WelcomeScreen() {
  const [recent, setRecent] = useState<any[]>([]);
  const { setLoading } = useProjectStore();

  useEffect(() => {
    getRecentProjects().then((res: any) => {
      if (res && res.success && res.projects) {
        setRecent(res.projects);
      }
    });
  }, []);

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

  const handleOpenRecent = async (path: string) => {
    setLoading(true);
    try {
      await openProject(path);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="empty-state h-full flex flex-col items-center justify-center fade-in" style={{ background: 'var(--bg-deep)', padding: 'var(--space-8)' }}>
      <div style={{ maxWidth: '600px', width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-6)' }}>
          <h1 style={{ fontSize: 'var(--font-size-2xl)', fontWeight: '700', color: 'var(--text-primary)', marginBottom: 'var(--space-2)' }}>
            Welcome to NexCoder
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--font-size-lg)' }}>
            An AI-first, Cursor-style code editor powered by Nexa AI
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
          {/* Quick Start */}
          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)' }}>
            <h3 style={{ fontSize: 'var(--font-size-md)', fontWeight: '600', marginBottom: 'var(--space-3)' }}>Start</h3>
            <button className="btn btn-primary w-full" onClick={handleOpenFolder} style={{ justifyContent: 'flex-start', marginBottom: 'var(--space-2)' }}>
              <FolderOpen size={16} /> Open Folder...
            </button>
            <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginTop: 'var(--space-2)' }}>
              Open an existing directory to start editing and using the AI Agent.
            </p>
          </div>

          {/* Recents */}
          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)', display: 'flex', flexDirection: 'column' }}>
            <h3 style={{ fontSize: 'var(--font-size-md)', fontWeight: '600', marginBottom: 'var(--space-3)' }}>Recent Projects</h3>
            <div className="overflow-auto flex-1" style={{ maxHeight: '150px' }}>
              {recent.length === 0 ? (
                <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>No recent projects</p>
              ) : (
                recent.map((proj) => (
                  <div
                    key={proj.path}
                    onClick={() => handleOpenRecent(proj.path)}
                    style={{
                      padding: 'var(--space-2)',
                      borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer',
                      fontSize: 'var(--font-size-sm)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      transition: 'background var(--transition-fast)'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--hover)'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    <div style={{ fontWeight: '500' }}>{proj.name}</div>
                    <div style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)' }}>{proj.path}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Shortcuts */}
        <div style={{ marginTop: 'var(--space-6)', background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-4)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', fontWeight: '600', marginBottom: 'var(--space-3)' }}>Keyboard Shortcuts</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-2)', fontSize: 'var(--font-size-sm)', color: 'var(--text-secondary)' }}>
            <div className="flex justify-between" style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '4px' }}>
              <span>Toggle Sidebar</span>
              <kbd style={{ background: 'var(--bg-elevated)', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', border: '1px solid var(--border)' }}>Ctrl + B</kbd>
            </div>
            <div className="flex justify-between" style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '4px' }}>
              <span>Toggle Terminal</span>
              <kbd style={{ background: 'var(--bg-elevated)', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', border: '1px solid var(--border)' }}>Ctrl + `</kbd>
            </div>
            <div className="flex justify-between" style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '4px' }}>
              <span>Toggle AI Panel</span>
              <kbd style={{ background: 'var(--bg-elevated)', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', border: '1px solid var(--border)' }}>Ctrl + Shift + A</kbd>
            </div>
            <div className="flex justify-between" style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '4px' }}>
              <span>Save File</span>
              <kbd style={{ background: 'var(--bg-elevated)', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', border: '1px solid var(--border)' }}>Ctrl + S</kbd>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
