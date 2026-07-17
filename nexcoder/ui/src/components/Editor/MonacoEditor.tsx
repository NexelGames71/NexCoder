import React, { useEffect, useRef, useState } from 'react';
import Editor, { Monaco } from '@monaco-editor/react';
import { OpenFile } from '../../types';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import { useDiagnosticsStore } from '../../store/useDiagnosticsStore';
import { writeFile } from '../../services/bridge';
import { notifyChange, notifyOpen } from '../../services/lsp';
import { registerLspProviders, registerModel } from '../../services/monacoLsp';

interface MonacoEditorProps {
  file: OpenFile;
}

export default function MonacoEditor({ file }: MonacoEditorProps) {
  const { updateFileContent, setFileDirty } = useEditorStateStore();
  const { settings } = useEditorSettingsStore();
  const editorRef = useRef<any>(null);
  // The mount handler runs once; the ref keeps listeners pointed at the
  // file currently shown in this editor instance.
  const fileRef = useRef(file);
  fileRef.current = file;

  const [monacoApi, setMonacoApi] = useState<Monaco | null>(null);

  const handleEditorDidMount = (editor: any, monaco: Monaco) => {
    editorRef.current = editor;
    setMonacoApi(monaco);

    // Language intelligence: register the LSP providers (idempotent),
    // map this model to its workspace file, and open the document.
    registerLspProviders(monaco);
    const model = editor.getModel();
    if (model) registerModel(model, file.path);
    notifyOpen(file.path, file.language, file.content);

    // Consume a pending jump (go-to-definition / Problems click).
    const reveal = useEditorStateStore.getState().pendingReveal;
    if (reveal && reveal.path === file.path) {
      useEditorStateStore.getState().setPendingReveal(null);
      editor.setPosition({ lineNumber: reveal.line, column: reveal.column });
      editor.revealPositionInCenter(
        { lineNumber: reveal.line, column: reveal.column });
      editor.focus();
    }

    // Track the selection so AI runs can auto-attach the code the user
    // is looking at ("fix this" without pasting).
    editor.onDidChangeCursorSelection(() => {
      const model = editor.getModel();
      const sel = editor.getSelection();
      if (!model || !sel) return;
      const text = model.getValueInRange(sel);
      useEditorStateStore.getState().setActiveSelection(
        text
          ? {
              path: fileRef.current.path,
              startLine: sel.startLineNumber,
              endLine: sel.endLineNumber,
              text,
            }
          : null,
      );
    });

    // Define custom theme matching NexCoder palette
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

    monaco.editor.setTheme('nexcoder-theme');

    // Add keybinding for Save (Ctrl+S)
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, async () => {
      const value = editor.getValue();
      try {
        if (settings.formatOnSave) {
          await editor.getAction('editor.action.formatDocument')?.run();
        }
        const res: any = await writeFile(file.path, value);
        if (res && res.success) {
          setFileDirty(file.path, false);
        }
      } catch (err) {
        console.error(err);
      }
    });

    // Add Context Menu actions for Ask AI
    editor.addAction({
      id: 'ask-nexcoder-ai',
      label: 'Ask NexCoder AI',
      contextMenuGroupId: 'navigation',
      contextMenuOrder: 1,
      run: (ed: any) => {
        const selection = ed.getModel().getValueInRange(ed.getSelection());
        if (selection) {
          // Trigger Chat with selected text
          // Can expose to global state or chat store
        }
      },
    });
  };

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      updateFileContent(file.path, value);
      notifyChange(file.path, file.language, value);
    }
  };

  // Jump requests for a file that is already mounted (e.g. Problems
  // click on the active file) — the mount-time check misses these.
  const pendingReveal = useEditorStateStore((s) => s.pendingReveal);
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || !pendingReveal || pendingReveal.path !== file.path) return;
    useEditorStateStore.getState().setPendingReveal(null);
    editor.setPosition({ lineNumber: pendingReveal.line, column: pendingReveal.column });
    editor.revealPositionInCenter(
      { lineNumber: pendingReveal.line, column: pendingReveal.column });
    editor.focus();
  }, [pendingReveal, file.path]);

  // Diagnostics → Monaco markers (squiggles) for this file.
  const diagnostics = useDiagnosticsStore(
    (s) => s.byPath[file.path]) || [];
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoApi;
    if (!editor || !monaco) return;
    const model = editor.getModel();
    if (!model) return;
    const severityMap: Record<number, number> = {
      1: monaco.MarkerSeverity.Error,
      2: monaco.MarkerSeverity.Warning,
      3: monaco.MarkerSeverity.Info,
      4: monaco.MarkerSeverity.Hint,
    };
    monaco.editor.setModelMarkers(model, 'nexlsp', diagnostics.map((d) => ({
      startLineNumber: (d.range?.start?.line ?? 0) + 1,
      startColumn: (d.range?.start?.character ?? 0) + 1,
      endLineNumber: (d.range?.end?.line ?? 0) + 1,
      endColumn: (d.range?.end?.character ?? 0) + 1,
      message: d.message,
      severity: severityMap[d.severity ?? 3] ?? monaco.MarkerSeverity.Info,
      source: d.source || 'lsp',
    })));
  }, [diagnostics, monacoApi, file.path]);

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <Editor
        height="100%"
        language={file.language}
        value={file.content}
        onChange={handleEditorChange}
        onMount={handleEditorDidMount}
        options={{
          fontSize: settings.fontSize,
          wordWrap: settings.wordWrap,
          minimap: { enabled: settings.minimap },
          tabSize: settings.tabSize,
          insertSpaces: settings.insertSpaces,
          lineNumbers: settings.lineNumbers,
          fontFamily: 'var(--font-code)',
          automaticLayout: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          padding: { top: 12 },
          lineNumbersMinChars: 3,
        }}
      />
    </div>
  );
}
