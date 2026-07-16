import { create } from 'zustand';

/**
 * Agent settings — anything that affects how the AI/agent loop runs
 * (mode, iteration limits, timeline UI, AI backend connection). Kept
 * separate from editor settings so they can evolve independently and
 * ship behind their own entry point in the UI.
 *
 * Persisted under ``nexcoder_agent_settings`` in localStorage.
 */
export interface AgentSettings {
  showAgentTimelineDetails: boolean;
  maxToolIterations: number;
  scanStepDelayMs: number;
  defaultAgentMode: string;
  aiModel: string;
  aiEndpoint: string;
  toolAccess: 'full' | 'read_only';
  contextWindow: number;
  adapter: 'xml' | 'native';
  fullAuto: boolean;
  settingsVersion?: number;
}

interface AgentSettingsState {
  settings: AgentSettings;
  updateSetting: <K extends keyof AgentSettings>(key: K, value: AgentSettings[K]) => void;
}

const STORAGE_KEY = 'nexcoder_agent_settings';

// Preferred model for NexCoder agent tasks. Qwen3-Coder-30B-A3B (Q4_K_M
// GGUF, MoE with 3B active params) is markedly more reliable at agentic
// tool use than the 7B and still runs locally via partial GPU offload.
export const DEFAULT_AI_MODEL = 'qwen3-coder-30b-a3b-instruct-q4_k_m';
export const DEFAULT_AI_ENDPOINT = 'http://127.0.0.1:8002';
// Settings saved before this version had a 7B model id as the default;
// they migrate to the 30B once, then user choices stick.
const SETTINGS_VERSION = 2;
const LEGACY_DEFAULT_MODELS = new Set([
  'qwen2.5-coder-7b-instruct-q6_k',
  'qwen2.5-coder-7b-instruct-q4_k_m',
]);

export const DEFAULT_AGENT_SETTINGS: AgentSettings = {
  showAgentTimelineDetails: true,
  maxToolIterations: 12,
  scanStepDelayMs: 90,
  defaultAgentMode: 'agent',
  aiModel: DEFAULT_AI_MODEL,
  aiEndpoint: DEFAULT_AI_ENDPOINT,
  toolAccess: 'full',
  contextWindow: 32768,
  adapter: 'xml',
  fullAuto: false,
  settingsVersion: SETTINGS_VERSION,
};

export const useAgentStore = create<AgentSettingsState>((set) => ({
  settings: (() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if ((parsed.settingsVersion ?? 1) < SETTINGS_VERSION
            && LEGACY_DEFAULT_MODELS.has(parsed.aiModel)) {
          parsed.aiModel = DEFAULT_AI_MODEL;
        }
        parsed.settingsVersion = SETTINGS_VERSION;
        return { ...DEFAULT_AGENT_SETTINGS, ...parsed };
      }
      // One-time migration: pull agent fields out of the legacy
      // ``nexcoder_settings`` blob. Existing users keep their
      // preferences the first time the new split stores load.
      const legacy = localStorage.getItem('nexcoder_settings');
      if (legacy) {
        const parsed = JSON.parse(legacy);
        const migrated: Partial<AgentSettings> = {};
        for (const key of Object.keys(DEFAULT_AGENT_SETTINGS) as (keyof AgentSettings)[]) {
          if (parsed[key] !== undefined) {
            (migrated as Record<string, unknown>)[key] = parsed[key];
          }
        }
        if (migrated.aiModel && LEGACY_DEFAULT_MODELS.has(migrated.aiModel)) {
          migrated.aiModel = DEFAULT_AI_MODEL;
        }
        return { ...DEFAULT_AGENT_SETTINGS, ...migrated };
      }
      return DEFAULT_AGENT_SETTINGS;
    } catch {
      return DEFAULT_AGENT_SETTINGS;
    }
  })(),
  updateSetting: (key, value) => set((state) => {
    const updated = { ...state.settings, [key]: value };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return { settings: updated };
  }),
}));
