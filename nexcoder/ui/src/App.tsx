import React, { useState, useEffect, useCallback } from 'react';
import TopBar from './components/TopBar/TopBar';
import Sidebar from './components/Sidebar/Sidebar';
import EditorArea from './components/Editor/EditorArea';
import BottomPanel from './components/BottomPanel/BottomPanel';
import AIPanel from './components/AIPanel/AIPanel';
import LoginScreen from './components/Auth/LoginScreen';
import EditorSettingsPage from './components/Settings/EditorSettingsPage';
import AgentSettingsPage from './components/Settings/AgentSettingsPage';
import { useProjectStore } from './store/useProjectStore';
import { useAgentStore } from './store/useAgentStore';
import { useEditorStateStore, selectActiveFile, selectOpenFiles } from './store/useEditorStateStore';
import { useResizable } from './hooks/useResizable';
import { 
  onProjectOpened, 
  onFileTreeUpdated,
  writeFile,
  saveFileAs,
  getRecentProjects,
  updateAiSettings,
  updateEngineSettings
} from './services/bridge';
import { getLanguageFromExtension } from './utils/languageMap';

export default function App() {
  const { setProject, setFileTree, projectPath, setRecentProjects } = useProjectStore();
  const editorState = useEditorStateStore();
  const activeFile = selectActiveFile(editorState);
  const openFiles = selectOpenFiles(editorState);
  const { setFileDirty, replaceFileContent } = useEditorStateStore();
  const { settings: agentSettings } = useAgentStore();

  // Sync AI settings to Python backend whenever they change in the UI
  useEffect(() => {
    updateAiSettings(agentSettings.aiEndpoint, agentSettings.aiModel)
      .catch((e) => console.error('Failed to sync AI settings to backend:', e));
  }, [agentSettings.aiEndpoint, agentSettings.aiModel]);

  // Same for engine settings (context window, adapter, full auto)
  useEffect(() => {
    updateEngineSettings({
      context_window: agentSettings.contextWindow,
      adapter: agentSettings.adapter,
      full_auto: agentSettings.fullAuto,
    }).catch((e) => console.error('Failed to sync engine settings:', e));
  }, [agentSettings.contextWindow, agentSettings.adapter, agentSettings.fullAuto]);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [bottomCollapsed, setBottomCollapsed] = useState(false);
  const [aiCollapsed, setAiCollapsed] = useState(false);

  const [showEditorSettings, setShowEditorSettings] = useState(false);
  const [showAgentSettings, setShowAgentSettings] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [user, setUser] = useState<any>(null);

  // Keyboard shortcuts: Ctrl+, opens Editor settings,
  // Ctrl+Shift+, opens Agent settings. Match VS Code conventions so
  // muscle memory carries over.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key !== ',') return;
      e.preventDefault();
      if (e.shiftKey) {
        setShowAgentSettings(true);
        setShowEditorSettings(false);
      } else {
        setShowEditorSettings(true);
        setShowAgentSettings(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // â”€â”€ Resizable panel state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [bottomHeight, setBottomHeight] = useState(240);
  const [aiWidth, setAiWidth] = useState(380);

  const sidebarResize = useResizable({
    direction: 'horizontal',
    initialSize: 260,
    minSize: 180,
    maxSize: 500,
    onResize: setSidebarWidth,
  });

  const bottomResize = useResizable({
    direction: 'vertical',
    initialSize: 240,
    minSize: 100,
    maxSize: 600,
    reverse: true,
    onResize: setBottomHeight,
  });

  const aiResize = useResizable({
    direction: 'horizontal',
    initialSize: 380,
    minSize: 260,
    maxSize: 600,
    reverse: true,
    onResize: setAiWidth,
  });

  // â”€â”€ Double-click resize handle to toggle collapse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const handleSidebarHandleDblClick = useCallback(() => {
    setSidebarCollapsed(prev => !prev);
  }, []);

  const handleBottomHandleDblClick = useCallback(() => {
    setBottomCollapsed(prev => !prev);
  }, []);

  const handleAiHandleDblClick = useCallback(() => {
    setAiCollapsed(prev => !prev);
  }, []);

  // Setup bridge signal listeners and native window triggers
  useEffect(() => {
    onProjectOpened((dataStr) => {
      try {
        const data = JSON.parse(dataStr);
        if (data.success && data.project) {
          setProject(data.project.path, data.project.name, data.project);
          if (data.tree) {
            setFileTree(data.tree);
          }
        }
      } catch (e) {
        console.error('Error handling project open signal:', e);
      }
    });

    onFileTreeUpdated((treeStr) => {
      try {
        const tree = JSON.parse(treeStr);
        setFileTree(tree);
      } catch (e) {
        console.error('Error handling tree update signal:', e);
      }
    });


    // Populate recent projects list
    getRecentProjects().then((res: any) => {
      if (res && res.success && res.projects) {
        setRecentProjects(res.projects);
      }
    });

    // Register global UI hooks for PySide6 MainWindow menu actions
    window.nexcoder = {
      toggleSidebar: () => setSidebarCollapsed(prev => !prev),
      toggleTerminal: () => setBottomCollapsed(prev => !prev),
      toggleAIPanel: () => setAiCollapsed(prev => !prev),
      newTerminal: () => {
        setBottomCollapsed(false);
      },
      saveActiveFile: async () => {
        if (activeFile) {
          try {
            const res: any = await writeFile(activeFile.path, activeFile.content);
            if (res && res.success) {
              setFileDirty(activeFile.path, false);
            }
          } catch (e) {
            console.error(e);
          }
        }
      },
      saveAllFiles: async () => {
        const dirtyFiles = openFiles.filter((file) => file.isDirty);
        for (const file of dirtyFiles) {
          try {
            const res: any = await writeFile(file.path, file.content);
            if (res && res.success) {
              setFileDirty(file.path, false);
            }
          } catch (e) {
            console.error(e);
          }
        }
      },
      saveActiveFileAs: async () => {
        if (!activeFile) return;
        try {
          const res: any = await saveFileAs(activeFile.path, activeFile.content);
          if (res && res.success && res.path) {
            const name = String(res.path).split(/[\\/]/).pop() || activeFile.name;
            const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')) : '';
            replaceFileContent({
              path: res.path,
              name,
              content: activeFile.content,
              language: getLanguageFromExtension(ext),
              isDirty: false,
            }, activeFile.path);
          }
        } catch (e) {
          console.error(e);
        }
      }
    };

    return () => {
      delete window.nexcoder;
    };
  }, [activeFile, openFiles, setFileDirty, replaceFileContent]);

  return (
    <div className="app-layout">
      {/* Top Bar */}
      <TopBar
        onToggleSettings={() => setShowEditorSettings(true)}
        onToggleAgentSettings={() => setShowAgentSettings(true)}
        onToggleAuth={() => setShowAuth(true)}
        user={user}
        onLogout={() => setUser(null)}
      />

      {/* Main Workspace */}
      <div className="main-content">
        {/* Sidebar */}
        <div 
          className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}
          style={!sidebarCollapsed ? { width: sidebarWidth } : undefined}
        >
          <Sidebar isCollapsed={sidebarCollapsed} />
        </div>

        {/* Sidebar resize handle */}
        {!sidebarCollapsed && (
          <div 
            ref={sidebarResize.handleRef}
            className="resize-handle resize-handle-horizontal" 
            onMouseDown={sidebarResize.handleMouseDown}
            onDoubleClick={handleSidebarHandleDblClick}
          />
        )}

        {/* Center column: Editor + Bottom Panel */}
        <div className="center-column">
          <div className="editor-wrapper">
            <EditorArea />
          </div>

          {/* Bottom panel resize handle */}
          <div 
            ref={bottomResize.handleRef}
            className="resize-handle resize-handle-vertical" 
            onMouseDown={bottomResize.handleMouseDown}
            onDoubleClick={handleBottomHandleDblClick}
          />

          {/* Bottom panel */}
          <div 
            className={`bottom-panel ${bottomCollapsed ? 'collapsed' : ''}`}
            style={!bottomCollapsed ? { height: bottomHeight } : undefined}
          >
            <BottomPanel isCollapsed={bottomCollapsed} onClose={() => setBottomCollapsed(true)} />
          </div>
        </div>

        {/* AI Panel resize handle */}
        {!aiCollapsed && (
          <div 
            ref={aiResize.handleRef}
            className="resize-handle resize-handle-horizontal" 
            onMouseDown={aiResize.handleMouseDown}
            onDoubleClick={handleAiHandleDblClick}
          />
        )}

        {/* AI Panel */}
        <div 
          className={`ai-panel ${aiCollapsed ? 'collapsed' : ''}`}
          style={!aiCollapsed ? { width: aiWidth } : undefined}
        >
          <AIPanel />
        </div>
      </div>

      {/* Status Bar */}
      <div className="statusbar">
        <div className="statusbar-section">
          <span>Project Root: {projectPath || 'none'}</span>
        </div>
        <div className="statusbar-section">
          <span>LF</span>
          <span>UTF-8</span>
        </div>
      </div>

      {/* Modals */}
      {showAuth && (
        <LoginScreen 
          onClose={() => setShowAuth(false)} 
          onLoginSuccess={(userData) => setUser(userData)}
        />
      )}

      {showEditorSettings && (
        <EditorSettingsPage onClose={() => setShowEditorSettings(false)} />
      )}

      {showAgentSettings && (
        <AgentSettingsPage onClose={() => setShowAgentSettings(false)} />
      )}
    </div>
  );
}


