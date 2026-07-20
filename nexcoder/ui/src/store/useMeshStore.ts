import { create } from 'zustand';

export interface MeshUnit {
  id: string;
  title: string;
  role: string;
  description: string;
  dependencies: string[];
  completion_criteria: string[];
}

export interface MeshAgent {
  id: string;                // work-unit id doubles as agent id
  role: string;
  displayName: string;
  title: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'blocked' | 'cancelled';
  files: string[];
  turns: number;
  summary: string;
  checkpointId: string | null;
  streamingChars?: number;
  lastActivity?: string;
}

export interface MeshTimelineEntry {
  ts: number;
  agentId: string | null;    // null = orchestrator
  kind: 'info' | 'tool' | 'edit' | 'warn' | 'done' | 'fail';
  text: string;
}

export interface MeshPermission { id: string; command: string; agentId: string; }

export interface MeshConflict { file: string; units: string[]; }

interface MeshRunSummary {
  mesh_id: string; goal: string; status: string;
  elapsed_seconds: number; agents: number; mutated_files: number;
}

interface MeshState {
  active: boolean;
  meshId: string | null;
  goal: string;
  status: string;            // idle|planning|running|completed|…
  fallbackPlan: boolean;
  units: MeshUnit[];
  agents: Record<string, MeshAgent>;
  order: string[];           // execution order of agent ids
  timeline: MeshTimelineEntry[];
  permission: MeshPermission | null;
  conflicts: MeshConflict[];
  report: string;
  elapsedSeconds: number;
  startedAt: number | null;
  pastRuns: MeshRunSummary[];
  selectedAgentId: string | null;

  start: (goal: string) => void;
  handleEvent: (eventJson: string) => void;
  setPastRuns: (runs: MeshRunSummary[]) => void;
  selectAgent: (id: string | null) => void;
  reset: () => void;
}

const MAX_TIMELINE = 200;

function pushTimeline(timeline: MeshTimelineEntry[], entry: MeshTimelineEntry) {
  const next = [...timeline, entry];
  return next.length > MAX_TIMELINE ? next.slice(-MAX_TIMELINE) : next;
}

function describeActivity(inner: { type: string; payload: any }):
  { kind: MeshTimelineEntry['kind']; text: string } | null {
  const p = inner.payload || {};
  switch (inner.type) {
    case 'tool_started':
      return { kind: 'tool', text: `${p.tool}${p.args?.path ? ` ${p.args.path}` : p.args?.command ? ` ${String(p.args.command).slice(0, 60)}` : ''}` };
    case 'edit_applied':
      return { kind: 'edit', text: `${p.path} +${p.added ?? 0} −${p.removed ?? 0}` };
    case 'tool_result':
      return p.success ? null
        : { kind: 'warn', text: `${p.tool} failed: ${String(p.summary || '').slice(0, 90)}` };
    default:
      return null;
  }
}

