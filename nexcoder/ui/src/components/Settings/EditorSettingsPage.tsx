import React from 'react';
import { X, Sliders, Eye, Columns2 } from 'lucide-react';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';

interface EditorSettingsPageProps {
  onClose: () => void;
}

/**
 * Editor settings page — controls the editor and workbench surface
 * (font, tabs, minimap, wrap, split direction). Opened from its own
 * TopBar button; lives behind ``Ctrl+,``.
 */
export default function EditorSettingsPage({ onClose }: EditorSettingsPageProps) {
  const { settings, updateSetting } = useEditorSettingsStore();
  const rowStyle: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-3)' };
  const labelStyle: React.CSSProperties = { fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' };
  const compactInput: React.CSSProperties = { width: '110px', padding: '4px 8px' };

  return (
    <div className="login-overlay">
      <div className="login-container" style={{ maxWidth: '620px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: '700', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Sliders size={18} style={{ color: 'var(--accent-purple)' }} /> Editor Settings
          </h2>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-tertiary)', marginTop: 'var(--space-1)' }}>
          Settings for the editor and workbench. Agent and AI backend settings live in their own panel.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', overflowY: 'auto', maxHeight: '520px', paddingRight: '4px', marginTop: 'var(--space-3)' }}>
          {/* Editor Preferences */}
          <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 'var(--space-3)' }}>
            <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: '600', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
              <Eye size={14} /> Editor Preferences
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={rowStyle}>
                <span style={labelStyle}>Font Size</span>
                <input
                  className="input"
                  type="number"
                  value={settings.fontSize}
                  onChange={(e) => updateSetting('fontSize', parseInt(e.target.value) || 12)}
                  style={compactInput}
                />
              </div>

              <div style={rowStyle}>
                <span style={labelStyle}>Tab Size</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={8}
                  value={settings.tabSize}
                  onChange={(e) => updateSetting('tabSize', Math.max(1, Math.min(8, parseInt(e.target.value) || 2)))}
                  style={compactInput}
                />
              </div>

              <div style={rowStyle}>
                <span style={labelStyle}>Line Numbers</span>
                <select
                  className="input"
                  value={settings.lineNumbers}
                  onChange={(e) => updateSetting('lineNumbers', e.target.value as 'on' | 'off' | 'relative')}
                  style={compactInput}
                >
                  <option value="on">On</option>
                  <option value="relative">Relative</option>
                  <option value="off">Off</option>
                </select>
              </div>

              <div style={rowStyle}>
                <span style={labelStyle}>Word Wrap</span>
                <select
                  className="input"
                  value={settings.wordWrap}
                  onChange={(e) => updateSetting('wordWrap', e.target.value as 'on' | 'off')}
                  style={compactInput}
                >
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </div>

              <div style={rowStyle}>
                <span style={labelStyle}>Minimap</span>
                <input
                  type="checkbox"
                  checked={settings.minimap}
                  onChange={(e) => updateSetting('minimap', e.target.checked)}
                  style={{ accentColor: 'var(--accent-purple)' }}
                />
              </div>

              <div style={rowStyle}>
                <span style={labelStyle}>Insert Spaces</span>
                <input
                  type="checkbox"
                  checked={settings.insertSpaces}
                  onChange={(e) => updateSetting('insertSpaces', e.target.checked)}
                  style={{ accentColor: 'var(--accent-purple)' }}
                />
              </div>

              <div style={rowStyle}>
                <span style={labelStyle}>Format On Save</span>
                <input
                  type="checkbox"
                  checked={settings.formatOnSave}
                  onChange={(e) => updateSetting('formatOnSave', e.target.checked)}
                  style={{ accentColor: 'var(--accent-purple)' }}
                />
              </div>
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: 'var(--font-size-sm)', fontWeight: '600', display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
              <Columns2 size={14} /> Workbench
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
              <div style={rowStyle}>
                <span style={labelStyle}>Default Split Direction</span>
                <select
                  className="input"
                  value={settings.defaultSplitDirection}
                  onChange={(e) => updateSetting('defaultSplitDirection', e.target.value as 'horizontal' | 'vertical')}
                  style={{ width: '150px', padding: '4px 8px' }}
                >
                  <option value="horizontal">Horizontal</option>
                  <option value="vertical">Vertical</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        <button className="btn btn-primary w-full" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
