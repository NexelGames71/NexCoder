import { create } from 'zustand';
import { EditorGroup, OpenFile } from '../types';

/**
 * Editor state — the *content* and *layout* of the editor surface
 * (open files, tabs, groups, active file). Distinct from
 * ``useEditorSettingsStore``, which holds the user's editor
 * *preferences* (font size, tab size, etc.). Splitting them keeps
 * re-renders cheap and stops a font-size tweak from invalidating
 * the whole editor surface.
 */
interface EditorState {
  editorGroups: EditorGroup[];
  activeGroupId: string;

  openFile: (file: OpenFile, groupId?: string) => void;
  setActiveGroup: (id: string) => void;
  setActiveFile: (path: string, groupId?: string) => void;
  closeFile: (path: string, groupId?: string) => void;
  splitEditor: () => void;
  closeGroup: (id: string) => void;

  setFileDirty: (path: string, isDirty: boolean) => void;
  updateFileContent: (path: string, content: string) => void;
  replaceFileContent: (file: OpenFile, originalPath?: string) => void;
}

const newGroup = (id: string = 'g1'): EditorGroup => ({
  id,
  openFiles: [],
  activeFilePath: null,
});

const findFileAcrossGroups = (groups: EditorGroup[], path: string) => {
  for (const group of groups) {
    const found = group.openFiles.find((file) => file.path === path);
    if (found) return found;
  }
  return null;
};

const mutateGroup = (
  groups: EditorGroup[],
  groupId: string,
  mutator: (group: EditorGroup) => EditorGroup,
): EditorGroup[] => groups.map((group) => (group.id === groupId ? mutator(group) : group));

export const useEditorStateStore = create<EditorState>((set, get) => ({
  editorGroups: [newGroup()],
  activeGroupId: 'g1',

  openFile: (file, groupId) =>
    set((state) => {
      const targetGroupId = groupId || state.activeGroupId;
      return {
        editorGroups: mutateGroup(state.editorGroups, targetGroupId, (group) => {
          const existing = group.openFiles.some((item) => item.path === file.path);
          return {
            ...group,
            openFiles: existing
              ? group.openFiles.map((item) => item.path === file.path ? { ...item, ...file } : item)
              : [...group.openFiles, { ...file, isDirty: file.isDirty ?? false }],
            activeFilePath: file.path,
          };
        }),
        activeGroupId: targetGroupId,
      };
    }),

  setActiveGroup: (id) => set({ activeGroupId: id }),

  setActiveFile: (path, groupId) =>
    set((state) => ({
      editorGroups: mutateGroup(state.editorGroups, groupId || state.activeGroupId, (group) => ({
        ...group,
        activeFilePath: path,
      })),
    })),

  closeFile: (path, groupId) =>
    set((state) => {
      const editorGroups = mutateGroup(state.editorGroups, groupId || state.activeGroupId, (group) => {
        const remaining = group.openFiles.filter((file) => file.path !== path);
        return {
          ...group,
          openFiles: remaining,
          activeFilePath:
            group.activeFilePath === path
              ? remaining.length > 0
                ? remaining[remaining.length - 1].path
                : null
              : group.activeFilePath,
        };
      });
      return { editorGroups };
    }),

  splitEditor: () =>
    set((state) => {
      const nextId = `g${state.editorGroups.length + 1}-${Date.now().toString(36)}`;
      return {
        editorGroups: [...state.editorGroups, newGroup(nextId)],
        activeGroupId: nextId,
      };
    }),

  closeGroup: (id) =>
    set((state) => {
      if (state.editorGroups.length <= 1) return state;
      const editorGroups = state.editorGroups.filter((group) => group.id !== id);
      return {
        editorGroups,
        activeGroupId:
          state.activeGroupId === id ? editorGroups[editorGroups.length - 1].id : state.activeGroupId,
      };
    }),

  setFileDirty: (path, isDirty) =>
    set((state) => ({
      editorGroups: state.editorGroups.map((group) => ({
        ...group,
        openFiles: group.openFiles.map((file) =>
          file.path === path ? { ...file, isDirty } : file,
        ),
      })),
    })),

  updateFileContent: (path, content) =>
    set((state) => ({
      editorGroups: state.editorGroups.map((group) => ({
        ...group,
        openFiles: group.openFiles.map((file) =>
          file.path === path ? { ...file, content, isDirty: true } : file,
        ),
      })),
    })),

  replaceFileContent: (file, originalPath) =>
    set((state) => {
      const targetPath = originalPath || file.path;
      let found = false;
      const editorGroups = state.editorGroups.map((group) => ({
        ...group,
        openFiles: group.openFiles.map((existing) => {
          if (existing.path !== targetPath) return existing;
          found = true;
          return { ...file, isDirty: false };
        }),
      }));
      if (found) return { editorGroups };
      // No existing tab for this path — add it to the active group.
      const activeGroupId = state.activeGroupId;
      return {
        editorGroups: mutateGroup(editorGroups, activeGroupId, (group) => ({
          ...group,
          openFiles: [...group.openFiles, { ...file, isDirty: false }],
          activeFilePath: file.path,
        })),
      };
    }),
}));

/** Convenience selectors that match the previous ``useEditorStore`` shape
 *  so older call sites keep working while we migrate them. */
export const selectActiveFile = (state: EditorState): OpenFile | null => {
  const group = state.editorGroups.find((g) => g.id === state.activeGroupId);
  if (!group || !group.activeFilePath) return null;
  return group.openFiles.find((f) => f.path === group.activeFilePath) || null;
};

export const selectOpenFiles = (state: EditorState): OpenFile[] => {
  const group = state.editorGroups.find((g) => g.id === state.activeGroupId);
  return group ? group.openFiles : [];
};

export const selectActiveFileOrAny = (state: EditorState): OpenFile | null => {
  return selectActiveFile(state) || findFileAcrossGroups(state.editorGroups, '');
};
