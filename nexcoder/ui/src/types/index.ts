/** Core types used across the NexCoder UI. */
export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  extension?: string;
  size?: number;
  children?: FileNode[];
}

export interface OpenFile {
  path: string;
  name: string;
  content: string;
  language: string;
  isDirty: boolean;
  cursorLine?: number;
  cursorColumn?: number;
  kind?: 'file' | 'implementation_plan' | 'artifact';
  resourceId?: string;
}

export interface EditorGroup {
  id: string;
  openFiles: OpenFile[];
  activeFilePath: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  mode?: AgentMode;
  isStreaming?: boolean;
  attachments?: PromptAttachment[];
  /** Stable UI identifier persisted with the prompt for safe rewind/resend. */
  clientPromptId?: string;
  /** Position in the persisted session transcript. */
  sessionMessageIndex?: number;
  /** True when this prompt was injected into an already-running agent turn. */
  isSteering?: boolean;
}

export interface ImageAttachment {
  kind?: 'image';
  id: string;
  name: string;
  mimeType: string;
  size: number;
  /** Present for a new/live prompt; omitted from persisted chat history. */
  dataUrl?: string;
}

export interface TextAttachment {
  kind: 'text';
  id: string;
  name: string;
  mimeType: 'text/plain';
  size: number;
  path: string;
}

export type PromptAttachment = ImageAttachment | TextAttachment;

export interface SessionMetadata {
  session_id: string;
  title: string;
  mode: string;
  project_path: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  status: 'active' | 'complete' | 'cancelled' | 'error' | string;
  tags: string[];
  archived?: boolean;
  plan_id?: string;
}

export type PlanStatus =
  | 'idle' | 'clarifying' | 'drafting' | 'awaiting_approval'
  | 'revision_requested' | 'approved' | 'executing' | 'paused'
  | 'completed' | 'cancelled' | 'failed';

export interface ClarificationOption {
  id: string;
  label: string;
  description?: string;
}

export interface ClarificationQuestion {
  id: string;
  title: string;
  kind: 'single' | 'multiple' | 'boolean' | 'text' | 'number' | 'file' | 'confirm';
  explanation?: string;
  options: ClarificationOption[];
  required: boolean;
  answer?: unknown;
}

export interface PlanTask {
  id: string;
  title: string;
  description?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'blocked' | 'skipped' | 'failed';
}

export interface PlanPhase {
  id: string;
  title: string;
  description?: string;
  status: PlanTask['status'];
  tasks: PlanTask[];
}

export interface ImplementationPlan {
  id: string;
  conversation_id: string;
  task_id?: string;
  title: string;
  objective: string;
  original_request: string;
  project_name?: string;
  status: PlanStatus;
  revision: number;
  questions: ClarificationQuestion[];
  proposed_architecture?: string[];
  phases: PlanPhase[];
  files: Array<{ path: string; operation: string; description: string; confirmed: boolean }>;
  risks: Array<{ title: string; mitigation: string; severity: string }>;
  validation_steps: Array<{ description: string; command?: string; status: string }>;
  markdown_content: string;
  revisions: Array<{ revision: number; summary: string; created_at: string }>;
  deviations: Array<{ id: string; classification: string; description: string; proposed_amendment?: string }>;
  approved_at?: string;
  saved_markdown_path?: string;
  created_at: string;
  updated_at: string;
}

export interface StoredSessionMessage {
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
  created_at: string;
  metadata?: Record<string, any>;
}

export type AgentMode = string;

export type TaskType =
  | 'question'
  | 'scan'
  | 'implement'
  | 'edit'
  | 'debug'
  | 'review';

export interface FinalAnswerEvidence {
  /** A short bullet the loop derived from a tool observation. */
  text: string;
  /** Optional file path the evidence came from. */
  source?: string | null;
}

export interface FinalAnswer {
  type: 'final_answer';
  title: string;
  summary: string;
  evidence: string[];
  files_used: string[];
  next_steps: string[];
}

export interface AgentArtifact {
  id: string;
  runId: string;
  projectPath: string;
  type:
    | 'run_summary'
    | 'patch_summary'
    | 'validation_report'
    | 'problem_fix_report'
    | 'review_report'
    | 'failure_report'
    | 'scan_report'
    | 'implementation_plan';
  title: string;
  summary: string;
  content: string;
  createdAt: number;
  updatedAt: number;
  status: 'draft' | 'generated' | 'saved';
  files: string[];
  savedPath?: string;
  sourcePrompt?: string;
}

export interface Skill {
  id: string; // Changed from AgentMode to string to accommodate dynamic skills
  label: string;
  icon: string;
  description: string;
  shortcut: string;
}

export interface AgentTask {
  id: string;
  mode: AgentMode;
  taskType?: TaskType | string;
  status: 'pending' | 'running' | 'complete' | 'error' | 'awaiting_approval';
  message: string;
  timestamp: number;
  title?: string;
  steps?: AgentTaskStep[];
  changedFiles?: Array<{ path: string; action: DiffHunk['action'] }>;
  validation?: string;
  patches?: DiffHunk[];
  finalAnswer?: FinalAnswer | null;
  plan?: AgentTaskPlan | null;
}

export interface AgentTaskPlan {
  id: string;
  session_id?: string | null;
  task_type: string;
  title: string;
  created_at: string;
  updated_at: string;
  items: AgentTaskPlanItem[];
}

export interface AgentTaskPlanItem {
  id: string;
  title: string;
  phase: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped' | 'blocked' | 'approval_required';
  detail?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export interface AgentTaskStep {
  id: string;
  type: 'tool_call' | 'system' | 'patch' | 'validation';
  tool?: string;
  label: string;
  target?: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'blocked' | 'approval_required';
  started_at?: string;
  completed_at?: string | null;
  result_summary?: string | null;
  error?: string | null;
  timestamp?: number;
}

export interface DiffHunk {
  id: string;
  file: string;
  action: 'modify' | 'create' | 'delete' | 'move' | 'mkdir' | 'rmdir';
  operation?: 'move' | 'create_directory' | 'remove_directory' | string;
  source?: string;
  supersedes?: string[];
  replaces_diff_ids?: string[];
  original_content?: string;
  content?: string;
  diff?: string;
  diff_display?: string;
  language?: string;
  safety?: {
    safe: boolean;
    requires_approval: boolean;
    reasons: string[];
    risk_score: number;
  };
}

export interface TerminalSession {
  id: string;
  cwd: string;
  isActive?: boolean;
  name?: string;
  shell?: string;
  status: 'starting' | 'running' | 'closing' | 'exited' | 'error';
  exitCode?: number | null;
  error?: string;
}

export interface Project {
  path: string;
  name: string;
  framework: string;
  language: string;
  packageManager?: string;
  buildCommand?: string;
  hasGit: boolean;
}

export interface SearchResult {
  file: string;
  line: number;
  content: string;
  column: number;
}

export interface GitStatus {
  isRepo: boolean;
  branch: string;
  changed: Array<{ path: string; change_type: string }>;
  staged: Array<{ path: string; change_type: string }>;
  untracked: string[];
  isDirty: boolean;
}

export interface GitCommit {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  date: string;
  files_changed: number;
}