export const useMeshStore = create<MeshState>((set) => ({
  active: false,
  meshId: null,
  goal: '',
  status: 'idle',
  fallbackPlan: false,
  units: [],
  agents: {},
  order: [],
  timeline: [],
  permission: null,
  conflicts: [],
  report: '',
  elapsedSeconds: 0,
  startedAt: null,
  pastRuns: [],
  selectedAgentId: null,

  start: (goal) => set({
    active: true, meshId: null, goal, status: 'planning',
    fallbackPlan: false, units: [], agents: {}, order: [], timeline: [{
      ts: Date.now(), agentId: null, kind: 'info',
      text: 'Orchestrator is decomposing the goal…',
    }],
    permission: null, conflicts: [], report: '', elapsedSeconds: 0,
    startedAt: Date.now(), selectedAgentId: null,
  }),

  handleEvent: (eventJson) => set((state) => {
    let event: { type: string; payload: any };
    try { event = JSON.parse(eventJson); } catch { return {}; }
    const { type, payload } = event;
    switch (type) {
      case 'mesh_started':
        return { meshId: payload.mesh_id, status: 'planning', active: true };
      case 'mesh_plan': {
        const units: MeshUnit[] = payload.units || [];
        const agents: Record<string, MeshAgent> = {};
        for (const unit of units) {
          agents[unit.id] = {
            id: unit.id, role: unit.role,
            displayName: unit.role.charAt(0).toUpperCase() + unit.role.slice(1),
            title: unit.title, status: 'queued', files: [], turns: 0,
            summary: '', checkpointId: null,
          };
        }
        return {
          units, agents, order: units.map((u) => u.id), status: 'running',
          fallbackPlan: !!payload.fallback_plan,
          timeline: pushTimeline(state.timeline, {
            ts: Date.now(), agentId: null, kind: 'info',
            text: `Plan ready: ${units.length} work unit(s)`
              + (payload.fallback_plan ? ' (default plan)' : ''),
          }),
        };
      }
      case 'agent_started': {
        const agent = state.agents[payload.agent_id];
        if (!agent) return {};
        return {
          agents: { ...state.agents, [payload.agent_id]: {
            ...agent, status: 'running',
            displayName: payload.display_name || agent.displayName,
          } },
          timeline: pushTimeline(state.timeline, {
            ts: Date.now(), agentId: payload.agent_id, kind: 'info',
            text: `${payload.display_name || payload.role} started: ${payload.title}`,
          }),
        };
      }
      case 'agent_activity': {
        const inner = payload.inner || {};
        const agent = state.agents[payload.agent_id];
        const updates: Partial<MeshState> = {};
        if (inner.type === 'permission_request') {
          updates.permission = {
            id: inner.payload?.id, command: inner.payload?.command || '',
            agentId: payload.agent_id,
          };
        } else if (inner.type === 'permission_resolved') {
          updates.permission = null;
        } else if (inner.type === 'tool_streaming' && agent) {
          updates.agents = { ...state.agents, [payload.agent_id]: {
            ...agent, streamingChars: inner.payload?.chars } };
          return updates;
        }
        const described = describeActivity(inner);
        if (described) {
          updates.timeline = pushTimeline(state.timeline, {
            ts: Date.now(), agentId: payload.agent_id,
            kind: described.kind, text: described.text,
          });
          if (agent) {
            updates.agents = { ...(updates.agents ?? state.agents),
              [payload.agent_id]: {
                ...((updates.agents ?? state.agents)[payload.agent_id]),
                lastActivity: described.text, streamingChars: undefined,
              } };
          }
        }
        return updates;
      }
      case 'agent_completed': {
        const agent = state.agents[payload.agent_id];
        if (!agent) return {};
        const status = (payload.status || 'completed') as MeshAgent['status'];
        return {
          agents: { ...state.agents, [payload.agent_id]: {
            ...agent, status,
            files: payload.files || [], turns: payload.turns || 0,
            summary: payload.summary || '',
            checkpointId: payload.checkpoint_id ?? null,
            streamingChars: undefined,
          } },
          timeline: pushTimeline(state.timeline, {
            ts: Date.now(), agentId: payload.agent_id,
            kind: status === 'completed' ? 'done' : 'fail',
            text: `${agent.displayName} ${status}`
              + (payload.files?.length ? ` — ${payload.files.length} file(s)` : ''),
          }),
        };
      }
      case 'mesh_conflict':
        return {
          conflicts: [...state.conflicts,
            { file: payload.file, units: payload.units || [] }],
          timeline: pushTimeline(state.timeline, {
            ts: Date.now(), agentId: null, kind: 'warn',
            text: `Conflict: ${payload.file} touched by ${(payload.units || []).join(', ')}`,
          }),
        };
      case 'mesh_completed':
        return {
          active: false, status: payload.status || 'completed',
          report: payload.report || '',
          elapsedSeconds: payload.elapsed_seconds || 0,
          permission: null,
          timeline: pushTimeline(state.timeline, {
            ts: Date.now(), agentId: null,
            kind: payload.status === 'completed' ? 'done' : 'warn',
            text: `Mesh ${payload.status}`,
          }),
        };
      case 'mesh_error':
        return {
          active: false, status: 'error',
          report: payload.error || 'Mesh failed.',
          permission: null,
        };
      default:
        return {};
    }
  }),

  setPastRuns: (runs) => set({ pastRuns: runs }),
  selectAgent: (id) => set({ selectedAgentId: id }),
  reset: () => set({
    active: false, meshId: null, goal: '', status: 'idle', units: [],
    agents: {}, order: [], timeline: [], permission: null, conflicts: [],
    report: '', elapsedSeconds: 0, startedAt: null, selectedAgentId: null,
  }),
}));
