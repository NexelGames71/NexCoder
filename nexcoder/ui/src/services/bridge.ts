/**
 * Bridge â€” TypeScript wrapper around the QWebChannel Python bridge.
 * Provides typed async methods matching the Python Bridge class.
 */

// Global QWebChannel type
declare global {
  interface Window {
    QWebChannel: any;
    qt: { webChannelTransport: any };
    nexcoder?: {
      toggleSidebar: () => void;
      toggleTerminal: () => void;
      toggleAIPanel: () => void;
      showAIPanel?: () => void;
      showSidebarTab?: (tabId?: string) => void;
      showBottomPanel?: (tabId?: string) => void;
      newTerminal: (cwd?: string) => void;
      saveActiveFile: () => void;
      saveAllFiles: () => void;
      saveActiveFileAs: () => void;
    };
  }
}

let bridge: any = null;
const pendingSignalListeners: Record<string, Function[]> = {};
const bridgeReadyListeners: Array<(native: boolean) => void> = [];

/**
 * Initialize the QWebChannel bridge to Python backend.
 */
export async function initBridge(): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const installBridge = (nextBridge: any) => {
      bridge = nextBridge;
      flushPendingSignalListeners();
      const native = !nextBridge?.__mock;
      bridgeReadyListeners.forEach((listener) => listener(native));
    };
    const finish = (nextBridge: any) => {
      installBridge(nextBridge);
      if (settled) return;
      settled = true;
      resolve();
    };
    const timeout = window.setTimeout(() => {
      console.warn('[Bridge] QWebChannel initialization timed out, rendering with mock bridge');
      finish(createMockBridge());
    }, 2000);

    if (typeof window.QWebChannel === 'undefined' || !window.qt?.webChannelTransport) {
      console.warn('[Bridge] QWebChannel not available, using mock bridge');
      window.clearTimeout(timeout);
      finish(createMockBridge());
      return;
    }

    try {
      new window.QWebChannel(window.qt.webChannelTransport, (channel: any) => {
        window.clearTimeout(timeout);
        const nativeBridge = channel?.objects?.bridge;
        if (!nativeBridge) {
          console.warn('[Bridge] QWebChannel connected without a bridge object, using mock bridge');
          finish(createMockBridge());
          return;
        }
        console.log('[Bridge] Connected to Python backend');
        if (settled) {
          installBridge(nativeBridge);
          return;
        }
        finish(nativeBridge);
      });
    } catch (err) {
      console.error('[Bridge] Connection failed:', err);
      window.clearTimeout(timeout);
      finish(createMockBridge());
    }
  });
}

/**
 * Get the bridge instance.
 */
export function getBridge(): any {
  return bridge;
}

export function onBridgeReady(callback: (native: boolean) => void): () => void {
  bridgeReadyListeners.push(callback);
  if (bridge) {
    queueMicrotask(() => callback(!bridge?.__mock));
  }
  return () => {
    const index = bridgeReadyListeners.indexOf(callback);
    if (index >= 0) {
      bridgeReadyListeners.splice(index, 1);
    }
  };
}

// â”€â”€ Typed API Methods â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export async function openFolderDialog(): Promise<string> {
  if (!bridge) return '';
  return callBridge('open_folder_dialog');
}

export async function openFileDialog(): Promise<string> {
  if (!bridge) return '';
  return callBridge('open_file_dialog');
}

export async function selectFolderDialog(title = 'Select Folder'): Promise<string> {
  if (!bridge) return '';
  return callBridge('select_folder_dialog', title);
}

export async function openProject(path: string): Promise<any> {
  return callBridge('open_project', path);
}

export async function cloneRepository(
  repositoryUrl: string,
  destinationParent = '',
  directoryName = '',
): Promise<any> {
  return callBridge('clone_repository', repositoryUrl, destinationParent, directoryName);
}

export async function readFile(path: string): Promise<any> {
  return callBridge('read_file', path);
}

export async function readFileBase64(path: string): Promise<any> {
  return callBridge('read_file_base64', path);
}

export async function writeFileBase64(path: string, b64: string): Promise<any> {
  return callBridge('write_file_base64', path, b64);
}

export async function writeFile(path: string, content: string): Promise<any> {
  return callBridge('write_file', path, content);
}

export async function saveFileAs(path: string, content: string): Promise<any> {
  return callBridge('save_file_as', path, content);
}

export async function deleteFile(path: string): Promise<any> {
  return callBridge('delete_file', path);
}

export async function deleteArtifactFile(path: string): Promise<any> {
  return callBridge('delete_artifact_file', path);
}

export async function renameFile(oldPath: string, newPath: string): Promise<any> {
  return callBridge('rename_file', oldPath, newPath);
}

