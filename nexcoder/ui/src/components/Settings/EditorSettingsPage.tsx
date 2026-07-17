import React from 'react';
import SettingsPage from './SettingsPage';

/** Legacy entry point (Ctrl+,): opens unified settings on Editor. */
export default function EditorSettingsPage({ onClose }: { onClose: () => void }) {
  return <SettingsPage onClose={onClose} initialTab="editor" />;
}
