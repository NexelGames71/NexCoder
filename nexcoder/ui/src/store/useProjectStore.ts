import { create } from 'zustand';
import { FileNode, Project } from '../types';

interface ProjectState {
  projectPath: string | null;
  projectName: string | null;
  projectInfo: Project | null;
  fileTree: FileNode[];
  recentProjects: Project[];
  isLoading: boolean;
  setProject: (path: string, name: string, info: Project) => void;
  setFileTree: (tree: FileNode[]) => void;
  setRecentProjects: (projects: Project[]) => void;
  setLoading: (loading: boolean) => void;
  closeProject: () => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  projectPath: null,
  projectName: null,
  projectInfo: null,
  fileTree: [],
  recentProjects: [],
  isLoading: false,
  setProject: (path, name, info) => set({ projectPath: path, projectName: name, projectInfo: info }),
  setFileTree: (tree) => set({ fileTree: tree }),
  setRecentProjects: (projects) => set({ recentProjects: projects }),
  setLoading: (loading) => set({ isLoading: loading }),
  closeProject: () => set({ projectPath: null, projectName: null, projectInfo: null, fileTree: [] }),
}));