export async function createDirectory(path: string): Promise<any> {
  return callBridge('create_directory', path);
}

export async function createFile(path: string, content: string = ''): Promise<any> {
  return callBridge('create_file', path, content);
}

export async function getFileTree(root: string): Promise<any> {
  return callBridge('get_file_tree', root);
}

export async function searchFiles(query: string, root?: string): Promise<any> {
  return callBridge('search_files', query, root || '');
}

// Desktop app state (stored in the user's NexCoder AppData folder)
export async function getAppState(): Promise<any> {
  return callBridge('app_state_get');
}

export async function updateAppState(patch: Record<string, unknown>): Promise<any> {
  return callBridge('app_state_update', JSON.stringify(patch));
}

export async function getWebAuthSessionStatus(): Promise<any> {
  return callBridge('web_auth_session_status');
}

export async function clearWebAuthSession(): Promise<any> {
  return callBridge('web_auth_clear');
}

export async function setAppShellStage(stage: 'auth' | 'ide'): Promise<any> {
  return callBridge('app_shell_set_stage', stage);
}

// Terminal
export async function spawnTerminal(cwd?: string): Promise<any> {
  return callBridge('spawn_terminal', cwd || '');
}

export async function getTerminalSnapshot(sessionId: string): Promise<any> {
  return callBridge('terminal_snapshot', sessionId);
}

export async function writeTerminal(sessionId: string, data: string): Promise<any> {
  return callBridge('write_terminal', sessionId, data);
}

export async function resizeTerminal(sessionId: string, cols: number, rows: number): Promise<any> {
  return callBridge('resize_terminal', sessionId, cols, rows);
}

export async function killTerminal(sessionId: string): Promise<any> {
  return callBridge('kill_terminal', sessionId);
}

// Git
export async function gitStatus(root?: string): Promise<any> {
  return callBridge('git_status', root || '');
}

export async function gitDiff(root?: string): Promise<any> {
  return callBridge('git_diff', root || '');
}

export async function gitStage(root: string, files: string[]): Promise<any> {
  return callBridge('git_stage', root, JSON.stringify(files));
}

export async function gitCommit(root: string, message: string): Promise<any> {
  return callBridge('git_commit', root, message);
}

export async function gitBranch(root?: string): Promise<any> {
  return callBridge('git_branch', root || '');
}

export async function gitLog(root?: string, count?: number): Promise<any> {
  return callBridge('git_log', root || '', count || 20);
}

// Agent v2 (agentic core engine â€” every AI mode)
export async function agentRunV2(
  prompt: string, skillId = '', mode = 'agent', contextJson = '',
): Promise<any> {
  return callBridge('agent_run_v2', prompt, skillId, mode, contextJson);
}

export async function agentPermissionResponse(requestId: string, decision: 'allow' | 'allow_always' | 'deny'): Promise<any> {
  return callBridge('agent_permission_response', requestId, decision);
}

export async function agentCancelV2(): Promise<any> {
  return callBridge('agent_cancel_v2');
}

export async function agentSteerV2(
  prompt: string, attachments: any[] = [], clientPromptId = '',
): Promise<any> {
  return callBridge('agent_steer_v2', prompt, JSON.stringify(attachments), clientPromptId);
}

export async function agentRevertRun(checkpointId: string): Promise<any> {
  return callBridge('agent_revert_run', checkpointId);
}

export async function agentRevertFile(checkpointId: string, path: string): Promise<any> {
  return callBridge('agent_revert_file', checkpointId, path);
}

export async function agentRewindToPrompt(
  sessionId: string,
  target: { client_prompt_id: string; content: string; user_ordinal: number },
): Promise<any> {
  return callBridge('agent_rewind_to_prompt', sessionId, JSON.stringify(target));
}

// Persistent implementation plans
export async function getPlan(planId: string): Promise<any> {
  return callBridge('plan_get', planId);
}

export async function listPlans(conversationId = ''): Promise<any> {
  return callBridge('plan_list', conversationId);
}

export async function answerPlanQuestions(
  planId: string, revision: number, answers: Record<string, unknown>,
): Promise<any> {
  return callBridge('plan_answer', planId, revision, JSON.stringify(answers));
}

export async function requestPlanRevision(
  planId: string, revision: number, review: string,
): Promise<any> {
  return callBridge('plan_request_revision', planId, revision, review);
}

export async function approvePlanAndExecute(planId: string, revision: number): Promise<any> {
  return callBridge('plan_approve_and_execute', planId, revision);
}

export async function cancelPlan(planId: string): Promise<any> {
  return callBridge('plan_cancel', planId);
}

export async function savePlanMarkdown(planId: string, suggestedPath = ''): Promise<any> {
  return callBridge('plan_save_markdown', planId, suggestedPath);
}

