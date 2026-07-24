/**
 * Monaco ↔ LSP glue: registers language providers once and maps
 * editor models to workspace file paths.
 *
 * Models are registered per editor mount (NexCoder keys one Monaco
 * instance per open file), so providers resolve the file path through
 * a WeakMap rather than model URIs.
 */
import type { Monaco } from '@monaco-editor/react';
import { readFile } from './bridge';
import { lspRequest } from './lsp';
import { useEditorStateStore } from '../store/useEditorStateStore';
import { useEditorSettingsStore } from '../store/useEditorSettingsStore';
import { useProjectStore } from '../store/useProjectStore';
import { getLanguageFromExtension } from '../utils/languageMap';
import {
  buildDiagnosticFixPrompt,
  loadComposerPrompt,
} from '../utils/diagnosticPrompt';
import type { LspDiagnostic } from '../store/useDiagnosticsStore';

const modelPaths = new WeakMap<object, string>();
let providersRegistered = false;
let diagnosticCommandsRegistered = false;
const FIX_DIAGNOSTIC_COMMAND = 'nexcoder.fixDiagnosticWithAgent';
const SEND_DIAGNOSTIC_COMMAND = 'nexcoder.sendDiagnosticToChat';

const PROVIDER_LANGUAGES = [
  'python', 'typescript', 'javascript', 'html', 'css', 'json',
];

export function registerModel(model: object, path: string): void {
  modelPaths.set(model, path);
}

function pathOf(model: object): string | null {
  return modelPaths.get(model) ?? null;
}

/** LSP CompletionItemKind → Monaco CompletionItemKind. */
function completionKind(monaco: Monaco, lspKind: number): number {
  const k = monaco.languages.CompletionItemKind;
  const table: Record<number, number> = {
    1: k.Text, 2: k.Method, 3: k.Function, 4: k.Constructor, 5: k.Field,
    6: k.Variable, 7: k.Class, 8: k.Interface, 9: k.Module, 10: k.Property,
    11: k.Unit, 12: k.Value, 13: k.Enum, 14: k.Keyword, 15: k.Snippet,
    16: k.Color, 17: k.File, 18: k.Reference, 19: k.Folder, 20: k.EnumMember,
    21: k.Constant, 22: k.Struct, 23: k.Event, 24: k.Operator,
    25: k.TypeParameter,
  };
  return table[lspKind] ?? k.Text;
}

async function openFileAt(path: string, line: number, column: number): Promise<void> {
  const state = useEditorStateStore.getState();
  state.setPendingReveal({ path, line, column });
  const res: any = await readFile(path);
  if (res?.success) {
    const name = path.split(/[\\/]/).pop() || path;
    const extension = name.includes('.') ? name.split('.').pop() || '' : '';
    state.openFile({
      path,
      name,
      content: res.content,
      language: getLanguageFromExtension(extension),
      isDirty: false,
    });
  }
}

function shortPathOf(path: string): string {
  const projectPath = useProjectStore.getState().projectPath;
  if (projectPath && path.toLowerCase().startsWith(projectPath.toLowerCase())) {
    return path.slice(projectPath.length).replace(/^[\\/]/, '');
  }
  return path;
}

function markerSeverityToDiagnostic(monaco: Monaco, severity: number): number {
  if (severity === monaco.MarkerSeverity.Error) return 1;
  if (severity === monaco.MarkerSeverity.Warning) return 2;
  if (severity === monaco.MarkerSeverity.Hint) return 4;
  return 3;
}

function markerToDiagnostic(monaco: Monaco, marker: any): LspDiagnostic {
  const markerCode = typeof marker.code === 'string' || typeof marker.code === 'number'
    ? marker.code
    : marker.code?.value !== undefined
      ? String(marker.code.value)
      : undefined;
  return {
    range: {
      start: {
        line: Math.max(0, (marker.startLineNumber || 1) - 1),
        character: Math.max(0, (marker.startColumn || 1) - 1),
      },
      end: {
        line: Math.max(0, (marker.endLineNumber || marker.startLineNumber || 1) - 1),
        character: Math.max(0, (marker.endColumn || marker.startColumn || 1) - 1),
      },
    },
    message: String(marker.message || ''),
    severity: markerSeverityToDiagnostic(monaco, marker.severity),
    source: marker.source,
    code: markerCode,
  };
}

