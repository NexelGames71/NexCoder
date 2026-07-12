import React from 'react';
import { X, Bot, Cpu, Database } from 'lucide-react';
import { useAgentStore } from '../../store/useAgentStore';

interface AgentSettingsPageProps {
  onClose: () => void;
}

/**
 * Agent settings page — controls the AI/agent loop and the model
 * backend it talks to. Lives in its own modal so editor changes and
 * agent changes never share a save round-trip.
 *
 * Opened from the agent cog in the TopBar; lives behind
 * ``Ctrl+Shift+,``.
 */
export default function AgentSettingsPage({ onClose }: AgentSettingsPageProps) {
  const { settings, updateSetting } = useAgentStore();
  const rowStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-3)' };
  const labelStyle: React.CSSProperties = { fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' };
  const compactInput: React.CSSProperties = { width: '110px', padding: '4px 8px' };

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
          Controls the AI/agent loop and the backend it talks to. Editor and workbench settings live in their own panel.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', overflowY: 'auto', maxHeight: '520px', paddingRight: '4px', marginTop: 'var(--space-3)' }}>
          <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 'var(--space-3)' }}>
            <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: '600', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
              <Bot size={14} /> Agent Behavior
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={rowStyle}>
                <span style={labelStyle}>Default Mode</span>
                <select
                  className="input"
                  value={settings.defaultAgentMode}
                  onChange={(e) => updateSetting('defaultAgentMode', e.target.value)}
                  style={compactInput}
                >
                  <option value="ask">Ask</option>
                  <option value="agent">Agent</option>
                  <option value="scan">Scan</option>
                  <option value="debug">Debug</option>
                  <option value="review">Review</option>
                </select>
              </div>
              <div style={rowStyle}>
                <span style={labelStyle}>Tool Access</span>
                <select
                  className="input"
                  value={settings.toolAccess}
                  onChange={(e) => updateSetting('toolAccess', e.target.value as 'full' | 'read_only')}
                  style={compactInput}
                >
                  <option value="full">Full access</option>
                  <option value="read_only">Read only</option>
                </select>
              </div>
              <div style={rowStyle}>
                <span style={labelStyle}>Max Tool Iterations</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={40}
                  value={settings.maxToolIterations}
                  onChange={(e) => updateSetting('maxToolIterations', Math.max(1, Math.min(40, parseInt(e.target.value) || 12)))}
                  style={compactInput}
                />
              </div>
              <div style={rowStyle}>
                <span style={labelStyle}>Scan Step Delay</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={1000}
                  value={settings.scanStepDelayMs}
                  onChange={(e) => updateSetting('scanStepDelayMs', Math.max(0, Math.min(1000, parseInt(e.target.value) || 0)))}
                  style={compactInput}
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

          {/* AI Backend */}
          <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 'var(--space-3)' }}>
            <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: '600', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
              <Cpu size={14} /> AI Backend
            </h3>
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
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: '600', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
              <Database size={14} /> Appwrite Database (Phase 3)
            </h3>
            <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', lineHeight: '1.4' }}>
              Connection status: <strong>Online</strong><br />
              Endpoint: <code>https://sgp.cloud.appwrite.io/v1</code><br />
              Project: <code>6a1c615b001a7362068c</code>
            </p>
          </div>
        </div>

        <button className="btn btn-primary w-full" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
