import React, { useState, useEffect, useCallback, useMemo } from 'react';
import TopBar from './components/TopBar/TopBar';
import Sidebar from './components/Sidebar/Sidebar';
import EditorArea from './components/Editor/EditorArea';
import BottomPanel from './components/BottomPanel/BottomPanel';
import AIPanel from './components/AIPanel/AIPanel';
import LoginScreen from './components/Auth/LoginScreen';
import EditorSettingsPage from './components/Settings/EditorSettingsPage';
import AgentSettingsPage from './components/Settings/AgentSettingsPage';
import OnboardingScreen from './components/Onboarding/OnboardingScreen';
import FirstRunSetup, { type SetupPatch } from './components/Onboarding/FirstRunSetup';
import { useProjectStore } from './store/useProjectStore';
import { useAgentStore } from './store/useAgentStore';
import { useEditorSettingsStore } from './store/useEditorSettingsStore';
import { usePlanStore } from './store/usePlanStore';
import { useEditorStateStore, selectActiveFile, selectOpenFiles } from './store/useEditorStateStore';
import { toShellTheme } from './services/theme';
import { useResizable } from './hooks/useResizable';
import {
  onProjectOpened,
  onFileTreeUpdated,
  onBridgeReady,
  readFile,
  writeFile,
  saveFileAs,
  getRecentProjects,
  getAppState,
  getWebAuthSessionStatus,
  clearWebAuthSession,
  getEngineSettings,
  setAppShellStage,
  updateAppState,
  updateAiSettings,
  updateEngineSettings,
  onPlanUpdated,
  onWebAuthCompleted,
} from './services/bridge';
import { getLanguageFromExtension } from './utils/languageMap';
import { getFilePreviewKind } from './utils/fileIcons';
import { countDiagnostics, useDiagnosticsStore } from './store/useDiagnosticsStore';

function normalizeStoredUser(value: any) {
  if (!value || typeof value !== 'object') return null;
  if (!value.id && !value.email) return null;
  const { session: _session, ...user } = value;
  return user;
}

function withStartupTimeout<T>(promise: Promise<T>, fallback: T, timeoutMs = 3500): Promise<T> {
  return new Promise((resolve) => {
    const timeout = window.setTimeout(() => resolve(fallback), timeoutMs);
    promise
      .then((value) => resolve(value))
      .catch(() => resolve(fallback))
      .finally(() => window.clearTimeout(timeout));
  });
}

