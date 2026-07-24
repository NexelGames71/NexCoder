import React, { useEffect, useState } from 'react';
import { ClarificationQuestion } from '../../types';

interface Props {
  questions: ClarificationQuestion[];
  answers: Record<string, unknown>;
  disabled?: boolean;
  onAnswer: (id: string, value: unknown) => void;
  onSubmit: () => void;
}

export default function ClarificationPanel({
  questions, answers, disabled = false, onAnswer, onSubmit,
}: Props) {
  const [questionIndex, setQuestionIndex] = useState(0);
  useEffect(() => setQuestionIndex(0), [questions]);
  const complete = questions.every((question) => {
    if (!question.required) return true;
    const answer = answers[question.id];
    if (answer === undefined || answer === null || answer === '') return false;
    return !Array.isArray(answer) || answer.length > 0;
  });

  return (
    <section className="plan-clarification">
      <div className="plan-section-heading">
        <h2>Clarification required</h2>
        <span>{questions.length} question{questions.length === 1 ? '' : 's'}</span>
      </div>
      <p>Answer only the decisions the repository could not determine safely.</p>
      {questions.slice(questionIndex, questionIndex + 1).map((question) => (
        <fieldset key={question.id} className="plan-question" disabled={disabled}>
          <legend>{questionIndex + 1}. {question.title}</legend>
          {question.explanation && <p>{question.explanation}</p>}
          {question.kind === 'multiple' ? question.options.map((option) => {
            const selected = Array.isArray(answers[question.id])
              ? (answers[question.id] as unknown[]).includes(option.id) : false;
            return (
              <label key={option.id} className="plan-option">
                <input type="checkbox" checked={selected} onChange={(event) => {
                  const current = Array.isArray(answers[question.id])
                    ? [...answers[question.id] as unknown[]] : [];
                  onAnswer(question.id, event.target.checked
                    ? [...current, option.id]
                    : current.filter((value) => value !== option.id));
                }} />
                <span><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</span>
              </label>
            );
          }) : ['single', 'boolean', 'confirm'].includes(question.kind) ? (
            <div className="plan-options">
              {(question.options.length ? question.options : [
                { id: 'yes', label: 'Yes' }, { id: 'no', label: 'No' },
              ]).map((option) => (
                <label key={option.id} className="plan-option">
                  <input type="radio" name={question.id}
                    checked={answers[question.id] === option.id}
                    onChange={() => onAnswer(question.id, option.id)} />
                  <span><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</span>
                </label>
              ))}
            </div>
          ) : (
            <input className="input plan-answer-input"
              type={question.kind === 'number' ? 'number' : 'text'}
              value={String(answers[question.id] ?? '')}
              onChange={(event) => onAnswer(question.id,
                question.kind === 'number' ? Number(event.target.value) : event.target.value)} />
          )}
        </fieldset>
      ))}
      <div className="plan-question-navigation">
        <button className="btn btn-ghost" disabled={disabled || questionIndex === 0}
          onClick={() => setQuestionIndex((index) => Math.max(0, index - 1))}>
          Previous
        </button>
        <span>{questionIndex + 1} of {questions.length}</span>
        {questionIndex < questions.length - 1 ? (
          <button className="btn" disabled={disabled}
            onClick={() => setQuestionIndex((index) => Math.min(questions.length - 1, index + 1))}>
            Next
          </button>
        ) : (
          <button className="btn btn-primary" disabled={!complete || disabled} onClick={onSubmit}>
            Submit answers
          </button>
        )}
      </div>
    </section>
  );
}
