import React, { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { searchFiles, readFile } from '../../services/bridge';
import { useProjectStore } from '../../store/useProjectStore';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { getLanguageFromExtension } from '../../utils/languageMap';

export default function SearchPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const { projectPath } = useProjectStore();
  const { openFile } = useEditorStateStore();

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || !projectPath) return;

    setIsSearching(true);
    try {
      const res = await searchFiles(query, projectPath);
      if (res && res.success && res.results) {
        // Group by file path
        const groupedMap = res.results.reduce((acc: any, curr: any) => {
          if (!acc[curr.file]) acc[curr.file] = [];
          acc[curr.file].push(curr);
          return acc;
        }, {});

        const groupedList = Object.keys(groupedMap).map((file) => ({
          file,
          name: file.split('/').pop() || file,
          matches: groupedMap[file],
        }));

        setResults(groupedList);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsSearching(false);
    }
  };

  const handleMatchClick = async (file: string, line: number) => {
    try {
      const res = await readFile(file);
      if (res && res.success) {
        const ext = file.split('.').pop() || '';
        openFile({
          path: file,
          name: file.split('/').pop() || file,
          content: res.content,
          language: getLanguageFromExtension(`.${ext}`),
          isDirty: false,
          cursorLine: line,
        });
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="sidebar-panel">
      <div className="sidebar-header">
        <span>Search</span>
      </div>

      <form onSubmit={handleSearch} style={{ padding: 'var(--space-3)', display: 'flex', gap: 'var(--space-2)' }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <input
            className="input"
            type="text"
            placeholder="Search project..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ paddingLeft: 'var(--space-6)' }}
          />
          <Search
            size={12}
            style={{
              position: 'absolute',
              left: '8px',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--text-tertiary)',
            }}
          />
        </div>
        <button className="btn btn-primary" type="submit" disabled={isSearching}>
          {isSearching ? <Loader2 size={12} className="spin" /> : 'Find'}
        </button>
      </form>

      <div className="search-results-list">
        {results.length === 0 && !isSearching && (
          <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', padding: 'var(--space-4)', fontSize: 'var(--font-size-xs)' }}>
            No results
          </p>
        )}

        {results.map((group) => (
          <div key={group.file} style={{ marginBottom: 'var(--space-3)' }}>
            <div className="search-result-file">
              <span>{group.name}</span>
              <span style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}>{group.file}</span>
            </div>
            {group.matches.map((match: any, idx: number) => (
              <div
                key={idx}
                className="search-result-match"
                onClick={() => handleMatchClick(group.file, match.line)}
              >
                <span style={{ color: 'var(--accent-purple)', marginRight: 'var(--space-2)' }}>L{match.line}:</span>
                {match.content}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
