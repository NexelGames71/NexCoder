import React from 'react';
import EditorSettingsPage from './EditorSettingsPage';
import AgentSettingsPage from './AgentSettingsPage';

export { EditorSettingsPage, AgentSettingsPage };

interface SettingsPageProps {
  onClose: () => void;
  /** When provided, the modal opens directly on the requested tab.
   *  Defaults to editor for any legacy caller that still imports the
   *  original single-page component.
   */
  initialTab?: 'editor' | 'agent';
}

/**
 * Compatibility wrapper around the split settings pages. The unified
 * settings entry point has been retired in favour of two independent
 * modals (Editor + Agent) with their own TopBar buttons and keyboard
 * shortcuts. This component remains so any old import path keeps
 * working, but new code should import the dedicated page directly.
 */
export default function SettingsPage({ onClose, initialTab = 'editor' }: SettingsPageProps) {
  return initialTab === 'agent'
    ? <AgentSettingsPage onClose={onClose} />
    : <EditorSettingsPage onClose={onClose} />;
}
