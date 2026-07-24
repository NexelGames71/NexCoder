import type { LspDiagnostic } from '../store/useDiagnosticsStore';

export interface DiagnosticPromptInput {
  path: string;
  shortPath?: string;
  diagnostic: LspDiagnostic;
  lineText?: string;
}

export interface ComposerPromptDetail {
  content: string;
  mode?: string;
  send?: boolean;
}

export function diagnosticSeverityLabel(severity?: number): string {
  if (severity === 1) return 'Error';
  if (severity === 2) return 'Warning';
  if (severity === 4) return 'Hint';
  return 'Info';
}

export function buildDiagnosticFixPrompt({
  path,
  shortPath,
  diagnostic,
  lineText,
}: DiagnosticPromptInput): string {
  const line = (diagnostic.range?.start?.line ?? 0) + 1;
  const column = (diagnostic.range?.start?.character ?? 0) + 1;
  const target = shortPath || path;
  const parts = [
    'Fix this IDE problem in the project.',
    '',
    `File: ${target}`,
    `Line: ${line}`,
    `Column: ${column}`,
    `Severity: ${diagnosticSeverityLabel(diagnostic.severity)}`,
  ];
  if (diagnostic.source) parts.push(`Source: ${diagnostic.source}`);
  if (diagnostic.code !== undefined && diagnostic.code !== null) {
    parts.push(`Code: ${diagnostic.code}`);
  }
  parts.push(`Message: ${diagnostic.message}`);
  if (lineText?.trim()) {
    parts.push('', 'Code line:', '```', lineText, '```');
  }
  parts.push(
    '',
    'Open the file, make the smallest correct code change, and verify the fix if possible.',
  );
  return parts.join('\n');
}

export function loadComposerPrompt(detail: ComposerPromptDetail): void {
  window.dispatchEvent(new CustomEvent('nexcoder:load-chat-composer', { detail }));
}
