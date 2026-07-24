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

export interface DiagnosticEntry {
  path: string;
  shortPath: string;
  diagnostic: LspDiagnostic;
}

export interface DiagnosticCounts {
  total: number;
  errors: number;
  warnings: number;
  infos: number;
  hints: number;
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

export function countDiagnostics(byPath: Record<string, LspDiagnostic[]>): DiagnosticCounts {
  const counts: DiagnosticCounts = { total: 0, errors: 0, warnings: 0, infos: 0, hints: 0 };
  for (const diagnostics of Object.values(byPath)) {
    for (const diagnostic of diagnostics) {
      counts.total += 1;
      if (diagnostic.severity === 1) counts.errors += 1;
      else if (diagnostic.severity === 2) counts.warnings += 1;
      else if (diagnostic.severity === 4) counts.hints += 1;
      else counts.infos += 1;
    }
  }
  return counts;
}

export function flattenDiagnostics(
  byPath: Record<string, LspDiagnostic[]>,
  projectPath?: string | null,
): DiagnosticEntry[] {
  const out: DiagnosticEntry[] = [];
  for (const [path, diagnostics] of Object.entries(byPath)) {
    const shortPath = projectPath && path.toLowerCase().startsWith(projectPath.toLowerCase())
      ? path.slice(projectPath.length).replace(/^[\\/]/, '')
      : path;
    for (const diagnostic of diagnostics) {
      out.push({ path, shortPath, diagnostic });
    }
  }
  return out.sort((a, b) =>
    (a.diagnostic.severity ?? 3) - (b.diagnostic.severity ?? 3)
    || a.shortPath.localeCompare(b.shortPath)
    || (a.diagnostic.range?.start?.line ?? 0) - (b.diagnostic.range?.start?.line ?? 0));
}