function sendDiagnosticPrompt(monaco: Monaco, payload: any, send: boolean): void {
  const path = String(payload?.path || '');
  const marker = payload?.marker;
  if (!path || !marker) return;
  const diagnostic = markerToDiagnostic(monaco, marker);
  const prompt = buildDiagnosticFixPrompt({
    path,
    shortPath: shortPathOf(path),
    diagnostic,
    lineText: String(payload?.lineText || ''),
  });
  window.nexcoder?.showAIPanel?.();
  loadComposerPrompt({ content: prompt, mode: 'agent', send });
}

function registerDiagnosticCommands(monaco: Monaco): void {
  if (diagnosticCommandsRegistered) return;
  diagnosticCommandsRegistered = true;
  monaco.editor.registerCommand(FIX_DIAGNOSTIC_COMMAND, (_accessor: any, payload: any) => {
    sendDiagnosticPrompt(monaco, payload, true);
  });
  monaco.editor.registerCommand(SEND_DIAGNOSTIC_COMMAND, (_accessor: any, payload: any) => {
    sendDiagnosticPrompt(monaco, payload, false);
  });
}

export function registerLspProviders(monaco: Monaco): void {
  if (providersRegistered) return;
  providersRegistered = true;
  registerDiagnosticCommands(monaco);

  for (const language of PROVIDER_LANGUAGES) {
    monaco.languages.registerCompletionItemProvider(language, {
      triggerCharacters: ['.', '"', "'", '/', '<'],
      provideCompletionItems: async (model: any, position: any) => {
        const prefs = useEditorSettingsStore.getState().settings;
        if (!prefs.lspEnabled || !prefs.lspAutocomplete) {
          return { suggestions: [] };
        }
        const path = pathOf(model);
        if (!path) return { suggestions: [] };
        try {
          const items = await lspRequest(
            'completion', path,
            position.lineNumber - 1, position.column - 1);
          const word = model.getWordUntilPosition(position);
          const range = {
            startLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endLineNumber: position.lineNumber,
            endColumn: word.endColumn,
          };
          return {
            suggestions: (items || []).map((item: any) => ({
              label: item.label,
              kind: completionKind(monaco, item.kind),
              detail: item.detail || undefined,
              insertText: item.insertText || item.label,
              sortText: item.sortText || undefined,
              range,
            })),
          };
        } catch {
          return { suggestions: [] };
        }
      },
    });

    monaco.languages.registerHoverProvider(language, {
      provideHover: async (model: any, position: any) => {
        const path = pathOf(model);
        if (!path) return null;
        const markers = monaco.editor.getModelMarkers({ resource: model.uri })
          .filter((marker: any) =>
            marker.owner === 'nexlsp'
            && marker.startLineNumber <= position.lineNumber
            && marker.endLineNumber >= position.lineNumber
            && marker.startColumn <= position.column
            && marker.endColumn >= position.column);
        if (markers.length > 0) {
          const marker = markers[0];
          const payload = encodeURIComponent(JSON.stringify([{
            path,
            marker,
            lineText: model.getLineContent(marker.startLineNumber),
          }]));
          return {
            contents: [{
              value: [
                `**${marker.message}**`,
                '',
                `[Send to Chat](command:${SEND_DIAGNOSTIC_COMMAND}?${payload})`,
                `[Fix with NexCoder Agent](command:${FIX_DIAGNOSTIC_COMMAND}?${payload})`,
              ].join('\n\n'),
              isTrusted: true,
            }],
          };
        }
        try {
          const contents = await lspRequest(
            'hover', path, position.lineNumber - 1, position.column - 1);
          if (!contents) return null;
          return { contents: [{ value: String(contents) }] };
        } catch {
          return null;
        }
      },
    });

    monaco.languages.registerCodeActionProvider(language, {
      provideCodeActions: (model: any, _range: any, context: any) => {
        const path = pathOf(model);
        if (!path) return { actions: [], dispose: () => undefined };
        const markers = (context.markers || []).filter((marker: any) =>
          !marker.owner || marker.owner === 'nexlsp');
        const actions = markers.flatMap((marker: any) => {
          const payload = {
            path,
            marker,
            lineText: model.getLineContent(marker.startLineNumber),
          };
          return [
            {
              title: 'Fix with NexCoder Agent',
              diagnostics: [marker],
              kind: 'quickfix',
              isPreferred: true,
              command: {
                id: FIX_DIAGNOSTIC_COMMAND,
                title: 'Fix with NexCoder Agent',
                arguments: [payload],
              },
            },
            {
              title: 'Send Problem to Chat',
              diagnostics: [marker],
              kind: 'quickfix',
              command: {
                id: SEND_DIAGNOSTIC_COMMAND,
                title: 'Send Problem to Chat',
                arguments: [payload],
              },
            },
          ];
        });
        return { actions, dispose: () => undefined };
      },
    });

    monaco.languages.registerDefinitionProvider(language, {
      provideDefinition: async (model: any, position: any) => {
        const path = pathOf(model);
        if (!path) return null;
        try {
          const locations = await lspRequest(
            'definition', path,
            position.lineNumber - 1, position.column - 1);
          if (!locations || locations.length === 0) return null;
          const target = locations[0];
          const startLine = (target.range?.start?.line ?? 0) + 1;
          const startCol = (target.range?.start?.character ?? 0) + 1;
          if (target.path === path) {
            return [{
              uri: model.uri,
              range: new monaco.Range(
                startLine, startCol,
                (target.range?.end?.line ?? 0) + 1,
                (target.range?.end?.character ?? 0) + 1),
            }];
          }
          // Cross-file: open the target ourselves and reveal.
          void openFileAt(target.path, startLine, startCol);
          return null;
        } catch {
          return null;
        }
      },
    });

    monaco.languages.registerReferenceProvider(language, {
      provideReferences: async (model: any, position: any) => {
        const path = pathOf(model);
        if (!path) return [];
        try {
          const locations = await lspRequest(
            'references', path,
            position.lineNumber - 1, position.column - 1);
          // Peek preview needs a live model, so only same-file
          // references render in the widget for now.
          return (locations || [])
            .filter((loc: any) => loc.path === path)
            .map((loc: any) => ({
              uri: model.uri,
              range: new monaco.Range(
                (loc.range?.start?.line ?? 0) + 1,
                (loc.range?.start?.character ?? 0) + 1,
                (loc.range?.end?.line ?? 0) + 1,
                (loc.range?.end?.character ?? 0) + 1),
            }));
        } catch {
          return [];
        }
      },
    });

    monaco.languages.registerRenameProvider(language, {
      provideRenameEdits: async (model: any, position: any, newName: string) => {
        const path = pathOf(model);
        if (!path) return { edits: [] };
        try {
          // Python applies the rename atomically on disk; the UI then
          // reloads the affected open files.
          const result = await lspRequest(
            'rename', path,
            position.lineNumber - 1, position.column - 1, newName);
          const changed: string[] = result?.changed_files || [];
          const state = useEditorStateStore.getState();
          for (const group of state.editorGroups) {
            for (const open of group.openFiles) {
              if (changed.some((c) => c.toLowerCase() === open.path.toLowerCase())) {
                const res: any = await readFile(open.path);
                if (res?.success) {
                  state.replaceFileContent({ ...open, content: res.content });
                }
              }
            }
          }
          return { edits: [] };
        } catch {
          return { edits: [] };
        }
      },
    });
  }
}
