import React from 'react';
import { Check, Clipboard, Download, MessageSquareText, X } from 'lucide-react';
import { ImplementationPlan } from '../../types';

interface Props {
  plan: ImplementationPlan;
  busy: boolean;
  onApprove: () => void;
  onReview: () => void;
  onSave: () => void;
  onCancel: () => void;
}

export default function PlanReviewToolbar({ plan, busy, onApprove, onReview, onSave, onCancel }: Props) {
  const reviewable = plan.status === 'awaiting_approval';
  const copy = async () => navigator.clipboard?.writeText(plan.markdown_content);
  return (
    <div className="plan-review-toolbar">
      <button className="btn btn-ghost" onClick={copy} title="Copy plan"><Clipboard size={13} /> Copy</button>
      <button className="btn btn-ghost" onClick={onSave} disabled={busy}><Download size={13} /> Save Markdown</button>
      <button className="btn btn-ghost" onClick={onReview} disabled={!reviewable || busy}>
        <MessageSquareText size={13} /> Request changes
      </button>
      <button className="btn btn-ghost plan-cancel" onClick={onCancel}
        disabled={['completed', 'cancelled'].includes(plan.status) || busy}><X size={13} /> Cancel</button>
      <button className="btn btn-primary" onClick={onApprove} disabled={!reviewable || busy}>
        <Check size={13} /> Approve and Proceed
      </button>
    </div>
  );
}
