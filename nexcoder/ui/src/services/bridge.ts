/**
 * Bridge — TypeScript wrapper around the QWebChannel Python bridge.
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
      newTerminal: () => void;
      saveActiveFile: () => void;
      saveAllFiles: () => void;
      saveActiveFileAs: () => void;
    };
  }
}

let bridge: any = null;
const pendingSignalListeners: Record<string, Function[]> = {};

/**
 * Initialize the QWebChannel bridge to Python backend.
 */
export async function initBridge(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window.QWebChannel === 'undefined') {
      // Development mode — no QWebChannel available
      console.warn('[Bridge] QWebChannel not available, using mock bridge');
      bridge = createMockBridge();
      flushPendingSignalListeners();
      resolve();
      return;
    }

    try {
      new window.QWebChannel(window.qt.webChannelTransport, (channel: any) => {
        bridge = channel.objects.bridge;
        flushPendingSignalListeners();
        console.log('[Bridge] Connected to Python backend');
        resolve();
      });
    } catch (err) {
      console.error('[Bridge] Connection failed:', err);
      bridge = createMockBridge();
      flushPendingSignalListeners();
      resolve();
    }
  });
}

/**
 * Get the bridge instance.
 */
export function getBridge(): any {
  return bridge;
}

// ── Typed API Methods ──────────────────────────────────────────────

export async function openFolderDialog(): Promise<string> {
  if (!bridge) return '';
  return callBridge('open_folder_dialog');
}

export async function openProject(path: string): Promise<any> {
  return callBridge('open_project', path);
}

export async function readFile(path: string): Promise<any> {
  return callBridge('read_file', path);
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

// Terminal
export async function spawnTerminal(cwd?: string): Promise<any> {
  return callBridge('spawn_terminal', cwd || '');
}

export function writeTerminal(sessionId: string, data: string): void {
  if (bridge) bridge.write_terminal(sessionId, data);
}

export function resizeTerminal(sessionId: string, cols: number, rows: number): void {
  if (bridge) bridge.resize_terminal(sessionId, cols, rows);
}

export function killTerminal(sessionId: string): void {
  if (bridge) bridge.kill_terminal(sessionId);
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

// Agent / AI
export async function agentAsk(prompt: string, context: any): Promise<any> {
  return callBridge('agent_ask', prompt, JSON.stringify(context));
}

export async function agentEdit(prompt: string, context: any): Promise<any> {
  return callBridge('agent_edit', prompt, JSON.stringify(context));
}

export async function agentRun(prompt: string, context: any): Promise<any> {
  return callBridge('agent_run', prompt, JSON.stringify(context));
}

export async function agentScan(context: any): Promise<any> {
  return callBridge('agent_scan', JSON.stringify(context));
}

export async function agentDebug(prompt: string, context: any): Promise<any> {
  return callBridge('agent_debug', prompt, JSON.stringify(context));
}

export async function agentReview(prompt: string, context: any): Promise<any> {
  return callBridge('agent_review', prompt, JSON.stringify(context));
}

// Agent v2 (agentic core engine)
export async function agentRunV2(prompt: string, skillId = ''): Promise<any> {
  return callBridge('agent_run_v2', prompt, skillId);
}

export async function agentPermissionResponse(requestId: string, decision: 'allow' | 'allow_always' | 'deny'): Promise<any> {
  return callBridge('agent_permission_response', requestId, decision);
}

export async function agentRevertRun(checkpointId: string): Promise<any> {
  return callBridge('agent_revert_run', checkpointId);
}

export async function agentRevertFile(checkpointId: string, path: string): Promise<any> {
  return callBridge('agent_revert_file', checkpointId, path);
}

export function onAgentEvent(callback: (eventJson: string) => void): void {
  connectSignal('agent_event', callback);
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

export async function saveToAppwrite(collection: string, data: any): Promise<any> {
  return callBridge('save_to_appwrite', collection, JSON.stringify(data));
}

export async function getRecentProjects(): Promise<any> {
  return callBridge('get_recent_projects');
}

// ── Signal Listeners ───────────────────────────────────────────────

export function onTerminalOutput(callback: (sessionId: string, data: string) => void): void {
  connectSignal('terminal_output', callback);
}

export function onTerminalExited(callback: (sessionId: string, exitCode: number) => void): void {
  connectSignal('terminal_exited', callback);
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

export function onGitUpdated(callback: (status: string) => void): void {
  connectSignal('git_updated', callback);
}

// ── Helpers ────────────────────────────────────────────────────────

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

function connectSignal(signalName: string, callback: Function): void {
  const signal = bridge?.[signalName];
  if (signal && typeof signal.connect === 'function') {
    signal.connect(callback);
    return;
  }

  pendingSignalListeners[signalName] = pendingSignalListeners[signalName] || [];
  pendingSignalListeners[signalName].push(callback);
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
  return new Proxy({}, {
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
