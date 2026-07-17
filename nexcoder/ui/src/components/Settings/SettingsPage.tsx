import React, { useEffect, useMemo, useState } from 'react';
import {
  Bot, BookOpen, Cpu, Info, Languages, Search, Settings2, ShieldCheck,
  Sliders, Trash2, X,
} from 'lucide-react';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import { useAgentStore } from '../../store/useAgentStore';
import { useProjectStore } from '../../store/useProjectStore';
import {
  getProjectMemory, listAgentPermissions, lspStatus,
  removeAgentPermission, saveProjectMemory, testModelConnection,
} from '../../services/bridge';
import './Settings.css';

export const APP_VERSION = '2.0.0';

type CategoryId =
  | 'editor' | 'agent' | 'backend' | 'languages'
  | 'permissions' | 'memory' | 'about';

const CATEGORIES: { id: CategoryId; label: string; icon: React.ReactNode }[] = [
  { id: 'editor', label: 'Editor', icon: <Sliders size={14} /> },
  { id: 'agent', label: 'AI Agent', icon: <Bot size={14} /> },
  { id: 'backend', label: 'Model Backend', icon: <Cpu size={14} /> },
  { id: 'languages', label: 'Language Servers', icon: <Languages size={14} /> },
  { id: 'permissions', label: 'Permissions', icon: <ShieldCheck size={14} /> },
  { id: 'memory', label: 'Project Memory', icon: <BookOpen size={14} /> },
  { id: 'about', label: 'About', icon: <Info size={14} /> },
];

interface SettingsPageProps {
  onClose: () => void;
  initialTab?: 'editor' | 'agent';
}

interface RowDef {
  id: string;
  category: CategoryId;
  label: string;
  description: string;
  keywords?: string;
  control: React.ReactNode;
}

function Row({ row, showCategory }: { row: RowDef; showCategory?: boolean }) {
  const category = CATEGORIES.find((c) => c.id === row.category);
  return (
    <div className="settings-row">
      <div className="settings-row-info">
        {showCategory && category && (
          <span className="settings-row-category">{category.label}</span>
        )}
        <div className="settings-row-label">{row.label}</div>
        <div className="settings-row-desc">{row.description}</div>
      </div>
      <div className="settings-control">{row.control}</div>
    </div>
  );
}

/**
 * Unified, searchable settings window. Every simple setting is a
 * declarative row (searchable by label/description); stateful panels
 * (permissions, memory, server status, backend health) render inside
 * their categories.
 */
