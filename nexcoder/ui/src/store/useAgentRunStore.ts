import { create } from 'zustand';

export interface AgentTodo { id: number; content: string; status: 'pending' | 'in_progress' | 'completed'; }
export interface AgentStep { tool: string; args?: Record<string, unknown>; success?: boolean; summary?: string; done: boolean; }
export interface PermissionReq { id: string; tool: string; command: string; }
export interface AgentEventMsg { type: string; payload: Record<string, any>; ts?: number; }

interface AgentRunState {
  runActive: boolean;
  steps: AgentStep[];
  todos: AgentTodo[];
  permission: PermissionReq | null;
  checkpointId: string | null;
  mutatedFiles: string[];
  streamText: string;
  finalText: string;
  status: string;
  start: () => void;
  handleEvent: (event: AgentEventMsg) => void;
  reset: () => void;
}

export const useAgentRunStore = create<AgentRunState>((set) => ({
  runActive: false, steps: [], todos: [], permission: null,
  checkpointId: null, mutatedFiles: [], streamText: '', finalText: '', status: '',
  start: () => set({
    runActive: true, steps: [], todos: [], permission: null,
    checkpointId: null, mutatedFiles: [], streamText: '', finalText: '', status: 'running',
  }),
  reset: () => set({
    runActive: false, steps: [], todos: [], permission: null,
    checkpointId: null, mutatedFiles: [], streamText: '', finalText: '', status: '',
  }),
  handleEvent: (event) => set((state) => {
    const { type, payload } = event;
    switch (type) {
      case 'run_started': return { runActive: true, status: 'running' };
      case 'text_delta': return { streamText: state.streamText + (payload.text ?? '') };
      case 'tool_started':
        return { steps: [...state.steps, { tool: payload.tool, args: payload.args, done: false }], streamText: '' };
      case 'tool_result': {
        const steps = [...state.steps];
        for (let i = steps.length - 1; i >= 0; i--) {
          if (!steps[i].done && steps[i].tool === payload.tool) {
            steps[i] = { ...steps[i], done: true, success: payload.success, summary: payload.summary };
            break;
          }
        }
        return { steps };
      }
      case 'todo_updated': return { todos: payload.todos ?? [] };
      case 'permission_request':
        return { permission: { id: payload.id, tool: payload.tool, command: payload.command } };
      case 'permission_resolved': return { permission: null };
      case 'checkpoint_created': return { checkpointId: payload.checkpoint_id };
      case 'edit_applied':
        return state.mutatedFiles.includes(payload.path)
          ? {} : { mutatedFiles: [...state.mutatedFiles, payload.path] };
      case 'run_completed':
        return {
          runActive: false, status: payload.status, finalText: payload.final_text ?? '',
          streamText: '',  // the completed card owns the final text now
          checkpointId: payload.checkpoint_id ?? state.checkpointId,
          mutatedFiles: payload.mutated_files ?? state.mutatedFiles,
        };
      case 'run_error': return { runActive: false, status: 'error', finalText: payload.error ?? '' };
      default: return {};
    }
  }),
}));
