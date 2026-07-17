import React from 'react';
import SettingsPage from './SettingsPage';

/** Legacy entry point (Ctrl+Shift+,): opens unified settings on AI Agent. */
export default function AgentSettingsPage({ onClose }: { onClose: () => void }) {
  return <SettingsPage onClose={onClose} initialTab="agent" />;
}
