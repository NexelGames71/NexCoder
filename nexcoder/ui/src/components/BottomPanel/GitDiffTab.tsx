import React, { useEffect, useState } from 'react';
import { gitDiff } from '../../services/bridge';
import { useProjectStore } from '../../store/useProjectStore';

export default function GitDiffTab() {
  const { projectPath } = useProjectStore();
  const [diffText, setDiffText] = useState('');

  useEffect(() => {
    if (projectPath) {
      gitDiff(projectPath).then((res: any) => {
        if (res && res.success && res.diff) {
          setDiffText(res.diff);
        } else {
          setDiffText('');
        }
      });
    }
  }, [projectPath]);

  return (
    <div className="overflow-auto h-full" style={{ padding: 'var(--space-3)', background: 'var(--bg-deep)' }}>
      {diffText ? (
        <pre style={{ margin: 0, fontFamily: 'var(--font-code)', fontSize: 'var(--font-size-xs)', color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
          <code>{diffText}</code>
        </pre>
      ) : (
        <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)', paddingTop: 'var(--space-4)' }}>
          No uncommitted changes to diff
        </p>
      )}
    </div>
  );
}
