/** Dev-only harness: mounts the redesigned FirstRunSetup wizard so it can
 *  be inspected without the web-login gate. Loaded via import(). */
import React from 'react';
import ReactDOM from 'react-dom/client';
import FirstRunSetup from './components/Onboarding/FirstRunSetup';

const el = document.createElement('div');
el.id = 'firstrun-dev-root';
document.body.appendChild(el);
ReactDOM.createRoot(el).render(
  React.createElement(FirstRunSetup, {
    userName: 'Jahvii Dark',
    onComplete: (patch: unknown) => console.log('setup complete', patch),
  }),
);
