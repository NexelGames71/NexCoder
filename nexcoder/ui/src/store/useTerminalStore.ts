import { create } from 'zustand';
import { TerminalSession } from '../types';

interface TerminalState {
  sessions: TerminalSession[];
  activeSessionId: string | null;
  addSession: (session: TerminalSession) => void;
  updateSession: (id: string, updates: Partial<TerminalSession>) => void;
  removeSession: (id: string) => void;
  setActiveSession: (id: string) => void;
  clearSessions: () => void;
}

export const useTerminalStore = create<TerminalState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  addSession: (session) => {
    const { sessions } = get();
    const existing = sessions.findIndex((item) => item.id === session.id);
    const nextSessions = existing >= 0
      ? sessions.map((item) => item.id === session.id ? { ...item, ...session } : item)
      : [...sessions, session];
    set({ sessions: nextSessions, activeSessionId: session.id });
  },
  updateSession: (id, updates) => set((state) => ({
    sessions: state.sessions.map((session) => (
      session.id === id ? { ...session, ...updates } : session
    )),
  })),
  removeSession: (id) => {
    const { sessions, activeSessionId } = get();
    const filtered = sessions.filter((s) => s.id !== id);
    let nextActive = activeSessionId;
    if (activeSessionId === id) {
      nextActive = filtered.length > 0 ? filtered[filtered.length - 1].id : null;
    }
    set({ sessions: filtered, activeSessionId: nextActive });
  },
  setActiveSession: (id) => set({ activeSessionId: id }),
  clearSessions: () => set({ sessions: [], activeSessionId: null }),
}));
