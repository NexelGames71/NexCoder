/**
 * LSP service — request/response correlation over the bridge.
 *
 * The Python side answers asynchronously on the lsp_response signal;
 * every call here returns a promise resolved by id when the signal
 * arrives (or rejected on timeout so Monaco providers never hang).
 */
import {
  lspDidChange,
  lspDidOpen,
  lspRequestRaw,
  onLspDiagnostics,
  onLspResponse,
} from './bridge';
import { useDiagnosticsStore } from '../store/useDiagnosticsStore';

const REQUEST_TIMEOUT_MS = 12000;
const SUPPORTED_LANGUAGES = new Set([
  'python', 'typescript', 'javascript', 'typescriptreact',
  'javascriptreact', 'html', 'css', 'json',
]);

let seq = 0;
let initialized = false;
const pending = new Map<string, {
  resolve: (value: any) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}>();

export function isLspLanguage(language: string | undefined): boolean {
  return !!language && SUPPORTED_LANGUAGES.has(language);
}

export function initLsp(): void {
  if (initialized) return;
  initialized = true;
  onLspResponse((json: string) => {
    try {
      const payload = JSON.parse(json);
      const entry = pending.get(payload.id);
      if (!entry) return;
      pending.delete(payload.id);
      clearTimeout(entry.timer);
      if (payload.error) entry.reject(new Error(payload.error));
      else entry.resolve(payload.result);
    } catch { /* ignore malformed payloads */ }
  });
  onLspDiagnostics((json: string) => {
    try {
      const { path, diagnostics } = JSON.parse(json);
      if (typeof path === 'string') {
        useDiagnosticsStore.getState().setForPath(path, diagnostics || []);
      }
    } catch { /* ignore malformed payloads */ }
  });
}

export function lspRequest(
  kind: 'completion' | 'hover' | 'definition' | 'references' | 'rename',
  path: string, line: number, character: number, extra = '',
): Promise<any> {
  initLsp();
  const id = `lsp_${++seq}`;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`LSP ${kind} timed out`));
    }, REQUEST_TIMEOUT_MS);
    pending.set(id, { resolve, reject, timer });
    lspRequestRaw(id, kind, path, line, character, extra).catch((err) => {
      pending.delete(id);
      clearTimeout(timer);
      reject(err);
    });
  });
}

// ── Document sync (debounced changes) ────────────────────────────────

const changeTimers = new Map<string, ReturnType<typeof setTimeout>>();

export function notifyOpen(path: string, language: string, text: string): void {
  if (!isLspLanguage(language)) return;
  initLsp();
  lspDidOpen(path, language, text).catch(() => {});
}

export function notifyChange(path: string, language: string, text: string): void {
  if (!isLspLanguage(language)) return;
  const existing = changeTimers.get(path);
  if (existing) clearTimeout(existing);
  changeTimers.set(path, setTimeout(() => {
    changeTimers.delete(path);
    lspDidChange(path, text).catch(() => {});
  }, 350));
}
