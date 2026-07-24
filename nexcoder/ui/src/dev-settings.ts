/** Dev-only harness: mounts the unified SettingsPage standalone so it
 *  can be inspected in a plain browser (no Qt bridge). Not imported by
 *  the app; loaded manually via `import('/src/dev-settings.ts')`. */
import React from 'react';
import ReactDOM from 'react-dom/client';
import SettingsPage from './components/Settings/SettingsPage';

const el = document.createElement('div');
el.id = 'settings-preview-root';
document.body.appendChild(el);
ReactDOM.createRoot(el).render(
  React.createElement(SettingsPage, { onClose: () => {} }),
);
