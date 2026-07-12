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
}

interface AgentSettingsState {
  settings: AgentSettings;
  updateSetting: <K extends keyof AgentSettings>(key: K, value: AgentSettings[K]) => void;
}

const STORAGE_KEY = 'nexcoder_agent_settings';

// Preferred model for NexCoder agent tasks. Qwen2.5-Coder-7B-Instruct
// (Q6_K GGUF) is the quality-focused local default for coding and tool use.
// workflows than the previous default (Gemma 4 12B Agentic), so it
// is the recommended default for the agent runner.
export const DEFAULT_AI_MODEL = 'qwen2.5-coder-7b-instruct-q6_k';
const LEGACY_Q4_MODEL = 'qwen2.5-coder-7b-instruct-q4_k_m';
export const DEFAULT_AI_ENDPOINT = 'http://127.0.0.1:8001';

export const DEFAULT_AGENT_SETTINGS: AgentSettings = {
  showAgentTimelineDetails: true,
  maxToolIterations: 12,
  scanStepDelayMs: 90,
  defaultAgentMode: 'agent',
  aiModel: DEFAULT_AI_MODEL,
  aiEndpoint: DEFAULT_AI_ENDPOINT,
  toolAccess: 'full',
};

export const useAgentStore = create<AgentSettingsState>((set) => ({
  settings: (() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.aiModel === LEGACY_Q4_MODEL) parsed.aiModel = DEFAULT_AI_MODEL;
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
        if (migrated.aiModel === LEGACY_Q4_MODEL) migrated.aiModel = DEFAULT_AI_MODEL;
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
