/** Dev-only harness: mounts MonacoEditor with a fake file so editor
 *  loading (bundled Monaco, no CDN) and themes can be verified in a
 *  plain browser. Loaded manually via `import('/src/dev-editor.ts')`. */
import React from 'react';
import ReactDOM from 'react-dom/client';
import MonacoEditor from './components/Editor/MonacoEditor';
import { monaco } from './services/monacoSetup';

(window as any).__monaco = monaco;
monaco.editor.onDidCreateEditor((editor) => {
  (window as any).__lastEditor = editor;
});

const el = document.createElement('div');
el.id = 'editor-dev-root';
el.style.cssText =
  'position:fixed;left:0;right:0;bottom:0;height:320px;z-index:9999;'
  + 'border-top:2px solid #6c5ce7;background:#0e0e14;';
document.body.appendChild(el);
ReactDOM.createRoot(el).render(
  React.createElement(MonacoEditor, {
    file: {
      path: 'C:/demo/hello.py',
      name: 'hello.py',
      content: 'def add(a, b):\n    """Add two numbers."""\n    return a + b\n',
      language: 'python',
      isDirty: false,
    },
  }),
);
