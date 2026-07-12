import { create } from 'zustand';
import { TerminalSession } from '../types';

interface TerminalState {
  sessions: TerminalSession[];
  activeSessionId: string | null;
  addSession: (session: TerminalSession) => void;
  removeSession: (id: string) => void;
  setActiveSession: (id: string) => void;
  clearSessions: () => void;
}

export const useTerminalStore = create<TerminalState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  addSession: (session) => {
    const { sessions } = get();
    set({ sessions: [...sessions, session], activeSessionId: session.id });
  },
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
