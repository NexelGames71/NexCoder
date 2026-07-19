import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { useProjectStore } from '../../store/useProjectStore';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { readFile } from '../../services/bridge';
import { getFileIcon, getFileColor } from '../../utils/fileIcons';
import { getLanguageFromExtension } from '../../utils/languageMap';
import type { FileNode } from '../../types';
import './QuickSearch.css';

interface FlatFile { name: string; path: string; extension: string; }

function flatten(nodes: FileNode[], out: FlatFile[] = []): FlatFile[] {
  for (const node of nodes) {
    if (node.type === 'directory') {
      if (node.children) flatten(node.children, out);
    } else {
      out.push({ name: node.name, path: node.path, extension: node.extension || '' });
    }
  }
  return out;
}

/** VS Code-style command-center: quick-open project files by name. */
export default function QuickSearch() {
  const { fileTree, projectName } = useProjectStore();
  const openFile = useEditorStateStore((s) => s.openFile);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const allFiles = useMemo(() => flatten(fileTree), [fileTree]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const scored = allFiles
      .map((f) => {
        const name = f.name.toLowerCase();
        const path = f.path.toLowerCase();
        let score = -1;
        if (name === q) score = 100;
        else if (name.startsWith(q)) score = 80;
        else if (name.includes(q)) score = 60;
        else if (path.includes(q)) score = 30;
        return { f, score };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score || a.f.name.length - b.f.name.length)
      .slice(0, 12)
      .map((x) => x.f);
    return scored;
  }, [query, allFiles]);

  useEffect(() => { setActive(0); }, [query]);

  // Ctrl+P focuses the bar (VS Code quick-open).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'p' || e.key === 'P') && !e.shiftKey) {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Close on outside click.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  const openResult = async (f: FlatFile) => {
    try {
      const res: any = await readFile(f.path);
      if (res?.success) {
        openFile({
          path: f.path, name: f.name, content: res.content,
          language: getLanguageFromExtension(f.extension), isDirty: false,
        });
      }
    } catch { /* ignore */ }
    setOpen(false);
    setQuery('');
    inputRef.current?.blur();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter' && results[active]) { e.preventDefault(); openResult(results[active]); }
    else if (e.key === 'Escape') { setOpen(false); inputRef.current?.blur(); }
  };

  const placeholder = projectName ? `Search ${projectName}` : 'Search files';

  return (
    <div className="quick-search" ref={wrapRef}>
      <div className="quick-search-bar">
        <Search size={12} className="quick-search-icon" />
        <input
          ref={inputRef}
          className="quick-search-input"
          value={query}
          placeholder={placeholder}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && query.trim() && (
        <div className="quick-search-results">
          {results.length === 0 ? (
            <div className="quick-search-empty">No matching files</div>
          ) : (
            results.map((f, i) => {
              const Icon = getFileIcon(f.extension, false, false, f.name);
              return (
                <div
                  key={f.path}
                  className={`quick-search-item ${i === active ? 'active' : ''}`}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => { e.preventDefault(); openResult(f); }}
                >
                  <Icon size={13} style={{ color: getFileColor(f.extension, f.name), flexShrink: 0 }} />
                  <span className="quick-search-name">{f.name}</span>
                  <span className="quick-search-path">{f.path}</span>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
