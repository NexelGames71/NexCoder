import { create } from 'zustand';
import { GitStatus, GitCommit } from '../types';

interface GitState {
  status: GitStatus | null;
  commits: GitCommit[];
  isLoading: boolean;
  setStatus: (status: GitStatus | null) => void;
  setCommits: (commits: GitCommit[]) => void;
  setLoading: (loading: boolean) => void;
}

export const useGitStore = create<GitState>((set) => ({
  status: null,
  commits: [],
  isLoading: false,
  setStatus: (status) => set({ status }),
  setCommits: (commits) => set({ commits }),
  setLoading: (loading) => set({ isLoading: loading }),
}));
