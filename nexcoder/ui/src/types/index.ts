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
}

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
  type:
    | 'final_answer'
    | 'patch_proposal'
    | 'approval_request'
    | 'validation_report'
    | 'failure_report'
    | 'scan_report';
  title?: string;
  summary?: string;
  data?: Record<string, any>;
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
  isActive: boolean;
  name?: string;
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
