import { create } from 'zustand';
import { ImplementationPlan } from '../types';

interface PlanState {
  activePlan: ImplementationPlan | null;
  answers: Record<string, unknown>;
  busy: boolean;
  error: string;
  setPlan: (plan: ImplementationPlan | null) => void;
  setAnswer: (questionId: string, value: unknown) => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string) => void;
  reset: () => void;
}

export const usePlanStore = create<PlanState>((set) => ({
  activePlan: null,
  answers: {},
  busy: false,
  error: '',
  setPlan: (activePlan) => set({
    activePlan,
    answers: Object.fromEntries((activePlan?.questions || [])
      .filter((question) => question.answer !== undefined && question.answer !== null)
      .map((question) => [question.id, question.answer])),
    error: '',
    busy: false,
  }),
  setAnswer: (questionId, value) => set((state) => ({
    answers: { ...state.answers, [questionId]: value },
  })),
  setBusy: (busy) => set({ busy }),
  setError: (error) => set({ error, busy: false }),
  reset: () => set({ activePlan: null, answers: {}, busy: false, error: '' }),
}));
