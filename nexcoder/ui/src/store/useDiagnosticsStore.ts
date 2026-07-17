import { create } from 'zustand';

/** One LSP diagnostic, as published by the language server. */
export interface LspDiagnostic {
  range: {
    start: { line: number; character: number };
    end: { line: number; character: number };
  };
  message: string;
  severity?: number; // 1 error, 2 warning, 3 info, 4 hint
  source?: string;
  code?: string | number;
}

interface DiagnosticsState {
  byPath: Record<string, LspDiagnostic[]>;
  setForPath: (path: string, diagnostics: LspDiagnostic[]) => void;
  clear: () => void;
}

export const useDiagnosticsStore = create<DiagnosticsState>((set) => ({
  byPath: {},
  setForPath: (path, diagnostics) =>
    set((state) => {
      const byPath = { ...state.byPath };
      if (diagnostics.length === 0) {
        delete byPath[path];
      } else {
        byPath[path] = diagnostics;
      }
      return { byPath };
    }),
  clear: () => set({ byPath: {} }),
}));
