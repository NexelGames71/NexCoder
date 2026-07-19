import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
// Must run before any editor mounts: points the Monaco loader at the
// bundled copy (no CDN) and registers workers + custom themes.
import './services/monacoSetup';
import { initBridge } from './services/bridge';

const root = ReactDOM.createRoot(document.getElementById('root')!);

// Initialize QWebChannel before rendering so signal listeners can connect reliably.
initBridge()
  .then(() => {
    console.log('[NexCoder] Bridge initialized');
  })
  .catch((err) => {
    console.warn('[NexCoder] Bridge init failed (dev mode?):', err);
  })
  .finally(() => {
    root.render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    );
  });
