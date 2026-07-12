import { create } from 'zustand';

export interface AgentTodo { id: number; content: string; status: 'pending' | 'in_progress' | 'completed'; }
export interface PermissionReq { id: string; tool: string; command: string; }
export interface AgentEventMsg { type: string; payload: Record<string, any>; ts?: number; }

// Ordered transcript, Codex-style: prose and tool actions interleave in
// the order they happened instead of living in separate buckets.
export type TranscriptItem =
  | { kind: 'text'; text: string }
  | { kind: 'step'; tool: string; args?: Record<string, unknown>; done: boolean;
      success?: boolean; summary?: string;
      output?: string[];   // streamed command output lines
      diff?: string };     // unified diff for file edits

const MAX_OUTPUT_LINES = 500;

export interface AgentRun {
  runActive: boolean;
  transcript: TranscriptItem[];
  todos: AgentTodo[];
  permission: PermissionReq | null;
  checkpointId: string | null;
  mutatedFiles: string[];
  finalText: string;
  status: string;
}

const emptyRun = (): AgentRun => ({
  runActive: true, transcript: [], todos: [], permission: null,
  checkpointId: null, mutatedFiles: [], finalText: '', status: 'running',
});

interface AgentRunState {
  // One run per user message id; old runs stay visible in the chat flow.
  runs: Record<string, AgentRun>;
  activeRunId: string | null;
  start: (runId: string) => void;
  handleEvent: (event: AgentEventMsg) => void;
  reset: () => void;
}

function applyEvent(run: AgentRun, event: AgentEventMsg): AgentRun {
  const { type, payload } = event;
  switch (type) {
    case 'run_started': return { ...run, runActive: true, status: 'running' };
    case 'text_delta': {
      const transcript = [...run.transcript];
      const last = transcript[transcript.length - 1];
      if (last && last.kind === 'text') {
        transcript[transcript.length - 1] = { kind: 'text', text: last.text + (payload.text ?? '') };
      } else {
        transcript.push({ kind: 'text', text: payload.text ?? '' });
      }
      return { ...run, transcript };
    }
    case 'tool_started':
      return { ...run, transcript: [...run.transcript,
               { kind: 'step', tool: payload.tool, args: payload.args, done: false }] };
    case 'tool_result': {
      const transcript = [...run.transcript];
      for (let i = transcript.length - 1; i >= 0; i--) {
        const item = transcript[i];
        if (item.kind === 'step' && !item.done && item.tool === payload.tool) {
          transcript[i] = { ...item, done: true, success: payload.success, summary: payload.summary };
          break;
        }
      }
      return { ...run, transcript };
    }
    case 'command_output': {
      const transcript = [...run.transcript];
      for (let i = transcript.length - 1; i >= 0; i--) {
        const item = transcript[i];
        if (item.kind === 'step' && item.tool === 'run_command' && !item.done) {
          const output = [...(item.output ?? [])];
          if (output.length < MAX_OUTPUT_LINES) output.push(String(payload.line ?? ''));
          transcript[i] = { ...item, output };
          break;
        }
      }
      return { ...run, transcript };
    }
    case 'todo_updated': return { ...run, todos: payload.todos ?? [] };
    case 'permission_request':
      return { ...run, permission: { id: payload.id, tool: payload.tool, command: payload.command } };
    case 'permission_resolved': return { ...run, permission: null };
    case 'checkpoint_created': return { ...run, checkpointId: payload.checkpoint_id };
    case 'edit_applied': {
      const transcript = [...run.transcript];
      for (let i = transcript.length - 1; i >= 0; i--) {
        const item = transcript[i];
        if (item.kind === 'step' && !item.done
            && (item.tool === 'edit_file' || item.tool === 'write_file')) {
          transcript[i] = { ...item, diff: String(payload.diff ?? '') };
          break;
        }
      }
      const mutatedFiles = run.mutatedFiles.includes(payload.path)
        ? run.mutatedFiles : [...run.mutatedFiles, payload.path];
      return { ...run, transcript, mutatedFiles };
    }
    case 'run_completed': {
      const transcript = [...run.transcript];
      const last = transcript[transcript.length - 1];
      if (last && last.kind === 'text' && (payload.final_text ?? '').startsWith(last.text.slice(0, 40))) {
        transcript.pop();
      }
      return {
        ...run, runActive: false, status: payload.status,
        finalText: payload.final_text ?? '', transcript,
        checkpointId: payload.checkpoint_id ?? run.checkpointId,
        mutatedFiles: payload.mutated_files ?? run.mutatedFiles,
      };
    }
    case 'run_error':
      return { ...run, runActive: false, status: 'error', finalText: payload.error ?? '' };
    default: return run;
  }
}

export const useAgentRunStore = create<AgentRunState>((set) => ({
  runs: {},
  activeRunId: null,
  start: (runId) => set((state) => ({
    runs: { ...state.runs, [runId]: emptyRun() },
    activeRunId: runId,
  })),
  handleEvent: (event) => set((state) => {
    const id = state.activeRunId;
    if (!id || !state.runs[id]) return {};
    return { runs: { ...state.runs, [id]: applyEvent(state.runs[id], event) } };
  }),
  reset: () => set({ runs: {}, activeRunId: null }),
}));