export function onPlanUpdated(callback: (planJson: string) => void): void {
  connectSignal('plan_updated', callback);
}

// Engine settings / permissions / project memory (settings surface)
export async function getEngineSettings(): Promise<any> {
  return callBridge('agent_get_engine_settings');
}

export async function updateEngineSettings(settings: {
  context_window?: number; adapter?: string; full_auto?: boolean;
  autonomy?: string; max_output_tokens?: number; temperature?: number;
  max_turns?: number; disabled_tools?: string[]; memory_enabled?: boolean;
  cmd_build?: string; cmd_test?: string; cmd_lint?: string;
}): Promise<any> {
  return callBridge('agent_update_engine_settings', JSON.stringify(settings));
}

export async function listAgentPermissions(): Promise<any> {
  return callBridge('agent_permissions_list');
}

export async function removeAgentPermission(command: string): Promise<any> {
  return callBridge('agent_permissions_remove', command);
}

export async function getProjectMemory(): Promise<any> {
  return callBridge('agent_memory_get');
}

// LSP (language intelligence)
export async function lspDidOpen(path: string, language: string, text: string): Promise<any> {
  return callBridge('lsp_did_open', path, language, text);
}

export async function lspDidChange(path: string, text: string): Promise<any> {
  return callBridge('lsp_did_change', path, text);
}

export async function lspDidClose(path: string): Promise<any> {
  return callBridge('lsp_did_close', path);
}

export async function lspRequestRaw(
  requestId: string, kind: string, path: string,
  line: number, character: number, extra = '',
): Promise<any> {
  return callBridge('lsp_request', requestId, kind, path, line, character, extra);
}

export async function lspStatus(): Promise<any> {
  return callBridge('lsp_status');
}

export async function testModelConnection(): Promise<any> {
  return callBridge('test_model_connection');
}

export async function getActiveRules(): Promise<any> {
  return callBridge('agent_get_active_rules');
}

export function onLspResponse(callback: (json: string) => void): void {
  connectSignal('lsp_response', callback);
}

export function onLspDiagnostics(callback: (json: string) => void): void {
  connectSignal('lsp_diagnostics', callback);
}

export async function saveProjectMemory(content: string): Promise<any> {
  return callBridge('agent_memory_save', content);
}

export function onAgentEvent(callback: (eventJson: string) => void): void {
  connectSignal('agent_event', callback);
}

// Agent Mesh (orchestrator + specialist agents)
export async function meshRun(goal: string): Promise<any> {
  return callBridge('mesh_run', goal);
}

export async function meshCancel(): Promise<any> {
  return callBridge('mesh_cancel');
}

export async function meshList(): Promise<any> {
  return callBridge('mesh_list');
}

export function onMeshEvent(callback: (eventJson: string) => void): void {
  connectSignal('mesh_event', callback);
}

export async function agentApproveDiff(diffId: string): Promise<any> {
  return callBridge('agent_approve_diff', diffId);
}

export async function agentApprovePatchset(diffIds: string[]): Promise<any> {
  return callBridge('agent_approve_patchset', JSON.stringify(diffIds));
}

export async function agentRejectDiff(diffId: string): Promise<any> {
  return callBridge('agent_reject_diff', diffId);
}

export async function updateAiSettings(endpoint: string, model: string): Promise<any> {
  return callBridge('update_ai_settings', endpoint, model);
}

export async function listSessions(projectPath?: string): Promise<any> {
  return callBridge('list_sessions', projectPath || '');
}

export async function loadSession(projectPath: string, sessionId: string): Promise<any> {
  return callBridge('load_session', projectPath, sessionId);
}

export async function deleteSession(projectPath: string, sessionId: string): Promise<any> {
  return callBridge('delete_session', projectPath, sessionId);
}

export async function archiveSession(projectPath: string, sessionId: string, archived = true): Promise<any> {
  return callBridge('archive_session', projectPath, sessionId, JSON.stringify(archived));
}

export async function createSession(projectPath: string, title = 'New session', mode = 'ask'): Promise<any> {
  return callBridge('create_session', projectPath, title, mode);
}

// Skills (grouped catalog and per-skill body fetcher)
export async function fetchSkills(): Promise<{
  categories: Array<{ id: string; label: string; description: string; icon: string; order: number }>;
  skills_by_category: Record<string, Array<{ id: string; label: string; description: string; category: string; icon: string; shortcut: string }>>;
} | null> {
  const result = await callBridge('get_skills');
  if (result?.success) {
    return { categories: result.categories, skills_by_category: result.skills_by_category };
  }
  return null;
}

