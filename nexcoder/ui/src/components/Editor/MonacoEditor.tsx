import React, { useEffect, useRef, useState } from 'react';
import Editor, { Monaco } from '@monaco-editor/react';
import { OpenFile } from '../../types';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import { useDiagnosticsStore } from '../../store/useDiagnosticsStore';
import { writeFile } from '../../services/bridge';
import { notifyChange, notifyOpen } from '../../services/lsp';
import { registerLspProviders, registerModel } from '../../services/monacoLsp';
import { toMonacoTheme } from '../../services/monacoSetup';
import { useProjectStore } from '../../store/useProjectStore';
import { buildDiagnosticFixPrompt, loadComposerPrompt } from '../../utils/diagnosticPrompt';

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

  const containerRef = useRef<HTMLDivElement>(null);

  const sendMarkerToComposer = (monaco: Monaco, editor: any, send: boolean) => {
    const model = editor.getModel();
    const position = editor.getPosition();
    if (!model || !position) return;
    const markers = monaco.editor.getModelMarkers({ resource: model.uri })
      .filter((marker: any) =>
        marker.owner === 'nexlsp'
        && marker.startLineNumber <= position.lineNumber
        && marker.endLineNumber >= position.lineNumber
        && (
          (marker.startColumn <= position.column && marker.endColumn >= position.column)
          || marker.startLineNumber === position.lineNumber
        ));
    const marker = markers[0];
    if (!marker) return;
    const projectPath = useProjectStore.getState().projectPath;
    const path = fileRef.current.path;
    const shortPath = projectPath && path.toLowerCase().startsWith(projectPath.toLowerCase())
      ? path.slice(projectPath.length).replace(/^[\\/]/, '')
      : path;
    const markerSeverityMap: Record<number, number> = {
      [monaco.MarkerSeverity.Error]: 1,
      [monaco.MarkerSeverity.Warning]: 2,
      [monaco.MarkerSeverity.Info]: 3,
      [monaco.MarkerSeverity.Hint]: 4,
    };
    const markerCode = typeof marker.code === 'string' || typeof marker.code === 'number'
      ? marker.code
      : marker.code?.value !== undefined
        ? String(marker.code.value)
        : undefined;
    const prompt = buildDiagnosticFixPrompt({
      path,
      shortPath,
      diagnostic: {
        range: {
          start: {
            line: Math.max(0, marker.startLineNumber - 1),
            character: Math.max(0, marker.startColumn - 1),
          },
          end: {
            line: Math.max(0, marker.endLineNumber - 1),
            character: Math.max(0, marker.endColumn - 1),
          },
        },
        message: marker.message,
        severity: markerSeverityMap[marker.severity] ?? 3,
        source: marker.source,
        code: markerCode,
      },
      lineText: model.getLineContent(marker.startLineNumber),
    });
    window.nexcoder?.showAIPanel?.();
    loadComposerPrompt({ content: prompt, mode: 'agent', send });
  };

  const handleEditorDidMount = (editor: any, monaco: Monaco) => {
    editorRef.current = editor;
    setMonacoApi(monaco);

    // Robust sizing: Monaco's own container measurement is unreliable
    // right after creation (observed persistent 5x5 editors inside a
    // healthy 1280px wrapper, immune to argument-less layout() retries).
    // Bypass its measuring entirely: feed explicit wrapper dimensions,
    // now and on every container resize.
    let disposed = false;
    const layoutToWrapper = () => {
      const wrapper = containerRef.current;
      if (disposed || !wrapper) return;
      const width = wrapper.clientWidth;
      const height = wrapper.clientHeight;
      if (width > 0 && height > 0) editor.layout({ width, height });
    };
    requestAnimationFrame(layoutToWrapper);
    setTimeout(layoutToWrapper, 150);
    const wrapper = containerRef.current;
    if (wrapper && typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(layoutToWrapper);
      observer.observe(wrapper);
      editor.onDidDispose(() => { disposed = true; observer.disconnect(); });
    } else {
      editor.onDidDispose(() => { disposed = true; });
    }

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

    // Themes are registered once in monacoSetup; apply the mapped id.
    monaco.editor.setTheme(toMonacoTheme(settings.theme));

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

    editor.addAction({
      id: 'send-diagnostic-to-nexcoder-chat',
      label: 'Send Problem to Chat',
      contextMenuGroupId: 'navigation',
      contextMenuOrder: 0.9,
      run: (ed: any) => sendMarkerToComposer(monaco, ed, false),
    });

    editor.addAction({
      id: 'fix-diagnostic-with-nexcoder-agent',
      label: 'Fix Problem with NexCoder Agent',
      contextMenuGroupId: 'navigation',
      contextMenuOrder: 1,
      run: (ed: any) => sendMarkerToComposer(monaco, ed, true),
    });
  };

  // Auto save: write ~1s after typing stops (when enabled).
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
  }, []);

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      updateFileContent(file.path, value);
      notifyChange(file.path, file.language, value);
      if (settings.autoSave) {
        if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
        const path = fileRef.current.path;
        autoSaveTimer.current = setTimeout(async () => {
          try {
            const res: any = await writeFile(path, value);
            if (res?.success) setFileDirty(path, false);
          } catch { /* keep the dirty marker on failure */ }
        }, 1000);
      }
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
    const visible = settings.lspEnabled && settings.lspDiagnostics
      ? diagnostics : [];
    monaco.editor.setModelMarkers(model, 'nexlsp', visible.map((d) => ({
      startLineNumber: (d.range?.start?.line ?? 0) + 1,
      startColumn: (d.range?.start?.character ?? 0) + 1,
      endLineNumber: (d.range?.end?.line ?? 0) + 1,
      endColumn: (d.range?.end?.character ?? 0) + 1,
      message: d.message,
      severity: severityMap[d.severity ?? 3] ?? monaco.MarkerSeverity.Info,
      source: d.source || 'lsp',
    })));
  }, [diagnostics, monacoApi, file.path,
      settings.lspEnabled, settings.lspDiagnostics]);

  // Handle theme changes
  useEffect(() => {
    if (monacoApi && editorRef.current) {
      monacoApi.editor.setTheme(toMonacoTheme(settings.theme));
    }
  }, [settings.theme, monacoApi]);

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
      <Editor
        height="100%"
        language={file.language}
        value={file.content}
        theme={toMonacoTheme(settings.theme)}
        onChange={handleEditorChange}
        onMount={handleEditorDidMount}
        options={{
          fontSize: settings.fontSize,
          wordWrap: settings.wordWrap,
          minimap: { enabled: settings.minimap },
          tabSize: settings.tabSize,
          insertSpaces: settings.insertSpaces,
          lineNumbers: settings.lineNumbers,
          bracketPairColorization: { enabled: settings.bracketPairColorization },
          stickyScroll: { enabled: settings.stickyScroll },
          folding: settings.codeFolding,
          matchBrackets: settings.bracketMatching ? 'always' : 'never',
          fontFamily: settings.fontFamily || 'var(--font-code)',
          readOnly: file.kind === 'artifact',
          readOnlyMessage: { value: 'Artifacts are read-only. Use Save in the Artifacts panel to write one into the project.' },
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