export default function SettingsPage({ onClose, initialTab = 'editor' }: SettingsPageProps) {
  const editor = useEditorSettingsStore();
  const agent = useAgentStore();
  const { projectPath } = useProjectStore();
  const [category, setCategory] = useState<CategoryId>(initialTab);
  const [query, setQuery] = useState('');

  // ── Live panels state ────────────────────────────────────────────
  const [permissions, setPermissions] = useState<string[]>([]);
  const [memory, setMemory] = useState('');
  const [memoryDirty, setMemoryDirty] = useState(false);
  const [servers, setServers] = useState<Record<string, string>>({});
  const [connection, setConnection] = useState<string>('');

  useEffect(() => {
    if (projectPath) {
      listAgentPermissions().then((r) => { if (r?.success) setPermissions(r.commands || []); }).catch(() => {});
      getProjectMemory().then((r) => { if (r?.success) setMemory(r.content || ''); }).catch(() => {});
    }
    lspStatus().then((r) => { if (r?.success) setServers(r.servers || {}); }).catch(() => {});
  }, [projectPath]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleTestConnection = async () => {
    setConnection('testing…');
    try {
      const res = await testModelConnection();
      if (res?.connected) {
        const models = res.models?.data?.map((m: any) => m.id) || [];
        setConnection(`connected${models.length ? `: ${models[0]}` : ''}`);
      } else {
        setConnection(`unreachable — ${res?.error || 'unknown error'}`);
      }
    } catch (e) {
      setConnection(`unreachable — ${String(e)}`);
    }
  };

  const handleRemovePermission = async (command: string) => {
    const res = await removeAgentPermission(command);
    if (res?.success) setPermissions(res.commands || []);
  };

  const handleSaveMemory = async () => {
    const res = await saveProjectMemory(memory);
    if (res?.success) setMemoryDirty(false);
  };

  // ── Declarative rows ─────────────────────────────────────────────
  const rows: RowDef[] = useMemo(() => [
    // Editor
    {
      id: 'fontSize', category: 'editor', label: 'Font Size',
      description: 'Editor font size in pixels.',
      control: <input className="input" type="number" min={8} max={32}
        value={editor.settings.fontSize}
        onChange={(e) => editor.updateSetting('fontSize', Math.max(8, Math.min(32, parseInt(e.target.value) || 14)))} />,
    },
    {
      id: 'tabSize', category: 'editor', label: 'Tab Size',
      description: 'Spaces per indentation level.',
      control: <input className="input" type="number" min={1} max={8}
        value={editor.settings.tabSize}
        onChange={(e) => editor.updateSetting('tabSize', Math.max(1, Math.min(8, parseInt(e.target.value) || 2)))} />,
    },
    {
      id: 'insertSpaces', category: 'editor', label: 'Insert Spaces',
      description: 'Use spaces instead of tab characters when indenting.',
      control: <input type="checkbox" checked={editor.settings.insertSpaces}
        onChange={(e) => editor.updateSetting('insertSpaces', e.target.checked)} />,
    },
    {
      id: 'wordWrap', category: 'editor', label: 'Word Wrap',
      description: 'Wrap long lines instead of horizontal scrolling.',
      control: (
        <select className="input" value={editor.settings.wordWrap}
          onChange={(e) => editor.updateSetting('wordWrap', e.target.value as 'on' | 'off')}>
          <option value="on">On</option>
          <option value="off">Off</option>
        </select>
      ),
    },
    {
      id: 'lineNumbers', category: 'editor', label: 'Line Numbers',
      description: 'Absolute, relative, or hidden line numbers.',
      control: (
        <select className="input" value={editor.settings.lineNumbers}
          onChange={(e) => editor.updateSetting('lineNumbers', e.target.value as 'on' | 'off' | 'relative')}>
          <option value="on">On</option>
          <option value="relative">Relative</option>
          <option value="off">Off</option>
        </select>
      ),
    },
    {
      id: 'minimap', category: 'editor', label: 'Minimap',
      description: 'Show the code minimap on the right edge.',
      control: <input type="checkbox" checked={editor.settings.minimap}
        onChange={(e) => editor.updateSetting('minimap', e.target.checked)} />,
    },
    {
      id: 'bracketPairColorization', category: 'editor', label: 'Bracket Pair Colorization',
      description: 'Color matching brackets by nesting depth.',
      control: <input type="checkbox" checked={editor.settings.bracketPairColorization}
        onChange={(e) => editor.updateSetting('bracketPairColorization', e.target.checked)} />,
    },
    {
      id: 'stickyScroll', category: 'editor', label: 'Sticky Scroll',
      description: 'Pin the enclosing scope headers to the top while scrolling.',
      control: <input type="checkbox" checked={editor.settings.stickyScroll}
        onChange={(e) => editor.updateSetting('stickyScroll', e.target.checked)} />,
    },
    {
      id: 'formatOnSave', category: 'editor', label: 'Format On Save',
      description: 'Run the document formatter before every save.',
      control: <input type="checkbox" checked={editor.settings.formatOnSave}
        onChange={(e) => editor.updateSetting('formatOnSave', e.target.checked)} />,
    },
    {
      id: 'autoSave', category: 'editor', label: 'Auto Save',
      description: 'Write changes to disk about a second after typing stops.',
      keywords: 'autosave save automatically',
      control: <input type="checkbox" checked={editor.settings.autoSave}
        onChange={(e) => editor.updateSetting('autoSave', e.target.checked)} />,
    },
    {
      id: 'defaultSplitDirection', category: 'editor', label: 'Default Split Direction',
      description: 'Direction used when splitting the editor.',
      control: (
        <select className="input" value={editor.settings.defaultSplitDirection}
          onChange={(e) => editor.updateSetting('defaultSplitDirection', e.target.value as 'horizontal' | 'vertical')}>
          <option value="horizontal">Horizontal</option>
          <option value="vertical">Vertical</option>
        </select>
      ),
    },
    // Agent
    {
      id: 'defaultAgentMode', category: 'agent', label: 'Default Mode',
      description: 'Mode the AI panel starts in.',
      control: (
        <select className="input" value={agent.settings.defaultAgentMode}
          onChange={(e) => agent.updateSetting('defaultAgentMode', e.target.value)}>
          <option value="agent">Agent</option>
          <option value="plan">Plan</option>
          <option value="ask">Ask</option>
          <option value="edit">Edit</option>
          <option value="debug">Debug</option>
          <option value="review">Review</option>
          <option value="scan">Scan</option>
          <option value="terminal">Terminal</option>
        </select>
      ),
    },
    {
      id: 'autonomy', category: 'agent', label: 'Autonomy',
      description: 'Which commands run without asking. Read-only commands never prompt; risky commands (installs, network, git push, deletes) are denied outright in Full auto.',
      keywords: 'permissions approval yolo full auto',
      control: (
        <select className="input" value={agent.settings.autonomy}
          onChange={(e) => agent.updateSetting('autonomy', e.target.value as any)}>
          <option value="read_only">Read only</option>
          <option value="ask">Ask every time</option>
          <option value="risky_only">Ask for risky</option>
          <option value="full_auto">Full auto</option>
        </select>
      ),
    },
    {
      id: 'showAgentTimelineDetails', category: 'agent', label: 'Show Timeline Details',
      description: 'Expand tool output and diffs in the run transcript.',
      control: <input type="checkbox" checked={agent.settings.showAgentTimelineDetails}
        onChange={(e) => agent.updateSetting('showAgentTimelineDetails', e.target.checked)} />,
    },
    // Backend
    {
      id: 'aiEndpoint', category: 'backend', label: 'Endpoint URL',
      description: 'OpenAI-compatible chat completions endpoint.',
      keywords: 'api url server host',
      control: <input className="input" type="text" style={{ width: 220 }}
        value={agent.settings.aiEndpoint}
        onChange={(e) => agent.updateSetting('aiEndpoint', e.target.value)} />,
    },
    {
      id: 'aiModel', category: 'backend', label: 'Model Name',
      description: 'Model id sent with every request.',
      control: <input className="input" type="text" style={{ width: 220 }}
        value={agent.settings.aiModel}
        onChange={(e) => agent.updateSetting('aiModel', e.target.value)} />,
    },
    {
      id: 'contextWindow', category: 'backend', label: 'Context Window',
      description: 'Token budget per run. Must not exceed what the model server was started with.',
      keywords: 'tokens context size compaction',
      control: <input className="input" type="number" min={2048} step={1024}
        value={agent.settings.contextWindow}
        onChange={(e) => agent.updateSetting('contextWindow', Math.max(2048, parseInt(e.target.value) || 32768))} />,
    },
    {
      id: 'adapter', category: 'backend', label: 'Tool-Call Transport',
      description: 'XML for local GGUF models; Native for OpenAI-style function calling.',
      control: (
        <select className="input" value={agent.settings.adapter}
          onChange={(e) => agent.updateSetting('adapter', e.target.value as 'xml' | 'native')}>
          <option value="xml">XML</option>
          <option value="native">Native</option>
        </select>
      ),
    },
  ], [editor, agent]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return rows.filter((row) =>
      [row.label, row.description, row.keywords || '', row.category]
        .join(' ').toLowerCase().includes(q));
  }, [query, rows]);

  const serverChip = (state: string) => {
    const cls = state === 'running' ? 'ok'
      : state === 'available' ? 'warn'
      : 'err';
    const label = state === 'running' ? 'running'
      : state === 'available' ? 'installed (starts on first use)'
      : state === 'failed' ? 'failed to start'
      : 'not installed';
    return <span className={`settings-chip ${cls}`}><span className="dot" />{label}</span>;
  };

  const renderPanel = () => {
    if (category === 'languages') {
      return (
        <>
          <div className="settings-section-title"><Languages size={14} /> Language Servers</div>
          <p className="settings-section-desc">
            Completions, diagnostics, go-to-definition, references and rename are powered
            by real language servers (LSP). Servers start on demand when a file of their
            language opens. Missing servers: run <code>npm install</code> inside <code>language-servers/</code>.
          </p>
          {Object.keys(servers).length === 0 ? (
            <div className="settings-empty">Server status unavailable.</div>
          ) : (
            Object.entries(servers).map(([family, state]) => (
              <div key={family} className="settings-row">
                <div className="settings-row-info">
                  <div className="settings-row-label" style={{ textTransform: 'capitalize' }}>{family}</div>
                  <div className="settings-row-desc">
                    {family === 'python' ? 'Pyright — type checking, completions, navigation.'
                      : family === 'typescript' ? 'typescript-language-server — TS and JS intelligence.'
                      : 'VS Code language server.'}
                  </div>
                </div>
                <div className="settings-control">{serverChip(state)}</div>
              </div>
            ))
          )}
        </>
      );
    }
    if (category === 'permissions') {
      return (
        <>
          <div className="settings-section-title"><ShieldCheck size={14} /> Command Permissions</div>
          <p className="settings-section-desc">
            Commands you allowed with &ldquo;Always&rdquo; run without prompting in this project.
            Revoke any of them here. The hard blocklist (destructive commands) cannot be relaxed.
          </p>
          {!projectPath ? (
            <div className="settings-empty">Open a project to see its allowed commands.</div>
          ) : permissions.length === 0 ? (
            <div className="settings-empty">No always-allowed commands yet.</div>
          ) : (
            permissions.map((command) => (
              <div key={command} className="settings-list-item">
                <code>{command}</code>
                <button className="btn btn-ghost btn-icon" title="Revoke"
                  onClick={() => handleRemovePermission(command)}>
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </>
      );
    }
    if (category === 'memory') {
      return (
        <>
          <div className="settings-section-title"><BookOpen size={14} /> Project Memory</div>
          <p className="settings-section-desc">
            Durable notes the agent injects into every run — architecture facts, build
            commands, conventions. The agent adds notes with its remember tool; edit freely.
          </p>
          {!projectPath ? (
            <div className="settings-empty">Open a project to see its memory.</div>
          ) : (
            <>
              <textarea className="input" rows={14} value={memory}
                onChange={(e) => { setMemory(e.target.value); setMemoryDirty(true); }}
                style={{ width: '100%', fontFamily: 'var(--font-code)', fontSize: 11, resize: 'vertical' }}
                placeholder="(empty — the agent has not saved any notes for this project)" />
              {memoryDirty && (
                <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={handleSaveMemory}>
                  Save memory
                </button>
              )}
            </>
          )}
        </>
      );
    }
    if (category === 'about') {
      return (
        <>
          <div className="settings-section-title"><Info size={14} /> About NexCoder</div>
          <p className="settings-section-desc">
            NexCoder {APP_VERSION} — an AI-first agentic coding IDE for the Nexa ecosystem.
            One agentic engine powers every mode; language intelligence via LSP; local-first
            model serving.
          </p>
          <div className="settings-row">
            <div className="settings-row-info">
              <div className="settings-row-label">Version</div>
              <div className="settings-row-desc">Application version.</div>
            </div>
            <div className="settings-control"><span className="settings-chip">{APP_VERSION}</span></div>
          </div>
          <div className="settings-row">
            <div className="settings-row-info">
              <div className="settings-row-label">Engine</div>
              <div className="settings-row-desc">v2 agentic core — profiles over one loop.</div>
            </div>
            <div className="settings-control"><span className="settings-chip ok"><span className="dot" />v2</span></div>
          </div>
          <div className="settings-row">
            <div className="settings-row-info">
              <div className="settings-row-label">Keyboard Shortcuts</div>
              <div className="settings-row-desc">
                Ctrl+B sidebar · Ctrl+` terminal · Ctrl+Shift+A AI panel · Ctrl+S save ·
                Ctrl+, settings · Ctrl+Shift+, agent settings
              </div>
            </div>
          </div>
        </>
      );
    }
    const categoryRows = rows.filter((r) => r.category === category);
    const meta = CATEGORIES.find((c) => c.id === category);
    return (
      <>
        <div className="settings-section-title">{meta?.icon} {meta?.label}</div>
        {category === 'backend' && (
          <p className="settings-section-desc">
            Applied live — every run reads the current values.{' '}
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
              onClick={handleTestConnection}>
              Test connection
            </button>
            {connection && <span style={{ marginLeft: 8 }}>{connection}</span>}
          </p>
        )}
        {categoryRows.map((row) => <Row key={row.id} row={row} />)}
      </>
    );
  };

  return (
    <div className="settings-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="settings-window">
        <div className="settings-header">
          <h2><Settings2 size={16} style={{ color: 'var(--accent-purple)' }} /> Settings</h2>
          <div className="settings-search" style={{ position: 'relative' }}>
            <Search size={12} style={{ position: 'absolute', left: 8, top: 8, color: 'var(--text-tertiary)' }} />
            <input className="input" placeholder="Search settings" value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{ width: '100%', paddingLeft: 26 }} autoFocus />
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onClose} style={{ marginLeft: 'auto' }}>
            <X size={16} />
          </button>
        </div>
        <div className="settings-layout">
          <div className="settings-nav">
            {CATEGORIES.map((c) => (
              <button key={c.id}
                className={`settings-nav-item ${category === c.id && !filtered ? 'active' : ''}`}
                onClick={() => { setQuery(''); setCategory(c.id); }}>
                {c.icon} {c.label}
              </button>
            ))}
          </div>
          <div className="settings-body">
            {filtered ? (
              filtered.length === 0 ? (
                <div className="settings-empty">No settings match &ldquo;{query}&rdquo;.</div>
              ) : (
                filtered.map((row) => <Row key={row.id} row={row} showCategory />)
              )
            ) : renderPanel()}
          </div>
        </div>
      </div>
    </div>
  );
}
