import React, { useEffect, useRef } from 'react';
import Editor, { Monaco } from '@monaco-editor/react';
import { OpenFile } from '../../types';
import { useEditorStateStore } from '../../store/useEditorStateStore';
import { useEditorSettingsStore } from '../../store/useEditorSettingsStore';
import { writeFile } from '../../services/bridge';

interface MonacoEditorProps {
  file: OpenFile;
}

export default function MonacoEditor({ file }: MonacoEditorProps) {
  const { updateFileContent, setFileDirty } = useEditorStateStore();
  const { settings } = useEditorSettingsStore();
  const editorRef = useRef<any>(null);

  const handleEditorDidMount = (editor: any, monaco: Monaco) => {
    editorRef.current = editor;

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
    }
  };

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
