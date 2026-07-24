/** Dev-only harness: mounts MeshPanel + MeshView with a store driven by
 *  a simulated mesh run. Loaded manually via `import('/src/dev-mesh.ts')`. */
import React from 'react';
import ReactDOM from 'react-dom/client';
import MeshPanel from './components/Sidebar/MeshPanel';
import MeshView from './components/Mesh/MeshView';
import { useMeshStore } from './store/useMeshStore';

const feed = (type: string, payload: Record<string, unknown>) =>
  useMeshStore.getState().handleEvent(JSON.stringify({ type, payload }));

useMeshStore.getState().start('Add an Appwrite auth system');
feed('mesh_started', { mesh_id: 'mesh_dev1', goal: 'Add an Appwrite auth system' });
feed('mesh_plan', {
  mesh_id: 'mesh_dev1', fallback_plan: false,
  units: [
    { id: 'work_1', title: 'Explore auth surface', role: 'explorer',
      description: 'Map existing auth-related files.', dependencies: [],
      completion_criteria: [] },
    { id: 'work_2', title: 'Implement session service', role: 'implementation',
      description: 'Create the Appwrite session service and wire the login UI.',
      dependencies: ['work_1'],
      completion_criteria: ['Session service exists', 'Login flow works'] },
    { id: 'work_3', title: 'Review changes', role: 'review',
      description: 'Review the combined change set.', dependencies: ['work_2'],
      completion_criteria: [] },
  ],
});
feed('agent_started', { mesh_id: 'mesh_dev1', agent_id: 'work_1', role: 'explorer', display_name: 'Explorer', title: 'Explore auth surface' });
feed('agent_activity', { mesh_id: 'mesh_dev1', agent_id: 'work_1', inner: { type: 'tool_started', payload: { tool: 'read_file', args: { path: 'app/auth.py' } } } });
feed('agent_completed', { mesh_id: 'mesh_dev1', agent_id: 'work_1', status: 'completed', turns: 4, files: [], summary: 'Auth lives in app/auth.py; login UI in src/Login.tsx.' });
feed('agent_started', { mesh_id: 'mesh_dev1', agent_id: 'work_2', role: 'implementation', display_name: 'Implementer', title: 'Implement session service' });
feed('agent_activity', { mesh_id: 'mesh_dev1', agent_id: 'work_2', inner: { type: 'edit_applied', payload: { path: 'app/session.py', added: 42, removed: 0 } } });
feed('agent_completed', { mesh_id: 'mesh_dev1', agent_id: 'work_2', status: 'completed', turns: 12, files: ['app/session.py', 'src/Login.tsx'], summary: 'Session service added; login UI wired.' });
feed('mesh_conflict', { mesh_id: 'mesh_dev1', file: 'src/Login.tsx', units: ['work_2', 'work_3'] });
feed('agent_started', { mesh_id: 'mesh_dev1', agent_id: 'work_3', role: 'review', display_name: 'Reviewer', title: 'Review changes' });

const panelRoot = document.createElement('div');
panelRoot.id = 'mesh-dev-panel';
panelRoot.style.cssText = 'position:fixed;top:0;left:0;bottom:0;width:320px;z-index:9999;background:var(--bg-panel,#16161e);border-right:2px solid #6c5ce7;overflow:auto;';
document.body.appendChild(panelRoot);
ReactDOM.createRoot(panelRoot).render(React.createElement(MeshPanel));

const viewRoot = document.createElement('div');
viewRoot.id = 'mesh-dev-view';
document.body.appendChild(viewRoot);
ReactDOM.createRoot(viewRoot).render(
  React.createElement(MeshView, { onClose: () => {} }),
);
