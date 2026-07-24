import { create } from 'zustand';
import type { AgentArtifact } from '../types';
import {
  deletePersistedArtifactFile,
  deletePersistedArtifactFiles,
  loadProjectArtifacts,
  persistProjectArtifacts,
  suggestedArtifactPath,
} from '../services/artifactRepository';

interface ArtifactState {
  artifacts: AgentArtifact[];
  activeProjectPath: string | null;
  isHydrating: boolean;
  lastError: string | null;
  hydrateProject: (projectPath: string | null) => Promise<void>;
  upsertArtifact: (artifact: AgentArtifact) => void;
  markSaved: (artifactId: string, savedPath: string) => void;
  removeArtifact: (artifactId: string) => void;
  clearProjectArtifacts: () => void;
}

function storageKey(projectPath: string): string {
  return `nexcoder_artifacts:${projectPath}`;
}

function loadArtifacts(projectPath: string | null): AgentArtifact[] {
  if (!projectPath) return [];
  try {
    const raw = localStorage.getItem(storageKey(projectPath));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveArtifacts(projectPath: string | null, artifacts: AgentArtifact[]) {
  if (!projectPath) return;
  localStorage.setItem(storageKey(projectPath), JSON.stringify(artifacts));
}

function normalizeArtifact(artifact: AgentArtifact): AgentArtifact {
  return {
    ...artifact,
    savedPath: artifact.savedPath || suggestedArtifactPath(artifact),
    status: artifact.status === 'draft' ? 'generated' : artifact.status,
    updatedAt: artifact.updatedAt || Date.now(),
  };
}

function sortedArtifacts(artifacts: AgentArtifact[]): AgentArtifact[] {
  return [...artifacts].sort((a, b) => b.updatedAt - a.updatedAt);
}

let persistTimer: ReturnType<typeof setTimeout> | null = null;

function persist(projectPath: string | null, artifacts: AgentArtifact[]) {
  saveArtifacts(projectPath, artifacts);
  if (!projectPath) return;
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(() => {
    const state = useArtifactStore.getState();
    const latestArtifacts = state.activeProjectPath === projectPath ? state.artifacts : artifacts;
    void persistProjectArtifacts(latestArtifacts).catch((error) => {
      useArtifactStore.setState({
        lastError: error instanceof Error ? error.message : String(error),
      });
    });
  }, 150);
}

export const useArtifactStore = create<ArtifactState>((set, get) => ({
  artifacts: [],
  activeProjectPath: null,
  isHydrating: false,
  lastError: null,
  hydrateProject: async (projectPath) => {
    const localArtifacts = sortedArtifacts(loadArtifacts(projectPath).map(normalizeArtifact));
    set({
      activeProjectPath: projectPath,
      artifacts: localArtifacts,
      isHydrating: Boolean(projectPath),
      lastError: null,
    });
    if (!projectPath) {
      set({ isHydrating: false });
      return;
    }

    try {
      const diskArtifacts = sortedArtifacts((await loadProjectArtifacts()).map(normalizeArtifact));
      if (get().activeProjectPath !== projectPath) return;
      const artifacts = diskArtifacts.length ? diskArtifacts : localArtifacts;
      set({ artifacts, isHydrating: false });
      if (!diskArtifacts.length && localArtifacts.length) {
        persist(projectPath, localArtifacts);
      } else {
        saveArtifacts(projectPath, artifacts);
      }
    } catch (error) {
      if (get().activeProjectPath !== projectPath) return;
      set({
        isHydrating: false,
        lastError: error instanceof Error ? error.message : String(error),
      });
    }
  },
  upsertArtifact: (artifact) => set((state) => {
    const normalized = normalizeArtifact(artifact);
    const existingIndex = state.artifacts.findIndex((item) => item.id === normalized.id);
    const artifacts = existingIndex >= 0
      ? state.artifacts.map((item, index) => index === existingIndex ? normalized : item)
      : [normalized, ...state.artifacts];
    const sorted = sortedArtifacts(artifacts);
    persist(state.activeProjectPath || normalized.projectPath, sorted);
    return { artifacts: sorted, lastError: null };
  }),
  markSaved: (artifactId, savedPath) => set((state) => {
    const artifacts = state.artifacts.map((artifact) => (
      artifact.id === artifactId
        ? { ...artifact, status: 'saved' as const, savedPath, updatedAt: Date.now() }
        : artifact
    ));
    const sorted = sortedArtifacts(artifacts);
    persist(state.activeProjectPath, sorted);
    return { artifacts: sorted, lastError: null };
  }),
  removeArtifact: (artifactId) => set((state) => {
    const removed = state.artifacts.find((artifact) => artifact.id === artifactId);
    const artifacts = state.artifacts.filter((artifact) => artifact.id !== artifactId);
    if (removed && state.activeProjectPath) {
      void deletePersistedArtifactFile(removed).catch((error) => {
        useArtifactStore.setState({
          lastError: error instanceof Error ? error.message : String(error),
        });
      });
    }
    persist(state.activeProjectPath, artifacts);
    return { artifacts, lastError: null };
  }),
  clearProjectArtifacts: () => {
    const projectPath = get().activeProjectPath;
    const artifacts = get().artifacts;
    if (projectPath) {
      localStorage.removeItem(storageKey(projectPath));
      if (persistTimer) {
        clearTimeout(persistTimer);
        persistTimer = null;
      }
      void deletePersistedArtifactFiles(artifacts).catch((error) => {
        useArtifactStore.setState({
          lastError: error instanceof Error ? error.message : String(error),
        });
      });
    }
    set({ artifacts: [] });
  },
}));
