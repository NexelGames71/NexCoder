import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { AlertTriangle, Clock3, FileText, GitBranch } from 'lucide-react';
import {
  agentRunV2, answerPlanQuestions, approvePlanAndExecute, cancelPlan,
  requestPlanRevision, savePlanMarkdown,
} from '../../services/bridge';
import { useChatStore } from '../../store/useChatStore';
import { usePlanStore } from '../../store/usePlanStore';
import ClarificationPanel from './ClarificationPanel';
import ExecutionProgress from './ExecutionProgress';
import PlanReviewToolbar from './PlanReviewToolbar';
import './Plan.css';

export default function ImplementationPlanView({ planId }: { planId: string }) {
  const { activePlan: plan, answers, busy, error, setAnswer, setBusy, setError, setPlan } = usePlanStore();
  const [reviewing, setReviewing] = useState(false);
  const [review, setReview] = useState('');
  if (!plan || plan.id !== planId) {
    return <div className="plan-empty">Loading implementation plan…</div>;
  }

  const resumePlanning = async (prompt: string, nextPlan = plan) => {
    setBusy(true);
    useChatStore.getState().setStreaming(true);
    const result = await agentRunV2(prompt, '', 'plan', JSON.stringify({
      session_id: nextPlan.conversation_id || null,
      plan_context: { plan_id: nextPlan.id, revision: nextPlan.revision },
    }));
    if (!result?.success) {
      useChatStore.getState().setStreaming(false);
      setError(result?.error || 'Could not resume plan generation.');
    }
  };

  const submitAnswers = async () => {
    setBusy(true); setError('');
    const result = await answerPlanQuestions(plan.id, plan.revision, answers);
    if (!result?.success) return setError(result?.error || 'Could not submit answers.');
    setPlan(result.plan);
    await resumePlanning(result.resume_prompt, result.plan);
  };

  const submitReview = async () => {
    if (!review.trim()) return;
    setBusy(true); setError('');
    const result = await requestPlanRevision(plan.id, plan.revision, review);
    if (!result?.success) return setError(result?.error || 'Could not request changes.');
    setPlan(result.plan); setReviewing(false); setReview('');
    await resumePlanning(result.resume_prompt, result.plan);
  };

  const approve = async () => {
    setBusy(true); setError('');
    const result = await approvePlanAndExecute(plan.id, plan.revision);
    if (!result?.success) return setError(result?.error || 'Could not approve the plan.');
    setPlan(result.plan);
    useChatStore.getState().setStreaming(true);
    setBusy(false);
  };

  const save = async () => {
    setBusy(true); setError('');
    const result = await savePlanMarkdown(plan.id);
    if (result?.cancelled) { setBusy(false); return; }
    if (!result?.success) return setError(result?.error || 'Could not save the plan.');
    setPlan(result.plan); setBusy(false);
  };

  const cancel = async () => {
    setBusy(true); setError('');
    const result = await cancelPlan(plan.id);
    if (!result?.success) return setError(result?.error || 'Could not cancel the plan.');
    setPlan(result.plan); setBusy(false);
  };

  const headings = (plan.markdown_content.match(/^##\s+.+$/gm) || [])
    .map((heading) => heading.replace(/^##\s+/, ''));

  return (
    <div className="implementation-plan-view">
      <header className="plan-document-header">
        <div className="plan-document-title">
          <FileText size={17} />
          <div><h1>{plan.title}</h1><span>Implementation Plan</span></div>
        </div>
        <PlanReviewToolbar plan={plan} busy={busy} onApprove={approve}
          onReview={() => setReviewing(true)} onSave={save} onCancel={cancel} />
      </header>

      <div className="plan-document-layout">
        <aside className="plan-toc">
          <strong>On this page</strong>
          {headings.map((heading) => <span key={heading}>{heading}</span>)}
          <div className="plan-meta-card">
            <span><GitBranch size={12} /> Revision {plan.revision}</span>
            <span><Clock3 size={12} /> {new Date(plan.updated_at).toLocaleString()}</span>
          </div>
        </aside>
        <main className="plan-document-content">
          <div className={`plan-status-banner is-${plan.status}`}>
            <strong>{plan.status.replace(/_/g, ' ')}</strong>
            {plan.status === 'awaiting_approval' && <span>Review is required before any project mutation.</span>}
          </div>
          {error && <div className="plan-error"><AlertTriangle size={14} /> {error}</div>}
          {reviewing && (
            <section className="plan-review-box">
              <h2>Request changes</h2>
              <textarea className="input" rows={5} value={review}
                onChange={(event) => setReview(event.target.value)}
                placeholder="Describe what should change in the next revision…" />
              <div><button className="btn btn-ghost" onClick={() => setReviewing(false)}>Back</button>
                <button className="btn btn-primary" disabled={!review.trim() || busy} onClick={submitReview}>Submit review</button></div>
            </section>
          )}
          {plan.status === 'clarifying' ? (
            <ClarificationPanel questions={plan.questions} answers={answers}
              disabled={busy} onAnswer={setAnswer} onSubmit={submitAnswers} />
          ) : (
            <article className="plan-markdown"><ReactMarkdown>{plan.markdown_content}</ReactMarkdown></article>
          )}
          {['approved', 'executing', 'paused', 'completed', 'failed'].includes(plan.status)
            && <ExecutionProgress plan={plan} />}
        </main>
      </div>
    </div>
  );
}