export async function fetchSkillBody(skillId: string): Promise<{
  id: string;
  name: string;
  category: string;
  body: string;
} | null> {
  const result = await callBridge('get_skill_body', skillId);
  if (result?.success) {
    return { id: result.id, name: result.name, category: result.category, body: result.body };
  }
  return null;
}

// Appwrite
export async function appwriteLogin(email: string, password: string): Promise<any> {
  return callBridge('appwrite_login', email, password);
}

export async function appwriteRegister(email: string, password: string, name: string): Promise<any> {
  return callBridge('appwrite_register', email, password, name);
}

export async function appwriteLogout(): Promise<any> {
  return callBridge('appwrite_logout');
}

export async function startWebAuthLogin(): Promise<any> {
  return callBridge('web_auth_start');
}

export function onWebAuthCompleted(callback: (eventJson: string) => void): () => void {
  return connectSignal('web_auth_completed', callback);
}

export async function saveToAppwrite(collection: string, data: any): Promise<any> {
  return callBridge('save_to_appwrite', collection, JSON.stringify(data));
}

export async function getRecentProjects(): Promise<any> {
  return callBridge('get_recent_projects');
}

// â”€â”€ Signal Listeners â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function onTerminalOutput(
  callback: (sessionId: string, data: string, sequence: number) => void,
): () => void {
  return connectSignal('terminal_output', callback);
}

export function onTerminalExited(
  callback: (sessionId: string, exitCode: number) => void,
): () => void {
  return connectSignal('terminal_exited', callback);
}

export function onAgentStream(callback: (chunk: string) => void): void {
  connectSignal('agent_stream', callback);
}

export function onAgentStatus(callback: (status: string) => void): void {
  connectSignal('agent_status', callback);
}

export function onAgentDiff(callback: (diff: string) => void): void {
  connectSignal('agent_diff', callback);
}

export function onAgentComplete(callback: (result: string) => void): void {
  connectSignal('agent_complete', callback);
}

export function onFileTreeUpdated(callback: (path: string) => void): void {
  connectSignal('file_tree_updated', callback);
}

export function onProjectOpened(callback: (info: string) => void): void {
  connectSignal('project_opened', callback);
}

export function onCloneCompleted(callback: (info: string) => void): () => void {
  return connectSignal('clone_completed', callback);
}

export function onGitUpdated(callback: (status: string) => void): void {
  connectSignal('git_updated', callback);
}

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async function callBridge(method: string, ...args: any[]): Promise<any> {
  if (!bridge || !bridge[method]) {
    console.warn(`[Bridge] Method not available: ${method}`);
    return { success: false, error: 'Bridge not available' };
  }

  try {
    let result = bridge[method](...args);
    // If it's a QWebChannel promise, await it
    if (result && typeof result.then === 'function') {
      result = await result;
    }

    if (typeof result === 'string') {
      try {
        return JSON.parse(result);
      } catch {
        return result;
      }
    }
    return result;
  } catch (err) {
    console.error(`[Bridge] Error calling ${method}:`, err);
    return { success: false, error: String(err) };
  }
}

function connectSignal(signalName: string, callback: Function): () => void {
  const signal = bridge?.[signalName];
  if (signal && typeof signal.connect === 'function') {
    signal.connect(callback);
  } else {
    pendingSignalListeners[signalName] = pendingSignalListeners[signalName] || [];
    if (!pendingSignalListeners[signalName].includes(callback)) {
      pendingSignalListeners[signalName].push(callback);
    }
  }

  return () => {
    const callbacks = pendingSignalListeners[signalName];
    if (callbacks) {
      pendingSignalListeners[signalName] = callbacks.filter((item) => item !== callback);
    }
    const currentSignal = bridge?.[signalName];
    if (currentSignal && typeof currentSignal.disconnect === 'function') {
      try {
        currentSignal.disconnect(callback);
      } catch {
        // QWebChannel may already have disconnected during application teardown.
      }
    }
  };
}

function flushPendingSignalListeners(): void {
  for (const [signalName, callbacks] of Object.entries(pendingSignalListeners)) {
    const signal = bridge?.[signalName];
    if (!signal || typeof signal.connect !== 'function') {
      continue;
    }
    callbacks.forEach((callback) => signal.connect(callback));
    pendingSignalListeners[signalName] = [];
  }
}

/**
 * Create a mock bridge for development mode (no QWebChannel).
 */
function createMockBridge(): any {
  return new Proxy({ __mock: true }, {
    get(target, prop) {
      if (typeof prop === 'string') {
        return (...args: any[]) => {
          console.log(`[MockBridge] ${prop}(`, ...args, ')');
          return JSON.stringify({ success: true, mock: true });
        };
      }
      return undefined;
    },
  });
}

