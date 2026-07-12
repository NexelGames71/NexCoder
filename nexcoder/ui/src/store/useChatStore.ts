import { create } from 'zustand';
import { ChatMessage, AgentMode, AgentTask, AgentTaskPlan, AgentTaskStep, DiffHunk, FinalAnswer, Skill, TaskType, SessionMetadata } from '../types';

interface ChatState {
  messages: ChatMessage[];
  activeMode: AgentMode;
  activeSkill: string | null;
  skills: Skill[];
  isStreaming: boolean;
  tasks: AgentTask[];
  pendingDiffs: DiffHunk[];
  activeDiffId: string | null;
  scanStepsByTask: Record<string, string[]>;
  sessions: SessionMetadata[];
  activeSessionId: string | null;
  addMessage: (message: ChatMessage) => void;
  updateLastMessage: (content: string) => void;
  appendToLastMessage: (chunk: string) => void;
  setActiveMode: (mode: AgentMode) => void;
  setActiveSkill: (skillId: string | null) => void;
  setSkills: (skills: Skill[]) => void;
  setStreaming: (isStreaming: boolean) => void;
  addTask: (task: AgentTask) => void;
  updateTaskStatus: (taskId: string, status: AgentTask['status'], message: string) => void;
  addTaskStep: (taskId: string, step: string, status?: Exclude<AgentTask['status'], 'pending'>) => void;
  addTaskStepItem: (taskId: string, step: AgentTaskStep) => void;
  addTaskChangedFile: (taskId: string, path: string, action: DiffHunk['action']) => void;
  setTaskFinalAnswer: (taskId: string, finalAnswer: FinalAnswer | null, taskType?: TaskType | string) => void;
  setTaskPlan: (taskId: string, plan: AgentTaskPlan | null) => void;
  addPendingDiff: (diff: DiffHunk) => void;
  setActiveDiffId: (diffId: string | null) => void;
  removePendingDiff: (diffId: string) => void;
  clearPendingDiffs: () => void;
  addScanStep: (taskId: string, step: string) => void;
  clearScanSteps: (taskId?: string) => void;
  clearChat: () => void;
  setMessages: (messages: ChatMessage[]) => void;
  setSessions: (sessions: SessionMetadata[]) => void;
  setActiveSessionId: (sessionId: string | null) => void;
  upsertSession: (session: SessionMetadata) => void;
  removeSession: (sessionId: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  activeMode: 'ask',
  activeSkill: null,
  skills: [],
  isStreaming: false,
  tasks: [],
  pendingDiffs: [],
  activeDiffId: null,
  scanStepsByTask: {},
  sessions: [],
  activeSessionId: null,
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  updateLastMessage: (content) => set((state) => {
    const updated = [...state.messages];
    if (updated.length > 0) {
      const last = updated[updated.length - 1];
      if (last.role === 'assistant') {
        updated[updated.length - 1] = { ...last, content };
      }
    }
    return { messages: updated };
  }),
  appendToLastMessage: (chunk) => set((state) => {
    const updated = [...state.messages];
    if (updated.length > 0) {
      const last = updated[updated.length - 1];
      if (last.role === 'assistant') {
        updated[updated.length - 1] = { ...last, content: last.content + chunk };
      }
    }
    return { messages: updated };
  }),
  setActiveMode: (mode) => set({ activeMode: mode }),
  setActiveSkill: (skillId) => set({ activeSkill: skillId }),
  setSkills: (skills) => set({ skills }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  addTask: (task) => set((state) => ({
    tasks: [...state.tasks, { ...task, steps: task.steps || [], changedFiles: task.changedFiles || [] }],
  })),
  updateTaskStatus: (taskId, status, message) => set((state) => ({
    tasks: state.tasks.map((t) => {
      if (t.id !== taskId) return t;
      const validation = message.toLowerCase().includes('verification') || message.toLowerCase().includes('running verification')
        ? message
        : t.validation;
      return { ...t, status, message, validation };
    }),
  })),
  addTaskStep: (taskId, step, status = 'running') => set((state) => ({
    tasks: state.tasks.map((task) => {
      if (task.id !== taskId) return task;
      const steps = task.steps || [];
      const lastStep = steps[steps.length - 1];
      if (lastStep?.label === step) {
        return {
          ...task,
          steps: steps.map((item, index) => index === steps.length - 1 ? { ...item, status: status === 'error' ? 'failed' : status === 'awaiting_approval' ? 'approval_required' : status === 'complete' ? 'completed' : 'running' } : item),
        };
      }
      const completedSteps = steps.map((item, index) => (
        index === steps.length - 1 && item.status === 'running'
          ? { ...item, status: 'completed' as const, completed_at: new Date().toISOString() }
          : item
      ));
      const mappedStatus = status === 'error'
        ? 'failed'
        : status === 'awaiting_approval'
          ? 'approval_required'
          : status === 'complete'
            ? 'completed'
            : 'running';
      return {
        ...task,
        steps: [
          ...completedSteps,
          {
            id: `${taskId}-${Date.now()}-${steps.length}`,
            type: 'system',
            label: step,
            status: mappedStatus,
            started_at: new Date().toISOString(),
            completed_at: mappedStatus === 'running' ? null : new Date().toISOString(),
            result_summary: null,
            error: mappedStatus === 'failed' ? step : null,
            timestamp: Date.now(),
          },
        ],
      };
    }),
  })),
  addTaskStepItem: (taskId, step) => set((state) => ({
    tasks: state.tasks.map((task) => {
      if (task.id !== taskId) return task;
      const steps = task.steps || [];
      const nextStep = { ...step, timestamp: step.timestamp || Date.now() };
      const taskStatus = step.status === 'failed' || step.status === 'blocked'
        ? 'error'
        : step.status === 'approval_required'
          ? 'awaiting_approval'
          : task.status === 'complete'
            ? 'complete'
            : 'running';
      const message = step.result_summary || step.label || task.message;
      const existingIndex = steps.findIndex((item) => item.id === step.id);
      if (existingIndex >= 0) {
        return {
          ...task,
          status: taskStatus,
          message,
          steps: steps.map((item, index) => index === existingIndex ? { ...item, ...nextStep } : item),
        };
      }
      return { ...task, status: taskStatus, message, steps: [...steps, nextStep] };
    }),
  })),
  addTaskChangedFile: (taskId, path, action) => set((state) => ({
    tasks: state.tasks.map((task) => {
      if (task.id !== taskId) return task;
      const changedFiles = task.changedFiles || [];
      if (changedFiles.some((file) => file.path === path && file.action === action)) return task;
      return { ...task, changedFiles: [...changedFiles, { path, action }] };
    }),
  })),
  setTaskFinalAnswer: (taskId, finalAnswer, taskType) => set((state) => ({
    tasks: state.tasks.map((task) => {
      if (task.id !== taskId) return task;
      return { ...task, finalAnswer, taskType: taskType || task.taskType };
    }),
  })),
  setTaskPlan: (taskId, plan) => set((state) => ({
    tasks: state.tasks.map((task) => task.id === taskId ? { ...task, plan } : task),
  })),
  addPendingDiff: (diff) => set((state) => {
    const replacedIds = new Set(diff.replaces_diff_ids || []);
    const retained = state.pendingDiffs.filter((item) => (
      !replacedIds.has(item.id)
      && !(item.file === diff.file && item.id !== diff.id)
    ));
    const activeWasReplaced = !!state.activeDiffId && replacedIds.has(state.activeDiffId);
    return {
      pendingDiffs: [...retained, diff],
      activeDiffId: activeWasReplaced ? diff.id : (state.activeDiffId || diff.id),
    };
  }),
  setActiveDiffId: (diffId) => set({ activeDiffId: diffId }),
  removePendingDiff: (diffId) => set((state) => ({
    pendingDiffs: state.pendingDiffs.filter((d) => d.id !== diffId),
    activeDiffId: state.activeDiffId === diffId
      ? state.pendingDiffs.find((d) => d.id !== diffId)?.id || null
      : state.activeDiffId,
  })),
  clearPendingDiffs: () => set({ pendingDiffs: [], activeDiffId: null }),
  addScanStep: (taskId, step) => set((state) => {
    const existing = state.scanStepsByTask[taskId] || [];
    return {
      scanStepsByTask: {
        ...state.scanStepsByTask,
        [taskId]: [...existing.slice(-19), step],
      },
    };
  }),
  clearScanSteps: (taskId) => set((state) => {
    if (!taskId) return { scanStepsByTask: {} };
    const next = { ...state.scanStepsByTask };
    delete next[taskId];
    return { scanStepsByTask: next };
  }),
  clearChat: () => set({ messages: [], tasks: [], pendingDiffs: [], activeDiffId: null, scanStepsByTask: {}, activeSessionId: null }),
  setMessages: (messages) => set({ messages }),
  setSessions: (sessions) => set({ sessions }),
  setActiveSessionId: (sessionId) => set({ activeSessionId: sessionId }),
  upsertSession: (session) => set((state) => {
    const exists = state.sessions.some((item) => item.session_id === session.session_id);
    const sessions = exists
      ? state.sessions.map((item) => item.session_id === session.session_id ? session : item)
      : [session, ...state.sessions];
    return { sessions: sessions.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))) };
  }),
  removeSession: (sessionId) => set((state) => ({
    sessions: state.sessions.filter((session) => session.session_id !== sessionId),
    activeSessionId: state.activeSessionId === sessionId ? null : state.activeSessionId,
  })),
}));
