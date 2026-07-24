import React, { useEffect, useMemo, useState } from 'react';
import {
  Bot, BookOpen, Braces, CheckCircle2, Cpu, FileText, GitBranch, Info,
  Keyboard, Languages, Lock, Search, Settings2, Shapes, ShieldCheck,
  Sliders, SquareTerminal, Trash2, Wrench, X,
} from 'lucide-react';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import { useAgentStore } from '../../store/useAgentStore';
import { useProjectStore } from '../../store/useProjectStore';
import type { EditorTheme } from '../../services/theme';
import {
  getActiveRules, getProjectMemory, listAgentPermissions, lspStatus,
  removeAgentPermission, saveProjectMemory, testModelConnection,
} from '../../services/bridge';
import './Settings.css';

export const APP_VERSION = '2.0.0';

type CategoryId =
  | 'appearance' | 'editor' | 'files' | 'terminal' | 'languages'
  | 'shortcuts' | 'privacy'
  | 'model' | 'modes' | 'tools' | 'rules' | 'validation' | 'memory'
  | 'permissions' | 'advanced' | 'about';

interface CategoryDef {
  id: CategoryId;
  label: string;
  icon: React.ReactNode;
  group: 'Editor' | 'Agent' | '';
}

const CATEGORIES: CategoryDef[] = [
  { id: 'appearance', label: 'Appearance', icon: <Shapes size={14} />, group: 'Editor' },
  { id: 'editor', label: 'Editor', icon: <Sliders size={14} />, group: 'Editor' },
  { id: 'files', label: 'Files', icon: <FileText size={14} />, group: 'Editor' },
  { id: 'terminal', label: 'Terminal', icon: <SquareTerminal size={14} />, group: 'Editor' },
  { id: 'languages', label: 'Languages', icon: <Languages size={14} />, group: 'Editor' },
  { id: 'shortcuts', label: 'Shortcuts', icon: <Keyboard size={14} />, group: 'Editor' },
  { id: 'privacy', label: 'Privacy', icon: <Lock size={14} />, group: 'Editor' },
  { id: 'model', label: 'Model', icon: <Cpu size={14} />, group: 'Agent' },
  { id: 'modes', label: 'Modes & Autonomy', icon: <Bot size={14} />, group: 'Agent' },
  { id: 'tools', label: 'Tools', icon: <Wrench size={14} />, group: 'Agent' },
  { id: 'rules', label: 'Rules', icon: <GitBranch size={14} />, group: 'Agent' },
  { id: 'validation', label: 'Validation', icon: <CheckCircle2 size={14} />, group: 'Agent' },
  { id: 'memory', label: 'Memory', icon: <BookOpen size={14} />, group: 'Agent' },
  { id: 'permissions', label: 'Permissions', icon: <ShieldCheck size={14} />, group: 'Agent' },
  { id: 'advanced', label: 'Advanced', icon: <Braces size={14} />, group: 'Agent' },
  { id: 'about', label: 'About', icon: <Info size={14} />, group: '' },
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
          <span className="settings-row-category">
            {category.group ? `${category.group} › ` : ''}{category.label}
          </span>
        )}
        <div className="settings-row-label">{row.label}</div>
        <div className="settings-row-desc">{row.description}</div>
      </div>
      <div className="settings-control">{row.control}</div>
    </div>
  );
}

/** Tool groups exposed as on/off toggles (mapped to belt tool names). */
const TOOL_GROUPS: { id: string; label: string; description: string; tools: string[] }[] = [
  { id: 'shell', label: 'Shell Commands', tools: ['run_command'],
    description: 'Run build, test, and terminal commands (still permission-gated).' },
  { id: 'writes', label: 'File Modifications',
    tools: ['write_file', 'edit_file', 'create_directory', 'move_path'],
    description: 'Create, edit, and move files. Off = the agent becomes read-only.' },
  { id: 'skills', label: 'Skills', tools: ['load_skill'],
    description: 'Load workflow skills (commit, code-review, …) on demand.' },
  { id: 'memory', label: 'Memory Tool', tools: ['remember'],
    description: 'Save durable project facts for future runs.' },
];

