import React from 'react';
import { ImplementationPlan } from '../../types';

export default function ExecutionProgress({ plan }: { plan: ImplementationPlan }) {
  const tasks = plan.phases.flatMap((phase) => phase.tasks);
  const done = tasks.filter((task) => ['completed', 'skipped'].includes(task.status)).length;
  const progress = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
  return (
    <section className="plan-progress">
      <div className="plan-section-heading"><h2>Implementation progress</h2><span>{progress}%</span></div>
      <div className="plan-progress-track"><span style={{ width: `${progress}%` }} /></div>
      {plan.phases.map((phase) => (
        <div key={phase.id} className={`plan-progress-phase is-${phase.status}`}>
          <span className="plan-progress-dot" />
          <div><strong>{phase.title}</strong><small>{phase.status.replace('_', ' ')}</small></div>
        </div>
      ))}
    </section>
  );
}
