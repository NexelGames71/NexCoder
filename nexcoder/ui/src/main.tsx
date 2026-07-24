import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import './index.css';
// Must run before any editor mounts: points the Monaco loader at the
// bundled copy (no CDN) and registers workers + custom themes.
import './services/monacoSetup';
import { initBridge } from './services/bridge';

const root = ReactDOM.createRoot(document.getElementById('root')!);

root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

// Initialize QWebChannel in the background. The app renders its auth shell
// immediately and hydrates native state when the bridge becomes available.
initBridge()
  .then(() => {
    console.log('[NexCoder] Bridge initialized');
  })
  .catch((err) => {
    console.warn('[NexCoder] Bridge init failed (dev mode?):', err);
  });
