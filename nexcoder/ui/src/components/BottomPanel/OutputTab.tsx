import React from 'react';

export default function OutputTab() {
  return (
    <div className="overflow-auto h-full" style={{ padding: 'var(--space-3)', fontFamily: 'var(--font-code)', fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
      <p style={{ color: 'var(--text-tertiary)' }}>No build outputs recorded</p>
    </div>
  );
}