export default function App() {
  const { setProject, setFileTree, projectPath, setRecentProjects } = useProjectStore();
  const editorState = useEditorStateStore();
  const activeFile = selectActiveFile(editorState);
  const openFiles = selectOpenFiles(editorState);
  const { setFileDirty, replaceFileContent } = useEditorStateStore();
  const { settings: agentSettings, hydrateSettings } = useAgentStore();
  const updateAgentSetting = useAgentStore((s) => s.updateSetting);
  // Select the stable store slice, then derive counts. Computing a fresh
  // object inside the selector returns a new snapshot every render, which
  // trips useSyncExternalStore's "getSnapshot should be cached" guard and
  // crashes the whole app (blank window / onboarding flash).
  const diagnosticsByPath = useDiagnosticsStore((state) => state.byPath);
  const diagnosticCounts = useMemo(
    () => countDiagnostics(diagnosticsByPath), [diagnosticsByPath]);
  const [engineSettingsReady, setEngineSettingsReady] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // The Python process loads .env before the web UI starts. Hydrate that
  // authoritative provider configuration before allowing persisted browser
  // settings to sync back, otherwise an old local endpoint can overwrite a
  // newly configured hosted provider during the first render.
  useEffect(() => {
    let active = true;
    const hasSavedAgentSettings = Boolean(
      localStorage.getItem('nexcoder_agent_settings')
      || localStorage.getItem('nexcoder_settings'),
    );
    getEngineSettings()
      .then((result) => {
        if (!active || !result?.success || !result.settings) return;
        if (hasSavedAgentSettings) return;
        const backend = result.settings;
        hydrateSettings({
          aiEndpoint: backend.base_url,
          aiModel: backend.model,
          adapter: backend.adapter,
          contextWindow: backend.context_window,
          maxOutputTokens: backend.max_output_tokens,
          temperature: backend.temperature,
          fullAuto: !!backend.full_auto,
          autonomy: backend.autonomy,
        });
      })
      .catch((error) => console.error('Failed to hydrate engine settings:', error))
      .finally(() => { if (active) setEngineSettingsReady(true); });
    return () => { active = false; };
  }, [hydrateSettings]);

  // Sync AI settings to Python backend whenever they change in the UI
  useEffect(() => {
    if (!engineSettingsReady) return;
    updateAiSettings(agentSettings.aiEndpoint, agentSettings.aiModel)
      .catch((e) => console.error('Failed to sync AI settings to backend:', e));
  }, [engineSettingsReady, agentSettings.aiEndpoint, agentSettings.aiModel]);

  // Same for engine settings (context window, adapter, autonomy, model
  // knobs, tool toggles, validation overrides)
  useEffect(() => {
    if (!engineSettingsReady) return;
    updateEngineSettings({
      context_window: agentSettings.contextWindow,
      adapter: agentSettings.adapter,
      autonomy: agentSettings.autonomy,
      max_output_tokens: agentSettings.maxOutputTokens,
      temperature: agentSettings.temperature,
      max_turns: agentSettings.maxTurns,
      disabled_tools: agentSettings.disabledTools,
      memory_enabled: agentSettings.memoryEnabled,
      cmd_build: agentSettings.cmdBuild,
      cmd_test: agentSettings.cmdTest,
      cmd_lint: agentSettings.cmdLint,
    }).catch((e) => console.error('Failed to sync engine settings:', e));
  }, [engineSettingsReady, agentSettings.contextWindow, agentSettings.adapter, agentSettings.autonomy,
      agentSettings.maxOutputTokens, agentSettings.temperature, agentSettings.maxTurns,
      agentSettings.disabledTools, agentSettings.memoryEnabled,
      agentSettings.cmdBuild, agentSettings.cmdTest, agentSettings.cmdLint]);

  // Appearance: UI scale applies to the whole window.
  const editorSettings = useEditorSettingsStore((s) => s.settings);
  const updateEditorSetting = useEditorSettingsStore((s) => s.updateSetting);
  useEffect(() => {
    (document.body.style as any).zoom = `${editorSettings.uiScale}%`;
  }, [editorSettings.uiScale]);

  // Theme: stamp data-theme on the root so the whole IDE (not just the
  // editor) swaps its CSS variables. The NexCoder default removes the
  // attribute; every other theme has its own variable block in index.css.
  useEffect(() => {
    const shell = toShellTheme(editorSettings.theme);
    if (shell) document.documentElement.setAttribute('data-theme', shell);
    else document.documentElement.removeAttribute('data-theme');
  }, [editorSettings.theme]);

  // Plans are first-class editor artifacts. Keep this listener separate from
  // the native menu wiring so opening files does not register duplicates.
  useEffect(() => {
    onPlanUpdated((planJson) => {
      try {
        const decoded = JSON.parse(planJson);
        const plan = decoded?.plan || decoded?.payload?.plan || decoded;
        if (!plan?.id) return;
        usePlanStore.getState().setPlan(plan);

        const virtualPath = `__nexcoder_plan__/${plan.id}`;
        const state = useEditorStateStore.getState();
        const alreadyOpen = state.editorGroups.some((group) =>
          group.openFiles.some((file) => file.path === virtualPath));
        if (!alreadyOpen) {
          state.openFile({
            path: virtualPath,
            name: 'Implementation Plan',
            content: plan.markdown_content || '',
            language: 'markdown',
            isDirty: false,
            kind: 'implementation_plan',
            resourceId: plan.id,
          });
        }
      } catch (error) {
        console.error('Error handling plan update signal:', error);
      }
    });
  }, []);

  // Restore previously open files when a project opens (once per project).
  const editorGroupsState = useEditorStateStore((s) => s.editorGroups);
  const restoredProjectRef = React.useRef<string | null>(null);
  useEffect(() => {
    if (!projectPath || restoredProjectRef.current === projectPath) return;
    restoredProjectRef.current = projectPath;
    if (!editorSettings.restoreOpenFiles) return;
    const raw = localStorage.getItem(`nexcoder_open_tabs:${projectPath}`);
    if (!raw) return;
    (async () => {
      try {
        const { paths, active } = JSON.parse(raw);
        const state = useEditorStateStore.getState();
        for (const path of (paths || []).slice(0, 20)) {
          const name = String(path).split(/[\\/]/).pop() || path;
          const ext = name.includes('.') ? name.split('.').pop() || '' : '';
          if (getFilePreviewKind(path) !== 'text') {
            state.openFile({
              path, name, content: '', language: 'plaintext', isDirty: false,
            });
            continue;
          }

          const res: any = await readFile(path);
          if (res?.success) {
            state.openFile({
              path, name, content: res.content,
              language: getLanguageFromExtension(ext), isDirty: false,
            });
          }
        }
        if (active) state.setActiveFile(active);
      } catch { /* stale entries are fine to skip */ }
    })();
  }, [projectPath, editorSettings.restoreOpenFiles]);

  // Persist the open-tab set per project.
  useEffect(() => {
    if (!projectPath || restoredProjectRef.current !== projectPath) return;
    const paths = editorGroupsState.flatMap((g) => g.openFiles
      .filter((file) => !file.kind || file.kind === 'file')
      .map((file) => file.path));
    const activeGroup = editorGroupsState.find((g) =>
      g.openFiles.some((file) => !file.kind || file.kind === 'file'));
    const persistedActive = activeGroup?.openFiles.some((file) =>
      file.path === activeGroup.activeFilePath && (!file.kind || file.kind === 'file'))
      ? activeGroup.activeFilePath : null;
    localStorage.setItem(`nexcoder_open_tabs:${projectPath}`, JSON.stringify({
      paths, active: persistedActive,
    }));
  }, [editorGroupsState, projectPath]);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [bottomCollapsed, setBottomCollapsed] = useState(false);
  const [aiCollapsed, setAiCollapsed] = useState(false);

  const [showEditorSettings, setShowEditorSettings] = useState(false);
  const [showAgentSettings, setShowAgentSettings] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [appStateReady, setAppStateReady] = useState(false);
  const [onboardingCompleted, setOnboardingCompleted] = useState(false);
  const [firstRunSetupCompleted, setFirstRunSetupCompleted] = useState(false);
  const [user, setUser] = useState<any>(null);

  const loadAppState = useCallback(async () => {
    try {
      const result = await withStartupTimeout(
        getAppState(),
        { success: false, state: {} },
      );
      const state = result?.success && result.state ? result.state : {};
      let nextUser = normalizeStoredUser(state.web_user);

      if (!nextUser) {
        try {
          const legacyUser = localStorage.getItem('nexcoder_web_user');
          if (legacyUser) {
            nextUser = normalizeStoredUser(JSON.parse(legacyUser));
            if (nextUser) {
              void withStartupTimeout(
                updateAppState({ web_user: nextUser }),
                { success: false },
              );
            }
          }
          localStorage.removeItem('nexcoder_web_user');
        } catch {
          localStorage.removeItem('nexcoder_web_user');
        }
      }

      if (nextUser) {
        const sessionStatus = await withStartupTimeout(
          getWebAuthSessionStatus(),
          { success: false, authenticated: false },
        );
        if (!sessionStatus?.success || !sessionStatus.authenticated) {
          void withStartupTimeout(
            updateAppState({ web_user: null }),
            { success: false },
          );
          nextUser = null;
        }
      }

      setUser(nextUser);
      setOnboardingCompleted(Boolean(state.onboarding_completed));
      setFirstRunSetupCompleted(Boolean(state.first_run_setup_completed));
    } catch (error) {
      console.error('Failed to load NexCoder app state:', error);
    } finally {
      setAppStateReady(true);
    }
  }, []);

  useEffect(() => {
    let active = true;
    let loadedNative = false;
    // In the packaged app a real Qt bridge is expected; initBridge may
    // install a temporary MOCK bridge on a 2s timeout during a cold
    // QWebEngine start. Loading auth/onboarding state off that mock and
    // then off the real bridge is what makes the onboarding screen flash
    // for ~0.1s. So when a native transport exists, wait for the native
    // bridge and only fall back to the mock if it never arrives.
    const expectsNative =
      typeof (window as any).QWebChannel !== 'undefined'
      && !!(window as any).qt?.webChannelTransport;

    // Absolute backstop: never hang on the loading screen forever.
    const backstopTimer = window.setTimeout(() => {
      if (active && !appStateReady) void loadAppState();
    }, 12000);

    const unsubscribe = onBridgeReady((native: boolean) => {
      if (!active) return;
      // Ignore the transient mock when a native bridge is still coming.
      if (!native && expectsNative && !loadedNative) return;
      if (native) loadedNative = true;
      window.clearTimeout(backstopTimer);
      void loadAppState();
    });
    return () => {
      active = false;
      window.clearTimeout(backstopTimer);
      unsubscribe();
    };
  }, [loadAppState]);

  useEffect(() => {
    const unsubscribe = onWebAuthCompleted((eventJson) => {
      try {
        const result = JSON.parse(eventJson);
        if (!result?.success || !result.user) {
          setAuthError(result?.error || 'Web login did not complete.');
          setShowAuth(true);
          return;
        }
        const nextUser = normalizeStoredUser(result.user);
        if (!nextUser || !result.session?.authenticated) {
          setAuthError('Web login completed without a desktop session.');
          setShowAuth(true);
          return;
        }
        const persistedUser = {
          ...nextUser,
          provider: 'nexcoder-web',
        };
        void updateAppState({ web_user: persistedUser });
        localStorage.removeItem('nexcoder_web_user');
        setUser(persistedUser);
        setAuthError(null);
        setShowAuth(false);
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : String(error));
        setShowAuth(true);
      }
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    const stage = appStateReady && user && firstRunSetupCompleted ? 'ide' : 'auth';
    void setAppShellStage(stage);
  }, [appStateReady, firstRunSetupCompleted, user]);

  const handleLogout = useCallback(() => {
    localStorage.removeItem('nexcoder_web_user');
    void clearWebAuthSession();
    void updateAppState({ web_user: null });
    setUser(null);
    setAuthError(null);
  }, []);

  const handleStartLoginFromOnboarding = useCallback(() => {
    void updateAppState({ onboarding_completed: true });
    setOnboardingCompleted(true);
    setAuthError(null);
    setShowAuth(true);
  }, []);

  const handleOpenLogin = useCallback(() => {
    setAuthError(null);
    setShowAuth(true);
  }, []);

  const handleFirstRunSetupComplete = useCallback((patch: SetupPatch) => {
    (Object.entries(patch.editor) as Array<[keyof typeof editorSettings, typeof editorSettings[keyof typeof editorSettings]]>)
      .forEach(([key, value]) => {
        updateEditorSetting(key, value);
      });

    (Object.entries(patch.agent) as Array<[keyof typeof agentSettings, typeof agentSettings[keyof typeof agentSettings]]>)
      .forEach(([key, value]) => {
        updateAgentSetting(key, value);
      });

    void updateAppState({
      first_run_setup_completed: true,
      onboarding_profile: patch.profile,
    });
    setFirstRunSetupCompleted(true);
  }, [agentSettings, editorSettings, updateAgentSetting, updateEditorSetting]);

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

  // Ã¢â€â‚¬Ã¢â€â‚¬ Resizable panel state Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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

  // Ã¢â€â‚¬Ã¢â€â‚¬ Double-click resize handle to toggle collapse Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
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
      showAIPanel: () => setAiCollapsed(false),
      showSidebarTab: (tabId?: string) => {
        setSidebarCollapsed(false);
        window.dispatchEvent(new CustomEvent('nexcoder:show-sidebar-tab', {
          detail: { tabId: tabId || 'explorer' },
        }));
      },
      showBottomPanel: (tabId?: string) => {
        setBottomCollapsed(false);
        window.dispatchEvent(new CustomEvent('nexcoder:show-bottom-tab', {
          detail: { tabId: tabId || 'terminal' },
        }));
      },
      newTerminal: (cwd?: string) => {
        setBottomCollapsed(false);
        window.dispatchEvent(new CustomEvent('nexcoder:show-bottom-tab', {
          detail: { tabId: 'terminal' },
        }));
        window.dispatchEvent(new CustomEvent('nexcoder:new-terminal', {
          detail: { cwd: cwd || '' },
        }));
      },
      saveActiveFile: async () => {
        if (activeFile && (!activeFile.kind || activeFile.kind === 'file')
            && getFilePreviewKind(activeFile.path) === 'text') {
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
        const dirtyFiles = openFiles.filter((file) =>
          file.isDirty
          && (!file.kind || file.kind === 'file')
          && getFilePreviewKind(file.path) === 'text');
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
        if (!activeFile || activeFile.kind === 'implementation_plan'
            || activeFile.kind === 'artifact'
            || getFilePreviewKind(activeFile.path) !== 'text') return;
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

  if (!appStateReady) {
    return (
      <div className="onboarding-auth-stage">
        <div className="onboarding-auth-card">
          <div className="onboarding-logo">N</div>
          <h1>Opening NexCoder</h1>
          <p>Loading your desktop workspace state.</p>
        </div>
      </div>
    );
  }

  if (!user && !onboardingCompleted) {
    return <OnboardingScreen onStartLogin={handleStartLoginFromOnboarding} />;
  }

  if (!user) {
    return (
      <div className="onboarding-auth-stage">
        <div className="onboarding-auth-card">
          <div className="onboarding-logo">N</div>
          <h1>Sign in to continue</h1>
          <p>
            NexCoder uses your web account to sync identity and unlock the authenticated desktop workspace.
          </p>
          <button className="btn btn-primary onboarding-primary" type="button" onClick={handleOpenLogin}>
            Open NexCoder Web Login
          </button>
        </div>

        {showAuth && (
          <LoginScreen
            onClose={() => setShowAuth(false)}
            authError={authError}
          />
        )}
      </div>
    );
  }

  if (!firstRunSetupCompleted) {
    return (
      <FirstRunSetup
        userName={user.name || user.email}
        onComplete={handleFirstRunSetupComplete}
      />
    );
  }

  return (
    <div className="app-layout">
      {/* Top Bar */}
      <TopBar
        onToggleSettings={() => setShowEditorSettings(true)}
        onToggleAgentSettings={() => setShowAgentSettings(true)}
        onToggleAuth={handleOpenLogin}
        user={user}
        onLogout={handleLogout}
      />

      {/* Main Workspace â€” panel sides are settings-driven via flex order */}
      <div className="main-content">
        {/* Sidebar */}
        <div
          className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}
          style={{
            ...(sidebarCollapsed ? {} : { width: sidebarWidth }),
            order: editorSettings.sidebarPosition === 'right' ? 9 : 0,
          }}
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
            style={{ order: editorSettings.sidebarPosition === 'right' ? 8 : 1 }}
          />
        )}

        {/* Center column: Editor + Bottom Panel */}
        <div className="center-column" style={{ order: 5 }}>
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
            style={{ order: editorSettings.aiPanelPosition === 'left' ? 3 : 6 }}
          />
        )}

        {/* AI Panel */}
        <div
          className={`ai-panel ${aiCollapsed ? 'collapsed' : ''}`}
          style={{
            ...(aiCollapsed ? {} : { width: aiWidth }),
            order: editorSettings.aiPanelPosition === 'left' ? 2 : 7,
          }}
        >
          <AIPanel />
        </div>
      </div>

      {/* Status Bar */}
      <div className="statusbar">
        <div className="statusbar-section">
          <span>Project Root: {projectPath || 'none'}</span>
          {diagnosticCounts.total > 0 && (
            <span
              className={`statusbar-item clickable problem-count ${diagnosticCounts.errors > 0 ? 'error' : diagnosticCounts.warnings > 0 ? 'warning' : ''}`}
              title={`${diagnosticCounts.total} problems: ${diagnosticCounts.errors} errors, ${diagnosticCounts.warnings} warnings`}
              onClick={() => {
                window.nexcoder?.showBottomPanel?.('problems');
              }}
            >
              Problems: {diagnosticCounts.total}
            </span>
          )}
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
          authError={authError}
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

