import React, { useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  ListChecks,
  Sparkles,
} from 'lucide-react';
import { FinalAnswer } from '../../types';

interface FinalAnswerCardProps {
  answer: FinalAnswer;
  taskType?: string;
}

/**
 * FinalAnswerCard — renders a structured final_answer object emitted by
 * the agent runner. The card has three collapsible sections so the chat
 * pane stays scannable: a summary, a list of files used, and a list of
 * follow-up steps.
 */
export default function FinalAnswerCard({ answer, taskType }: FinalAnswerCardProps) {
  const [expanded, setExpanded] = useState(true);
  const hasFiles = (answer.files_used?.length ?? 0) > 0;
  const hasNextSteps = (answer.next_steps?.length ?? 0) > 0;
  const hasEvidence = (answer.evidence?.length ?? 0) > 0;

  return (
    <div className="final-answer-card" data-task-type={taskType || ''}>
      <button
        type="button"
        className="final-answer-header"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="final-answer-header-left">
          <div className="final-answer-icon">
            <Sparkles size={12} />
          </div>
          <div className="final-answer-title-block">
            <div className="final-answer-eyebrow">
              {taskType ? taskType.toUpperCase() : 'ANSWER'}
            </div>
            <div className="final-answer-title">
              {answer.title || 'Answer'}
            </div>
          </div>
        </div>
        <div className="final-answer-header-right">
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </div>
      </button>

      {expanded && (
        <div className="final-answer-body">
          {answer.summary ? (
            <div className="final-answer-summary">{answer.summary}</div>
          ) : (
            <div className="final-answer-summary final-answer-summary-empty">
              No summary was produced.
            </div>
          )}

          {hasEvidence && (
            <section className="final-answer-section">
              <div className="final-answer-section-label">
                <FileText size={11} /> Evidence
              </div>
              <ul className="final-answer-list">
                {answer.evidence.map((item, i) => (
                  <li key={i} className="final-answer-list-item">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {hasFiles && (
            <section className="final-answer-section">
              <div className="final-answer-section-label">
                <FileCode2 size={11} /> Files used
              </div>
              <div className="final-answer-files">
                {answer.files_used.map((path) => (
                  <span key={path} className="final-answer-file-chip" title={path}>
                    {path.split(/[\\/]/).pop() || path}
                  </span>
                ))}
              </div>
            </section>
          )}

          {hasNextSteps && (
            <section className="final-answer-section">
              <div className="final-answer-section-label">
                <ListChecks size={11} /> Suggested next steps
              </div>
              <ul className="final-answer-list">
                {answer.next_steps.map((step, i) => (
                  <li key={i} className="final-answer-list-item">
                    <CheckCircle2 size={10} className="final-answer-list-icon" />
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
