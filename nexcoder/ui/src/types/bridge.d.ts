/** Type declarations for the QWebChannel Python bridge. */

declare namespace Bridge {
  // Filesystem
  function open_folder_dialog(): string;
  function open_file_dialog(): string;
  function select_folder_dialog(title: string): string;
  function open_project(path: string): string;
  function clone_repository(repositoryUrl: string, destinationParent: string, directoryName: string): string;
  function read_file(path: string): string;
  function write_file(path: string, content: string): string;
  function save_file_as(path: string, content: string): string;
  function delete_file(path: string): string;
  function delete_artifact_file(path: string): string;
  function rename_file(oldPath: string, newPath: string): string;
  function create_directory(path: string): string;
  function create_file(path: string, content?: string): string;
  function get_file_tree(root: string): string;
  function search_files(query: string, root: string): string;
  function app_state_get(): string;
  function app_state_update(patchJson: string): string;
  function web_auth_session_status(): string;
  function web_auth_clear(): string;
  function app_shell_set_stage(stage: string): string;

  // Terminal
  function spawn_terminal(cwd: string): string;
  function terminal_snapshot(sessionId: string): string;
  function write_terminal(sessionId: string, data: string): string;
  function resize_terminal(sessionId: string, cols: number, rows: number): string;
  function kill_terminal(sessionId: string): string;

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
  function agent_run_v2(prompt: string, skillId: string, mode: string, contextJson: string): string;
  function agent_cancel_v2(): string;
  function agent_steer_v2(prompt: string, attachmentsJson: string, clientPromptId: string): string;
  function agent_permission_response(requestId: string, decision: string): string;
  function agent_approve_diff(diffId: string): string;
  function agent_approve_patchset(diffIdsJson: string): string;
  function agent_reject_diff(diffId: string): string;
  function agent_rewind_to_prompt(sessionId: string, targetJson: string): string;
  function plan_get(planId: string): string;
  function plan_list(conversationId: string): string;
  function plan_answer(planId: string, revision: number, answersJson: string): string;
  function plan_request_revision(planId: string, revision: number, review: string): string;
  function plan_approve_and_execute(planId: string, revision: number): string;
  function plan_cancel(planId: string): string;
  function plan_save_markdown(planId: string, suggestedPath: string): string;
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
  function web_auth_start(): string;
  function save_to_appwrite(collection: string, dataJson: string): string;
  function get_recent_projects(): string;

  // Signals (Python → JS)
  const file_tree_updated: { connect: (cb: (path: string) => void) => void };
  const terminal_output: {
    connect: (cb: (sid: string, data: string, sequence: number) => void) => void;
    disconnect: (cb: (sid: string, data: string, sequence: number) => void) => void;
  };
  const terminal_exited: { connect: (cb: (sid: string, code: number) => void) => void };
  const agent_stream: { connect: (cb: (chunk: string) => void) => void };
  const agent_status: { connect: (cb: (status: string) => void) => void };
  const agent_diff: { connect: (cb: (diff: string) => void) => void };
  const agent_complete: { connect: (cb: (result: string) => void) => void };
  const agent_event: { connect: (cb: (event: string) => void) => void };
  const plan_updated: { connect: (cb: (plan: string) => void) => void };
  const git_updated: { connect: (cb: (status: string) => void) => void };
  const project_opened: { connect: (cb: (info: string) => void) => void };
  const clone_completed: { connect: (cb: (info: string) => void) => void };
  const web_auth_completed: { connect: (cb: (info: string) => void) => void };
}
