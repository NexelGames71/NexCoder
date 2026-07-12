import React from 'react';
import { AlertCircle, AlertTriangle } from 'lucide-react';

export default function ProblemsTab() {
  return (
    <div className="overflow-auto h-full" style={{ padding: 'var(--space-3)' }}>
      <div className="problems-list">
        <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)', padding: 'var(--space-4)' }}>
          No problems found in workspace
        </p>
      </div>
    </div>
  );
}
