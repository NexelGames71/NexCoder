/** Monaco bootstrap: bundle-local loading, workers, and themes.
 *
 * Without this module, @monaco-editor/react downloads Monaco from a CDN
 * at runtime — the packaged desktop app then hangs on "Loading…"
 * whenever the network is unavailable. Importing this module (main.tsx)
 * points the loader at the monaco-editor copy bundled by vite and wires
 * its web workers, so the editor always loads instantly and offline.
 */
import * as monaco from 'monaco-editor';
import { loader } from '@monaco-editor/react';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import JsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';
import CssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker';
import HtmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker';
import TsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker';
import type { EditorTheme } from './theme';

(self as any).MonacoEnvironment = {
  getWorker(_workerId: string, label: string) {
    switch (label) {
      case 'json': return new JsonWorker();
      case 'css': case 'scss': case 'less': return new CssWorker();
      case 'html': case 'handlebars': case 'razor': return new HtmlWorker();
      case 'typescript': case 'javascript': return new TsWorker();
      default: return new EditorWorker();
    }
  },
};

loader.config({ monaco });

// ── Themes ───────────────────────────────────────────────────────────
// Registered once at startup so setTheme never references an unknown id.

monaco.editor.defineTheme('nexcoder-theme', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: '', background: '0e0e14' },
    { token: 'comment', foreground: '5a5a72', fontStyle: 'italic' },
    { token: 'keyword', foreground: '6c5ce7', fontStyle: 'bold' },
    { token: 'string', foreground: '00b894' },
    { token: 'number', foreground: 'fdcb6e' },
  ],
  colors: {
    'editor.background': '#0e0e14',
    'editor.foreground': '#e0e0e8',
    'editor.lineHighlightBackground': '#1a1a26',
    'editorCursor.foreground': '#6c5ce7',
    'editorWhitespace.foreground': '#2a2a3a',
    'editorLineNumber.foreground': '#5a5a72',
    'editorLineNumber.activeForeground': '#e0e0e8',
    'editorWidget.background': '#16161e',
    'editorWidget.border': '#2a2a3a',
  },
});

monaco.editor.defineTheme('dark-plus', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '6a9955', fontStyle: 'italic' },
    { token: 'keyword', foreground: '569cd6' },
    { token: 'string', foreground: 'ce9178' },
    { token: 'number', foreground: 'b5cea8' },
    { token: 'type', foreground: '4ec9b0' },
  ],
  colors: {
    'editor.background': '#1e1e1e',
    'editor.foreground': '#d4d4d4',
    'editor.lineHighlightBackground': '#2a2a2a',
  },
});

monaco.editor.defineTheme('github-dark', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '8b949e', fontStyle: 'italic' },
    { token: 'keyword', foreground: 'ff7b72' },
    { token: 'string', foreground: 'a5d6ff' },
    { token: 'number', foreground: '79c0ff' },
    { token: 'type', foreground: 'ffa657' },
  ],
  colors: {
    'editor.background': '#0d1117',
    'editor.foreground': '#c9d1d9',
    'editor.lineHighlightBackground': '#161b22',
  },
});

export { monaco };

/** Map a settings theme id to a registered Monaco theme id. */
export function toMonacoTheme(setting: EditorTheme): string {
  switch (setting) {
    case 'nexcoder': return 'nexcoder-theme';
    case 'light': case 'vs': return 'vs';
    case 'vs-dark': case 'hc-black':
    case 'dark-plus': case 'github-dark':
      return setting;
    default: return 'nexcoder-theme';
  }
}
