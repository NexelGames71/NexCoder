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

interface AgentRunState {
  runActive: boolean;
  transcript: TranscriptItem[];
  todos: AgentTodo[];
  permission: PermissionReq | null;
  checkpointId: string | null;
  mutatedFiles: string[];
  finalText: string;
  status: string;
  start: () => void;
  handleEvent: (event: AgentEventMsg) => void;
  reset: () => void;
}

export const useAgentRunStore = create<AgentRunState>((set) => ({
  runActive: false, transcript: [], todos: [], permission: null,
  checkpointId: null, mutatedFiles: [], finalText: '', status: '',
  start: () => set({
    runActive: true, transcript: [], todos: [], permission: null,
    checkpointId: null, mutatedFiles: [], finalText: '', status: 'running',
  }),
  reset: () => set({
    runActive: false, transcript: [], todos: [], permission: null,
    checkpointId: null, mutatedFiles: [], finalText: '', status: '',
  }),
  handleEvent: (event) => set((state) => {
    const { type, payload } = event;
    switch (type) {
      case 'run_started': return { runActive: true, status: 'running' };
      case 'text_delta': {
        const transcript = [...state.transcript];
        const last = transcript[transcript.length - 1];
        if (last && last.kind === 'text') {
          transcript[transcript.length - 1] = { kind: 'text', text: last.text + (payload.text ?? '') };
        } else {
          transcript.push({ kind: 'text', text: payload.text ?? '' });
        }
        return { transcript };
      }
      case 'tool_started':
        return { transcript: [...state.transcript,
                 { kind: 'step', tool: payload.tool, args: payload.args, done: false }] };
      case 'tool_result': {
        const transcript = [...state.transcript];
        for (let i = transcript.length - 1; i >= 0; i--) {
          const item = transcript[i];
          if (item.kind === 'step' && !item.done && item.tool === payload.tool) {
            transcript[i] = { ...item, done: true, success: payload.success, summary: payload.summary };
            break;
          }
        }
        return { transcript };
      }
      case 'command_output': {
        const transcript = [...state.transcript];
        for (let i = transcript.length - 1; i >= 0; i--) {
          const item = transcript[i];
          if (item.kind === 'step' && item.tool === 'run_command' && !item.done) {
            const output = [...(item.output ?? [])];
            if (output.length < MAX_OUTPUT_LINES) output.push(String(payload.line ?? ''));
            transcript[i] = { ...item, output };
            break;
          }
        }
        return { transcript };
      }
      case 'todo_updated': return { todos: payload.todos ?? [] };
      case 'permission_request':
        return { permission: { id: payload.id, tool: payload.tool, command: payload.command } };
      case 'permission_resolved': return { permission: null };
      case 'checkpoint_created': return { checkpointId: payload.checkpoint_id };
      case 'edit_applied': {
        // Attach the diff to the in-flight edit/write step for expansion.
        const transcript = [...state.transcript];
        for (let i = transcript.length - 1; i >= 0; i--) {
          const item = transcript[i];
          if (item.kind === 'step' && !item.done
              && (item.tool === 'edit_file' || item.tool === 'write_file')) {
            transcript[i] = { ...item, diff: String(payload.diff ?? '') };
            break;
          }
        }
        const mutatedFiles = state.mutatedFiles.includes(payload.path)
          ? state.mutatedFiles : [...state.mutatedFiles, payload.path];
        return { transcript, mutatedFiles };
      }
      case 'run_completed': {
        // The final text already streamed into the transcript; drop the
        // trailing text item so it isn't shown twice.
        const transcript = [...state.transcript];
        const last = transcript[transcript.length - 1];
        if (last && last.kind === 'text' && (payload.final_text ?? '').startsWith(last.text.slice(0, 40))) {
          transcript.pop();
        }
        return {
          runActive: false, status: payload.status, finalText: payload.final_text ?? '',
          transcript,
          checkpointId: payload.checkpoint_id ?? state.checkpointId,
          mutatedFiles: payload.mutated_files ?? state.mutatedFiles,
        };
      }
      case 'run_error': return { runActive: false, status: 'error', finalText: payload.error ?? '' };
      default: return {};
    }
  }),
}));
