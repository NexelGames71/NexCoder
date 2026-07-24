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
  /** Command autonomy: read_only | ask | risky_only | full_auto */
  autonomy: 'read_only' | 'ask' | 'risky_only' | 'full_auto';
  maxOutputTokens: number;
  temperature: number;
  /** 0 = use each mode profile's own turn budget. */
  maxTurns: number;
  /** Tool names removed from the agent's belt. */
  disabledTools: string[];
  memoryEnabled: boolean;
  cmdBuild: string;
  cmdTest: string;
  cmdLint: string;
  settingsVersion?: number;
}

interface AgentSettingsState {
  settings: AgentSettings;
  updateSetting: <K extends keyof AgentSettings>(key: K, value: AgentSettings[K]) => void;
  hydrateSettings: (settings: Partial<AgentSettings>) => void;
}

const STORAGE_KEY = 'nexcoder_agent_settings';

// Preferred model for NexCoder agent tasks. GLM-5.2 (z-ai/glm-5.2) is a
// strong general-purpose model served through the NVIDIA NIM endpoint and
// is the verified default for new installs.
export const DEFAULT_AI_MODEL = 'z-ai/glm-5.2';
export const DEFAULT_AI_ENDPOINT = 'https://integrate.api.nvidia.com/v1';
// Settings saved before this version had an older model id as the default;
// they migrate to GLM-5.2 once, then user choices stick.
const SETTINGS_VERSION = 4;
const LEGACY_DEFAULT_MODELS = new Set([
  'qwen2.5-coder-7b-instruct-q6_k',
  'qwen2.5-coder-7b-instruct-q4_k_m',
  'qwen3-coder-30b-a3b-instruct-q4_k_m',
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
  adapter: 'native',
  fullAuto: false,
  autonomy: 'ask',
  maxOutputTokens: 6144,
  temperature: 0.2,
  maxTurns: 0,
  disabledTools: [],
  memoryEnabled: true,
  cmdBuild: '',
  cmdTest: '',
  cmdLint: '',
  settingsVersion: SETTINGS_VERSION,
};

export const useAgentStore = create<AgentSettingsState>((set) => ({
  settings: (() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        const storedVersion = parsed.settingsVersion ?? 1;
        if (storedVersion < 4) {
          if (LEGACY_DEFAULT_MODELS.has(parsed.aiModel)) {
            parsed.aiModel = DEFAULT_AI_MODEL;
          }
          if (!parsed.aiEndpoint || parsed.aiEndpoint === 'https://nexcoder.trynexa-ai.com/v1') {
            parsed.aiEndpoint = DEFAULT_AI_ENDPOINT;
          }
          // Native tool-call adapter is the verified default for the
          // current model lineup; migrate once from the legacy xml adapter.
          if (parsed.adapter === 'xml' || parsed.adapter === undefined) {
            parsed.adapter = 'native';
          }
        }
        parsed.settingsVersion = SETTINGS_VERSION;
        const loaded = { ...DEFAULT_AGENT_SETTINGS, ...parsed };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(loaded));
        return loaded;
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
        if (!migrated.aiEndpoint || migrated.aiEndpoint === 'https://nexcoder.trynexa-ai.com/v1') {
          migrated.aiEndpoint = DEFAULT_AI_ENDPOINT;
        }
        const loaded = { ...DEFAULT_AGENT_SETTINGS, ...migrated, settingsVersion: SETTINGS_VERSION };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(loaded));
        return loaded;
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(DEFAULT_AGENT_SETTINGS));
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
  hydrateSettings: (incoming) => set((state) => {
    const updated = { ...state.settings, ...incoming };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return { settings: updated };
  }),
}));
