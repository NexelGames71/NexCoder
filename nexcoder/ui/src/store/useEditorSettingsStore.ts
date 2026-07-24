import { create } from 'zustand';
import type { EditorTheme } from '../services/theme';

/**
 * Editor *settings* — what the user sees and types in the editor
 * surface itself (font, tab, wrap, minimap, format-on-save, split
 * direction). Persisted under ``nexcoder_editor_settings`` in
 * localStorage.
 *
 * Kept distinct from ``useEditorStateStore`` (which holds editor
 * content/layout) and from ``useAgentStore`` (agent/AI behaviour).
 * The two settings stores power the two independent settings modals
 * in the TopBar.
 */
export interface EditorSettings {
  theme: EditorTheme;
  fontSize: number;
  wordWrap: 'on' | 'off';
  minimap: boolean;
  tabSize: number;
  insertSpaces: boolean;
  formatOnSave: boolean;
  lineNumbers: 'on' | 'off' | 'relative';
  defaultSplitDirection: 'horizontal' | 'vertical';
  /** Write changes to disk automatically ~1s after typing stops. */
  autoSave: boolean;
  bracketPairColorization: boolean;
  stickyScroll: boolean;
  // Appearance
  fontFamily: string;            // '' = theme default
  uiScale: number;               // percent, 100 = default
  sidebarPosition: 'left' | 'right';
  aiPanelPosition: 'right' | 'left';
  // Editor extras
  codeFolding: boolean;
  bracketMatching: boolean;
  // Files
  restoreOpenFiles: boolean;
  confirmFileDelete: boolean;
  // Terminal
  terminalFontSize: number;
  terminalScrollback: number;
  // Language intelligence
  lspEnabled: boolean;
  lspDiagnostics: boolean;
  lspAutocomplete: boolean;
}

interface EditorSettingsState {
  settings: EditorSettings;
  updateSetting: <K extends keyof EditorSettings>(key: K, value: EditorSettings[K]) => void;
}

const STORAGE_KEY = 'nexcoder_editor_settings';

export const DEFAULT_EDITOR_SETTINGS: EditorSettings = {
  theme: 'nexcoder',
  fontSize: 14,
  wordWrap: 'on',
  minimap: false,
  tabSize: 2,
  insertSpaces: true,
  formatOnSave: false,
  lineNumbers: 'on',
  defaultSplitDirection: 'horizontal',
  autoSave: false,
  bracketPairColorization: true,
  stickyScroll: false,
  fontFamily: '',
  uiScale: 100,
  sidebarPosition: 'left',
  aiPanelPosition: 'right',
  codeFolding: true,
  bracketMatching: true,
  restoreOpenFiles: true,
  confirmFileDelete: true,
  terminalFontSize: 13,
  terminalScrollback: 5000,
  lspEnabled: true,
  lspDiagnostics: true,
  lspAutocomplete: true,
};

export const useEditorSettingsStore = create<EditorSettingsState>((set) => ({
  settings: (() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const loaded = { ...DEFAULT_EDITOR_SETTINGS, ...JSON.parse(saved) };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(loaded));
        return loaded;
      }
      // One-time migration: pull editor fields out of the legacy
      // ``nexcoder_settings`` blob. Existing users keep their
      // preferences the first time the new split stores load.
      const legacy = localStorage.getItem('nexcoder_settings');
      if (legacy) {
        const parsed = JSON.parse(legacy);
        const migrated: Partial<EditorSettings> = {};
        for (const key of Object.keys(DEFAULT_EDITOR_SETTINGS) as (keyof EditorSettings)[]) {
          if (parsed[key] !== undefined) {
            (migrated as Record<string, unknown>)[key] = parsed[key];
          }
        }
        const loaded = { ...DEFAULT_EDITOR_SETTINGS, ...migrated };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(loaded));
        return loaded;
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_EDITOR_SETTINGS));
      return DEFAULT_EDITOR_SETTINGS;
    } catch {
      return DEFAULT_EDITOR_SETTINGS;
    }
  })(),
  updateSetting: (key, value) => set((state) => {
    const updated = { ...state.settings, [key]: value };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return { settings: updated };
  }),
}));
