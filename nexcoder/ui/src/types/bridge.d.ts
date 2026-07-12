/** Type declarations for the QWebChannel Python bridge. */

declare namespace Bridge {
  // Filesystem
  function open_folder_dialog(): string;
  function open_project(path: string): string;
  function read_file(path: string): string;
  function write_file(path: string, content: string): string;
  function save_file_as(path: string, content: string): string;
  function delete_file(path: string): string;
  function rename_file(oldPath: string, newPath: string): string;
  function create_directory(path: string): string;
  function create_file(path: string, content?: string): string;
  function get_file_tree(root: string): string;
  function search_files(query: string, root: string): string;

  // Terminal
  function spawn_terminal(cwd: string): string;
  function write_terminal(sessionId: string, data: string): void;
  function resize_terminal(sessionId: string, cols: number, rows: number): void;
  function kill_terminal(sessionId: string): void;

  // Git
  function git_status(root: string): string;
  function git_diff(root: string): string;
  function git_stage(root: string, filesJson: string): string;
  function git_commit(root: string, message: string): string;
  function git_branch(root: string): string;
  function git_log(root: string, count: number): string;

  // Agent
  function agent_ask(prompt: string, contextJson: string): string;
  function agent_edit(prompt: string, contextJson: string): string;
  function agent_run(prompt: string, contextJson: string): string;
  function agent_scan(contextJson: string): string;
  function agent_debug(prompt: string, contextJson: string): string;
  function agent_review(prompt: string, contextJson: string): string;
  function agent_approve_diff(diffId: string): string;
  function agent_approve_patchset(diffIdsJson: string): string;
  function agent_reject_diff(diffId: string): string;
  function update_ai_settings(endpoint: string, model: string): string;
  function list_sessions(projectPath?: string): string;
  function load_session(projectPath: string, sessionId: string): string;
  function delete_session(projectPath: string, sessionId: string): string;
  function archive_session(projectPath: string, sessionId: string, archivedJson: string): string;
  function create_session(projectPath: string, title?: string, mode?: string): string;
  function get_skills(): string;
  function get_skill_body(skillId: string): string;

  // Appwrite
  function appwrite_login(email: string, password: string): string;
  function appwrite_register(email: string, password: string, name: string): string;
  function appwrite_logout(): string;
  function save_to_appwrite(collection: string, dataJson: string): string;
  function get_recent_projects(): string;

  // Signals (Python → JS)
  const file_tree_updated: { connect: (cb: (path: string) => void) => void };
  const terminal_output: { connect: (cb: (sid: string, data: string) => void) => void };
  const terminal_exited: { connect: (cb: (sid: string, code: number) => void) => void };
  const agent_stream: { connect: (cb: (chunk: string) => void) => void };
  const agent_status: { connect: (cb: (status: string) => void) => void };
  const agent_diff: { connect: (cb: (diff: string) => void) => void };
  const agent_complete: { connect: (cb: (result: string) => void) => void };
  const git_updated: { connect: (cb: (status: string) => void) => void };
  const project_opened: { connect: (cb: (info: string) => void) => void };
}
