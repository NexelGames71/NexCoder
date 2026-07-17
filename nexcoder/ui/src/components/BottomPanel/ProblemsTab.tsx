import React, { useMemo } from 'react';
import { AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { useDiagnosticsStore, LspDiagnostic } from '../../store/useDiagnosticsStore';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useProjectStore } from '../../store/useProjectStore';
import { readFile } from '../../services/bridge';
import { getLanguageFromExtension } from '../../utils/languageMap';

function severityIcon(severity?: number) {
  if (severity === 1) return <AlertCircle size={13} style={{ color: 'var(--accent-red, #ef4444)', flexShrink: 0 }} />;
  if (severity === 2) return <AlertTriangle size={13} style={{ color: 'var(--accent-yellow, #facc15)', flexShrink: 0 }} />;
  return <Info size={13} style={{ color: 'var(--accent-blue, #60a5fa)', flexShrink: 0 }} />;
}

export default function ProblemsTab() {
  const byPath = useDiagnosticsStore((s) => s.byPath);
  const { projectPath } = useProjectStore();

  const entries = useMemo(() => {
    const out: { path: string; shortPath: string; diagnostic: LspDiagnostic }[] = [];
    for (const [path, diagnostics] of Object.entries(byPath)) {
      const shortPath = projectPath && path.toLowerCase().startsWith(projectPath.toLowerCase())
        ? path.slice(projectPath.length).replace(/^[\\/]/, '')
        : path;
      for (const diagnostic of diagnostics) {
        out.push({ path, shortPath, diagnostic });
      }
    }
    // Errors first, then warnings, then by file.
    return out.sort((a, b) =>
      (a.diagnostic.severity ?? 3) - (b.diagnostic.severity ?? 3)
      || a.shortPath.localeCompare(b.shortPath));
  }, [byPath, projectPath]);

  const handleClick = async (path: string, diagnostic: LspDiagnostic) => {
    const state = useEditorStateStore.getState();
    const line = (diagnostic.range?.start?.line ?? 0) + 1;
    const column = (diagnostic.range?.start?.character ?? 0) + 1;
    state.setPendingReveal({ path, line, column });
    const alreadyOpen = state.editorGroups.some(
      (g) => g.openFiles.some((f) => f.path === path));
    if (!alreadyOpen) {
      const res: any = await readFile(path);
      if (res?.success) {
        const name = path.split(/[\\/]/).pop() || path;
        const extension = name.includes('.') ? name.split('.').pop() || '' : '';
        state.openFile({
          path, name, content: res.content,
          language: getLanguageFromExtension(extension), isDirty: false,
        });
      }
    } else {
      state.setActiveFile(path);
    }
  };

  if (entries.length === 0) {
    return (
      <div className="overflow-auto h-full" style={{ padding: 'var(--space-3)' }}>
        <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)', padding: 'var(--space-4)' }}>
          No problems detected in open files
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-auto h-full" style={{ padding: 'var(--space-2)' }}>
      <div className="problems-list">
        {entries.map(({ path, shortPath, diagnostic }, index) => (
          <div
            key={`${path}:${index}`}
            onClick={() => handleClick(path, diagnostic)}
            style={{
              display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
              padding: '3px var(--space-2)', cursor: 'pointer',
              borderRadius: 'var(--radius-sm)', fontSize: 'var(--font-size-xs)',
            }}
            className="problems-row"
            title={diagnostic.message}
          >
            {severityIcon(diagnostic.severity)}
            <span className="truncate" style={{ color: 'var(--text-primary)' }}>
              {diagnostic.message}
            </span>
            <span style={{ color: 'var(--text-tertiary)', marginLeft: 'auto', whiteSpace: 'nowrap' }}>
              {shortPath}:{(diagnostic.range?.start?.line ?? 0) + 1}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