export default function SettingsPage({ onClose, initialTab = 'editor' }: SettingsPageProps) {
  const editor = useEditorSettingsStore();
  const agent = useAgentStore();
  const { projectPath } = useProjectStore();
  const [category, setCategory] = useState<CategoryId>(
    initialTab === 'agent' ? 'model' : 'editor');
  const [query, setQuery] = useState('');

  const [permissions, setPermissions] = useState<string[]>([]);
  const [memory, setMemory] = useState('');
  const [memoryDirty, setMemoryDirty] = useState(false);
  const [servers, setServers] = useState<Record<string, string>>({});
  const [connection, setConnection] = useState('');
  const [activeRules, setActiveRules] = useState<string | null>(null);

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

  const handleShowRules = async () => {
    try {
      const res = await getActiveRules();
      setActiveRules(res?.success ? (res.rules || '(no rules files found — add AGENTS.md, NEXCODER.md, or .nexcoder/rules/*.md)') : '(unavailable)');
    } catch {
      setActiveRules('(unavailable)');
    }
  };

  const toolGroupEnabled = (tools: string[]) =>
    !tools.some((t) => agent.settings.disabledTools.includes(t));

  const setToolGroup = (tools: string[], enabled: boolean) => {
    const current = new Set(agent.settings.disabledTools);
    for (const tool of tools) {
      if (enabled) current.delete(tool);
      else current.add(tool);
    }
    agent.updateSetting('disabledTools', Array.from(current));
  };

  // ── Declarative rows ─────────────────────────────────────────────
  const rows: RowDef[] = useMemo(() => [
    // Appearance
    {
      id: 'theme', category: 'appearance', label: 'Editor Theme',
      description: 'Choose the color theme for the editor.',
      control: (
        <select className="input" value={editor.settings.theme}
          onChange={(e) => editor.updateSetting('theme', e.target.value as EditorTheme)}>
          <option value="nexcoder">NexCoder Dark</option>
          <option value="vs-dark">VS Dark</option>
          <option value="light">Light</option>
          <option value="hc-black">High Contrast Black</option>
          <option value="dark-plus">Dark Plus</option>
          <option value="github-dark">GitHub Dark</option>
          <option value="vs">VS</option>
        </select>
      ),
    },
    {
      id: 'uiScale', category: 'appearance', label: 'UI Scale',
      description: 'Zoom the whole interface (percent).', keywords: 'zoom size',
      control: <input className="input" type="number" min={80} max={150} step={5}
        value={editor.settings.uiScale}
        onChange={(e) => editor.updateSetting('uiScale', Math.max(80, Math.min(150, parseInt(e.target.value) || 100)))} />,
    },
    {
      id: 'fontFamily', category: 'appearance', label: 'Editor Font Family',
      description: 'Blank uses the theme default (JetBrains Mono stack).',
      control: <input className="input" type="text" style={{ width: 200 }}
        placeholder="e.g. Cascadia Code" value={editor.settings.fontFamily}
        onChange={(e) => editor.updateSetting('fontFamily', e.target.value)} />,
    },
    {
      id: 'fontSize', category: 'appearance', label: 'Editor Font Size',
      description: 'Editor font size in pixels.',
      control: <input className="input" type="number" min={8} max={32}
        value={editor.settings.fontSize}
        onChange={(e) => editor.updateSetting('fontSize', Math.max(8, Math.min(32, parseInt(e.target.value) || 14)))} />,
    },
    {
      id: 'sidebarPosition', category: 'appearance', label: 'Sidebar Position',
      description: 'Which side the file explorer sidebar docks to.',
      control: (
        <select className="input" value={editor.settings.sidebarPosition}
          onChange={(e) => editor.updateSetting('sidebarPosition', e.target.value as 'left' | 'right')}>
          <option value="left">Left</option>
          <option value="right">Right</option>
        </select>
      ),
    },
    {
      id: 'aiPanelPosition', category: 'appearance', label: 'Agent Panel Position',
      description: 'Which side the AI panel docks to.',
      control: (
        <select className="input" value={editor.settings.aiPanelPosition}
          onChange={(e) => editor.updateSetting('aiPanelPosition', e.target.value as 'right' | 'left')}>
          <option value="right">Right</option>
          <option value="left">Left</option>
        </select>
      ),
    },
    // Editor
    {
      id: 'tabSize', category: 'editor', label: 'Tab Size',
      description: 'Spaces per indentation level.',
      control: <input className="input" type="number" min={1} max={8}
        value={editor.settings.tabSize}
        onChange={(e) => editor.updateSetting('tabSize', Math.max(1, Math.min(8, parseInt(e.target.value) || 2)))} />,
    },
    {
      id: 'insertSpaces', category: 'editor', label: 'Spaces Instead of Tabs',
      description: 'Indent with spaces rather than tab characters.',
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
      id: 'codeFolding', category: 'editor', label: 'Code Folding',
      description: 'Collapse code regions from the gutter.',
      control: <input type="checkbox" checked={editor.settings.codeFolding}
        onChange={(e) => editor.updateSetting('codeFolding', e.target.checked)} />,
    },
    {
      id: 'bracketMatching', category: 'editor', label: 'Bracket Matching',
      description: 'Highlight the matching bracket at the cursor.',
      control: <input type="checkbox" checked={editor.settings.bracketMatching}
        onChange={(e) => editor.updateSetting('bracketMatching', e.target.checked)} />,
    },
    {
      id: 'bracketPairColorization', category: 'editor', label: 'Bracket Pair Colorization',
      description: 'Color matching brackets by nesting depth.',
      control: <input type="checkbox" checked={editor.settings.bracketPairColorization}
        onChange={(e) => editor.updateSetting('bracketPairColorization', e.target.checked)} />,
    },
    {
      id: 'stickyScroll', category: 'editor', label: 'Sticky Scroll',
      description: 'Pin the enclosing scope headers while scrolling.',
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
      keywords: 'autosave',
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
    // Files
    {
      id: 'restoreOpenFiles', category: 'files', label: 'Restore Open Files',
      description: 'Reopen the files you had open when a project loads.',
      keywords: 'session tabs workspace restore',
      control: <input type="checkbox" checked={editor.settings.restoreOpenFiles}
        onChange={(e) => editor.updateSetting('restoreOpenFiles', e.target.checked)} />,
    },
    {
      id: 'confirmFileDelete', category: 'files', label: 'Confirm File Deletion',
      description: 'Ask before deleting files from the explorer.',
      control: <input type="checkbox" checked={editor.settings.confirmFileDelete}
        onChange={(e) => editor.updateSetting('confirmFileDelete', e.target.checked)} />,
    },
    // Terminal
    {
      id: 'terminalFontSize', category: 'terminal', label: 'Terminal Font Size',
      description: 'Applies to new terminal sessions.',
      control: <input className="input" type="number" min={8} max={24}
        value={editor.settings.terminalFontSize}
        onChange={(e) => editor.updateSetting('terminalFontSize', Math.max(8, Math.min(24, parseInt(e.target.value) || 13)))} />,
    },
    {
      id: 'terminalScrollback', category: 'terminal', label: 'Scrollback Limit',
      description: 'Lines kept in the terminal buffer (new sessions).',
      control: <input className="input" type="number" min={200} max={100000} step={1000}
        value={editor.settings.terminalScrollback}
        onChange={(e) => editor.updateSetting('terminalScrollback', Math.max(200, parseInt(e.target.value) || 5000))} />,
    },
    // Languages
    {
      id: 'lspEnabled', category: 'languages', label: 'Enable Language Servers',
      description: 'Master switch for completions, diagnostics, and navigation.',
      keywords: 'lsp intellisense',
      control: <input type="checkbox" checked={editor.settings.lspEnabled}
        onChange={(e) => editor.updateSetting('lspEnabled', e.target.checked)} />,
    },
    {
      id: 'lspDiagnostics', category: 'languages', label: 'Enable Diagnostics',
      description: 'Show errors and warnings as squiggles and in Problems.',
      control: <input type="checkbox" checked={editor.settings.lspDiagnostics}
        onChange={(e) => editor.updateSetting('lspDiagnostics', e.target.checked)} />,
    },
    {
      id: 'lspAutocomplete', category: 'languages', label: 'Enable Autocomplete',
      description: 'Language-server completions while typing.',
      control: <input type="checkbox" checked={editor.settings.lspAutocomplete}
        onChange={(e) => editor.updateSetting('lspAutocomplete', e.target.checked)} />,
    },
    // Model
    {
      id: 'aiEndpoint', category: 'model', label: 'Endpoint URL',
      description: 'OpenAI-compatible chat completions endpoint.',
      keywords: 'api server host', control: <input className="input" type="text" style={{ width: 220 }}
        value={agent.settings.aiEndpoint}
        onChange={(e) => agent.updateSetting('aiEndpoint', e.target.value)} />,
    },
    {
      id: 'aiModel', category: 'model', label: 'Model Name',
      description: 'Model id sent with every request.',
      control: <input className="input" type="text" style={{ width: 220 }}
        value={agent.settings.aiModel}
        onChange={(e) => agent.updateSetting('aiModel', e.target.value)} />,
    },
    {
      id: 'contextWindow', category: 'model', label: 'Context Size',
      description: 'Token budget per run. Must not exceed the model server’s context.',
      keywords: 'tokens window',
      control: <input className="input" type="number" min={2048} step={1024}
        value={agent.settings.contextWindow}
        onChange={(e) => agent.updateSetting('contextWindow', Math.max(2048, parseInt(e.target.value) || 32768))} />,
    },
    {
      id: 'maxOutputTokens', category: 'model', label: 'Maximum Output Tokens',
      description: 'Per-response output cap. Larger lets the agent write bigger files in one call.',
      control: <input className="input" type="number" min={1024} step={512}
        value={agent.settings.maxOutputTokens}
        onChange={(e) => agent.updateSetting('maxOutputTokens', Math.max(1024, parseInt(e.target.value) || 6144))} />,
    },
    {
      id: 'temperature', category: 'model', label: 'Temperature',
      description: 'Sampling temperature (0 = deterministic, 2 = wild). 0.2 recommended for coding.',
      control: <input className="input" type="number" min={0} max={2} step={0.1}
        value={agent.settings.temperature}
        onChange={(e) => agent.updateSetting('temperature', Math.min(2, Math.max(0, parseFloat(e.target.value) || 0)))} />,
    },
    // Modes & Autonomy
    {
      id: 'defaultAgentMode', category: 'modes', label: 'Default Mode',
      description: 'Mode new chats start in.',
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
      id: 'autonomy', category: 'modes', label: 'Autonomy Preset',
      description: 'Read Only: inspect but never modify. Review Changes: every command asks. Trusted Workspace: routine work runs, risky actions ask. Full Auto: never asks; risky actions are denied outright.',
      keywords: 'permissions approval sandbox trusted',
      control: (
        <select className="input" style={{ width: 170 }} value={agent.settings.autonomy}
          onChange={(e) => agent.updateSetting('autonomy', e.target.value as any)}>
          <option value="read_only">Read Only</option>
          <option value="ask">Review Changes</option>
          <option value="risky_only">Trusted Workspace</option>
          <option value="full_auto">Full Auto</option>
        </select>
      ),
    },
    {
      id: 'showAgentTimelineDetails', category: 'modes', label: 'Show Timeline Details',
      description: 'Expand tool output and diffs in the run transcript.',
      control: <input type="checkbox" checked={agent.settings.showAgentTimelineDetails}
        onChange={(e) => agent.updateSetting('showAgentTimelineDetails', e.target.checked)} />,
    },
    // Validation
    {
      id: 'cmdBuild', category: 'validation', label: 'Build Command',
      description: 'Blank = auto-detected from project config (package.json, pyproject, Makefile…).',
      control: <input className="input" type="text" style={{ width: 220 }}
        placeholder="auto-detect" value={agent.settings.cmdBuild}
        onChange={(e) => agent.updateSetting('cmdBuild', e.target.value)} />,
    },
    {
      id: 'cmdTest', category: 'validation', label: 'Test Command',
      description: 'Blank = auto-detected. The agent uses this to verify its work.',
      control: <input className="input" type="text" style={{ width: 220 }}
        placeholder="auto-detect" value={agent.settings.cmdTest}
        onChange={(e) => agent.updateSetting('cmdTest', e.target.value)} />,
    },
    {
      id: 'cmdLint', category: 'validation', label: 'Lint Command',
      description: 'Blank = auto-detected.',
      control: <input className="input" type="text" style={{ width: 220 }}
        placeholder="auto-detect" value={agent.settings.cmdLint}
        onChange={(e) => agent.updateSetting('cmdLint', e.target.value)} />,
    },
    // Memory
    {
      id: 'memoryEnabled', category: 'memory', label: 'Enable Project Memory',
      description: 'Inject saved project facts into every run and allow the agent to add more.',
      control: <input type="checkbox" checked={agent.settings.memoryEnabled}
        onChange={(e) => agent.updateSetting('memoryEnabled', e.target.checked)} />,
    },
    // Advanced
    {
      id: 'maxTurns', category: 'advanced', label: 'Maximum Agent Iterations',
      description: '0 = each mode’s own budget (Agent 50, Edit 25, Ask 12, …). Override with care.',
      control: <input className="input" type="number" min={0} max={200}
        value={agent.settings.maxTurns}
        onChange={(e) => agent.updateSetting('maxTurns', Math.max(0, Math.min(200, parseInt(e.target.value) || 0)))} />,
    },
    {
      id: 'adapter', category: 'advanced', label: 'Tool-Call Format',
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
    const cls = state === 'running' ? 'ok' : state === 'available' ? 'warn' : 'err';
    const label = state === 'running' ? 'running'
      : state === 'available' ? 'installed (starts on first use)'
      : state === 'failed' ? 'failed to start' : 'not installed';
    return <span className={`settings-chip ${cls}`}><span className="dot" />{label}</span>;
  };

  const sectionRows = (id: CategoryId) =>
    rows.filter((r) => r.category === id).map((row) => <Row key={row.id} row={row} />);

  const renderPanel = () => {
    const meta = CATEGORIES.find((c) => c.id === category);
    const header = (
      <div className="settings-section-title">{meta?.icon} {meta?.label}</div>
    );
    switch (category) {
      case 'languages':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              Language intelligence via LSP. Servers start on demand per language.
            </p>
            {sectionRows('languages')}
            <div className="settings-section-title" style={{ marginTop: 16 }}>Server Status</div>
            {Object.entries(servers).map(([family, state]) => (
              <div key={family} className="settings-row">
                <div className="settings-row-info">
                  <div className="settings-row-label" style={{ textTransform: 'capitalize' }}>{family}</div>
                  <div className="settings-row-desc">
                    {family === 'python' ? 'Pyright — type checking, completions, navigation.'
                      : family === 'typescript' ? 'typescript-language-server — TS and JS.'
                      : 'VS Code language server.'}
                  </div>
                </div>
                <div className="settings-control">{serverChip(state)}</div>
              </div>
            ))}
          </>
        );
      case 'shortcuts':
        return (
          <>
            {header}
            <p className="settings-section-desc">Custom keybindings are on the roadmap; the current shortcuts:</p>
            {[
              ['Ctrl+B', 'Toggle sidebar'], ['Ctrl+`', 'Toggle terminal'],
              ['Ctrl+Shift+A', 'Toggle AI panel'], ['Ctrl+S', 'Save file'],
              ['Ctrl+,', 'Open settings'], ['Ctrl+Shift+,', 'Agent settings'],
              ['/', 'Skill & mode picker (in chat)'],
            ].map(([keys, what]) => (
              <div key={keys} className="settings-row">
                <div className="settings-row-info">
                  <div className="settings-row-label">{what}</div>
                </div>
                <div className="settings-control"><span className="settings-chip">{keys}</span></div>
              </div>
            ))}
          </>
        );
      case 'privacy':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              NexCoder is local-first: source files, chat history, embeddings, terminal
              output, and secrets stay on this machine. No usage analytics or crash
              reports are collected — there is nothing to opt out of.
            </p>
            <div className="settings-row">
              <div className="settings-row-info">
                <div className="settings-row-label">Clear Local Cache</div>
                <div className="settings-row-desc">Reset UI state and preferences stored in this window (settings, open-tab history). Project data is untouched.</div>
              </div>
              <div className="settings-control">
                <button className="btn btn-ghost" style={{ fontSize: 11 }}
                  onClick={() => { if (window.confirm('Clear cached UI state and reload?')) { localStorage.clear(); location.reload(); } }}>
                  Clear & reload
                </button>
              </div>
            </div>
          </>
        );
      case 'modes':
        return (
          <>
            {header}
            {sectionRows('modes')}
            <div className="settings-section-title" style={{ marginTop: 16 }}>Always asks before</div>
            <p className="settings-section-desc">
              In Trusted Workspace these actions always prompt (Full Auto denies them outright):
              installing packages · network access (curl, wget, ssh) · deleting or force-removing
              files · git push, rebase, or hard reset · publishing · changing system settings or
              environment files. The workspace boundary and the hard blocklist can never be relaxed.
            </p>
          </>
        );
      case 'tools':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              Disable tool groups to shrink what the agent can do. Read tools (read, list,
              search) can never be disabled. Changes apply from the next run.
            </p>
            {TOOL_GROUPS.map((group) => (
              <div key={group.id} className="settings-row">
                <div className="settings-row-info">
                  <div className="settings-row-label">{group.label}</div>
                  <div className="settings-row-desc">{group.description}</div>
                </div>
                <div className="settings-control">
                  <input type="checkbox" checked={toolGroupEnabled(group.tools)}
                    onChange={(e) => setToolGroup(group.tools, e.target.checked)} />
                </div>
              </div>
            ))}
          </>
        );
      case 'rules':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              Persistent instructions loaded into every run, in order: <code>AGENTS.md</code>,{' '}
              <code>NEXCODER.md</code> (project root), then <code>.nexcoder/rules/*.md</code>.
              Rules guide the agent but can never override safety gates.
            </p>
            <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={handleShowRules}>
              Show active rules
            </button>
            {activeRules !== null && (
              <pre className="input" style={{ marginTop: 8, maxHeight: 300, overflow: 'auto', fontSize: 11, whiteSpace: 'pre-wrap', padding: 10 }}>
                {activeRules}
              </pre>
            )}
          </>
        );
      case 'memory':
        return (
          <>
            {header}
            {sectionRows('memory')}
            <div className="settings-section-title" style={{ marginTop: 16 }}>Saved Memory</div>
            {!projectPath ? (
              <div className="settings-empty">Open a project to see its memory.</div>
            ) : (
              <>
                <textarea className="input" rows={10} value={memory}
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
      case 'permissions':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              Commands allowed with &ldquo;Always&rdquo; run without prompting in this project.
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
      case 'advanced':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              Most users never need these. Wrong values degrade the agent.
            </p>
            {sectionRows('advanced')}
          </>
        );
      case 'about':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              NexCoder {APP_VERSION} — an AI-first agentic coding IDE. One agentic engine
              powers every mode; language intelligence via LSP; local-first model serving.
            </p>
            <div className="settings-row">
              <div className="settings-row-info"><div className="settings-row-label">Version</div></div>
              <div className="settings-control"><span className="settings-chip">{APP_VERSION}</span></div>
            </div>
            <div className="settings-row">
              <div className="settings-row-info"><div className="settings-row-label">Engine</div>
                <div className="settings-row-desc">v2 agentic core — mode profiles over one loop.</div></div>
              <div className="settings-control"><span className="settings-chip ok"><span className="dot" />v2</span></div>
            </div>
          </>
        );
      case 'model':
        return (
          <>
            {header}
            <p className="settings-section-desc">
              Applied live — every run reads the current values.{' '}
              <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
                onClick={handleTestConnection}>
                Test connection
              </button>
              {connection && <span style={{ marginLeft: 8 }}>{connection}</span>}
            </p>
            {sectionRows('model')}
          </>
        );
      default:
        return <>{header}{sectionRows(category)}</>;
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

  // Nav with group headers
  const nav = () => {
    let lastGroup: string | null = null;
    return CATEGORIES.map((c) => {
      const groupHeader = c.group !== lastGroup && c.group ? (
        <div key={`g-${c.group}`} style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, color: 'var(--text-tertiary)', padding: '10px 10px 2px', textTransform: 'uppercase' }}>
          {c.group}
        </div>
      ) : null;
      lastGroup = c.group;
      return (
        <React.Fragment key={c.id}>
          {groupHeader}
          <button
            className={`settings-nav-item ${category === c.id && !filtered ? 'active' : ''}`}
            onClick={() => { setQuery(''); setCategory(c.id); }}>
            {c.icon} {c.label}
          </button>
        </React.Fragment>
      );
    });
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
          <div className="settings-nav">{nav()}</div>
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
