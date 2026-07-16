import React, { useEffect, useState } from 'react';
import { X, Bot, Cpu, ShieldCheck, BookOpen, Trash2 } from 'lucide-react';
import { useAgentStore } from '../../store/useAgentStore';
import { useProjectStore } from '../../store/useProjectStore';
import {
  getProjectMemory,
  listAgentPermissions,
  removeAgentPermission,
  saveProjectMemory,
} from '../../services/bridge';

interface AgentSettingsPageProps {
  onClose: () => void;
}

/**
 * Agent settings page — the v2 engine's control surface: behavior
 * defaults, model backend, per-project command permissions, and the
 * project memory the agent injects into every run.
 *
 * Opened from the agent cog in the TopBar; lives behind
 * ``Ctrl+Shift+,``.
 */
export default function AgentSettingsPage({ onClose }: AgentSettingsPageProps) {
  const { settings, updateSetting } = useAgentStore();
  const { projectPath } = useProjectStore();
  const [permissions, setPermissions] = useState<string[]>([]);
  const [memory, setMemory] = useState('');
  const [memoryDirty, setMemoryDirty] = useState(false);

  useEffect(() => {
    if (!projectPath) return;
    listAgentPermissions()
      .then((res) => { if (res?.success) setPermissions(res.commands || []); })
      .catch(() => {});
    getProjectMemory()
      .then((res) => { if (res?.success) setMemory(res.content || ''); })
      .catch(() => {});
  }, [projectPath]);

  const handleRemovePermission = async (command: string) => {
    const res = await removeAgentPermission(command);
    if (res?.success) setPermissions(res.commands || []);
  };

  const handleSaveMemory = async () => {
    const res = await saveProjectMemory(memory);
    if (res?.success) setMemoryDirty(false);
  };

  const rowStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-3)' };
  const labelStyle: React.CSSProperties = { fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' };
  const compactInput: React.CSSProperties = { width: '110px', padding: '4px 8px' };
  const sectionStyle: React.CSSProperties = { borderBottom: '1px solid var(--border)', paddingBottom: 'var(--space-3)' };
  const headingStyle: React.CSSProperties = { fontSize: 'var(--font-size-sm)', fontWeight: '600', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' };
  const hintStyle: React.CSSProperties = { fontSize: '10px', color: 'var(--text-tertiary)', lineHeight: 1.4 };

  return (
    <div className="login-overlay">
      <div className="login-container" style={{ maxWidth: '620px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: '700', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Bot size={18} style={{ color: 'var(--accent-purple)' }} /> Agent Settings
          </h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginTop: 'var(--space-1)' }}>
          Controls the agent engine and the backend it talks to. Editor and workbench settings live in their own panel.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', overflowY: 'auto', maxHeight: '520px', paddingRight: '4px', marginTop: 'var(--space-3)' }}>
          <div style={sectionStyle}>
            <h3 style={headingStyle}><Bot size={14} /> Agent Behavior</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={rowStyle}>
                <span style={labelStyle}>Default Mode</span>
                <select
                  className="input"
                  value={settings.defaultAgentMode}
                  onChange={(e) => updateSetting('defaultAgentMode', e.target.value)}
                  style={compactInput}
                >
                  <option value="agent">Agent</option>
                  <option value="ask">Ask</option>
                  <option value="edit">Edit</option>
                  <option value="debug">Debug</option>
                  <option value="review">Review</option>
                  <option value="scan">Scan</option>
                </select>
              </div>
              <div style={rowStyle}>
                <div>
                  <span style={labelStyle}>Full Auto</span>
                  <div style={hintStyle}>Skip command permission prompts. Risky commands (push, hard reset, recursive delete) are still blocked.</div>
                </div>
                <input
                  type="checkbox"
                  checked={settings.fullAuto}
                  onChange={(e) => updateSetting('fullAuto', e.target.checked)}
                  style={{ accentColor: 'var(--accent-purple)' }}
                />
              </div>
              <div style={rowStyle}>
                <span style={labelStyle}>Show Timeline Details</span>
                <input
                  type="checkbox"
                  checked={settings.showAgentTimelineDetails}
                  onChange={(e) => updateSetting('showAgentTimelineDetails', e.target.checked)}
                  style={{ accentColor: 'var(--accent-purple)' }}
                />
              </div>
            </div>
          </div>

          <div style={sectionStyle}>
            <h3 style={headingStyle}><Cpu size={14} /> Model Backend</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div className="form-group">
                <span className="form-label">Endpoint URL</span>
                <input
                  className="input"
                  type="text"
                  value={settings.aiEndpoint}
                  onChange={(e) => updateSetting('aiEndpoint', e.target.value)}
                />
              </div>
              <div className="form-group">
                <span className="form-label">Model Name</span>
                <input
                  className="input"
                  type="text"
                  value={settings.aiModel}
                  onChange={(e) => updateSetting('aiModel', e.target.value)}
                />
              </div>
              <div style={rowStyle}>
                <div>
                  <span style={labelStyle}>Context Window</span>
                  <div style={hintStyle}>Tokens per run. Must not exceed what the model server was started with.</div>
                </div>
                <input
                  className="input"
                  type="number"
                  min={2048}
                  step={1024}
                  value={settings.contextWindow}
                  onChange={(e) => updateSetting('contextWindow', Math.max(2048, parseInt(e.target.value) || 32768))}
                  style={compactInput}
                />
              </div>
              <div style={rowStyle}>
                <div>
                  <span style={labelStyle}>Tool-Call Transport</span>
                  <div style={hintStyle}>XML for local GGUF models; Native for OpenAI-compatible tool calling.</div>
                </div>
                <select
                  className="input"
                  value={settings.adapter}
                  onChange={(e) => updateSetting('adapter', e.target.value as 'xml' | 'native')}
                  style={compactInput}
                >
                  <option value="xml">XML</option>
                  <option value="native">Native</option>
                </select>
              </div>
            </div>
          </div>

          <div style={sectionStyle}>
            <h3 style={headingStyle}><ShieldCheck size={14} /> Command Permissions</h3>
            {!projectPath ? (
              <p style={hintStyle}>Open a project to see its allowed commands.</p>
            ) : permissions.length === 0 ? (
              <p style={hintStyle}>No always-allowed commands yet. When you answer a permission prompt with &ldquo;Always&rdquo;, the command shows up here.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {permissions.map((command) => (
                  <div key={command} style={{ ...rowStyle, background: 'var(--bg-deep)', padding: '4px 8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                    <code className="truncate" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{command}</code>
                    <button className="btn btn-ghost btn-icon" title="Revoke" onClick={() => handleRemovePermission(command)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <h3 style={headingStyle}><BookOpen size={14} /> Project Memory</h3>
            {!projectPath ? (
              <p style={hintStyle}>Open a project to see its memory.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <p style={hintStyle}>Durable notes the agent injects into every run. Edit freely — the agent adds notes with its remember tool.</p>
                <textarea
                  className="input"
                  rows={6}
                  value={memory}
                  onChange={(e) => { setMemory(e.target.value); setMemoryDirty(true); }}
                  style={{ fontFamily: 'var(--font-code)', fontSize: '11px', resize: 'vertical' }}
                  placeholder="(empty — the agent has not saved any notes for this project)"
                />
                {memoryDirty && (
                  <button className="btn btn-primary" style={{ alignSelf: 'flex-end' }} onClick={handleSaveMemory}>
                    Save memory
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        <button className="btn btn-primary w-full" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
