import React from 'react';
import { CircleAlert, Crown, Network, Square, X } from 'lucide-react';
import { useMeshStore } from '../../store/useMeshStore';
import { meshCancel } from '../../services/bridge';
import { ROLE_META, AgentStatusChip } from '../Sidebar/MeshPanel';
import './MeshView.css';

/** Full-screen Mesh View: orchestrator, specialists, dependencies,
 *  progress, conflicts, and the final report. Static and truthful —
 *  every visual state maps to a real runtime event (roadmap §10). */
export default function MeshView({ onClose }: { onClose: () => void }) {
  const mesh = useMeshStore();
  const running = mesh.active;
  const selected = mesh.selectedAgentId
    ? mesh.agents[mesh.selectedAgentId] : null;
  const selectedUnit = selected
    ? mesh.units.find((u) => u.id === selected.id) : null;

  return (
    <div className="meshview-overlay">
      <div className="meshview-window">
        {/* Header */}
        <div className="meshview-header">
          <Network size={16} style={{ color: 'var(--accent-purple)' }} />
          <div className="meshview-goal" title={mesh.goal}>
            {mesh.goal || 'Agent Mesh'}
          </div>
          <span className={`mesh-chip mesh-chip-${running ? 'running' : (mesh.status || 'queued')}`}>
            {mesh.status || 'idle'}
          </span>
          <span className="meshview-meta">
            {mesh.order.length} agent{mesh.order.length === 1 ? '' : 's'}
          </span>
          {running && (
            <button className="btn btn-ghost" onClick={() => meshCancel()}>
              <Square size={12} /> Cancel
            </button>
          )}
          <button className="btn btn-ghost btn-icon" onClick={onClose} style={{ marginLeft: 'auto' }}>
            <X size={16} />
          </button>
        </div>

        <div className="meshview-body">
          {/* Graph column */}
          <div className="meshview-graph">
            {/* Orchestrator node */}
            <div className="meshview-orchestrator">
              <div className={`mesh-node mesh-node-orchestrator ${running ? 'running' : ''}`}>
                <Crown size={14} style={{ color: 'var(--accent-purple)' }} />
                <div>
                  <div className="mesh-node-name">Orchestrator</div>
                  <div className="mesh-node-sub">
                    {running ? 'coordinating' : (mesh.status || 'idle')}
                  </div>
                </div>
              </div>
            </div>

            {/* Stem + rail linking orchestrator to agents */}
            {mesh.order.length > 0 && <div className="meshview-stem" />}
            {mesh.order.length > 1 && <div className="meshview-rail" />}

            {/* Agent nodes in execution order */}
            <div className="meshview-agents">
              {mesh.order.map((id) => {
                const agent = mesh.agents[id];
                if (!agent) return null;
                const meta = ROLE_META[agent.role] || ROLE_META.explorer;
                const Icon = meta.icon;
                const unit = mesh.units.find((u) => u.id === id);
                const deps = unit?.dependencies || [];
                return (
                  <div key={id} className="meshview-agent-slot">
                    <div className="meshview-drop" />
                    <div
                      className={`mesh-node mesh-node-${agent.status} ${mesh.selectedAgentId === id ? 'selected' : ''}`}
                      onClick={() => mesh.selectAgent(mesh.selectedAgentId === id ? null : id)}
                      style={{ borderColor: agent.status === 'running' ? meta.color : undefined }}
                    >
                      <Icon size={14} style={{ color: meta.color }} />
                      <div className="mesh-node-info">
                        <div className="mesh-node-name">{agent.displayName}</div>
                        <div className="mesh-node-sub" title={agent.title}>{agent.title}</div>
                        <div className="mesh-node-foot">
                          <AgentStatusChip status={agent.status} />
                          {agent.files.length > 0 && (
                            <span className="mesh-node-files">{agent.files.length} file{agent.files.length > 1 ? 's' : ''}</span>
                          )}
                        </div>
                        {deps.length > 0 && (
                          <div className="mesh-node-deps">
                            waits for {deps.map((d) => mesh.agents[d]?.displayName || d).join(', ')}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              {mesh.order.length === 0 && (
                <div className="meshview-empty">
                  No mesh yet — start one from the Agent Mesh panel.
                </div>
              )}
            </div>

            {/* Conflicts */}
            {mesh.conflicts.length > 0 && (
              <div className="meshview-conflicts">
                {mesh.conflicts.map((c, i) => (
                  <div key={i} className="mesh-conflict-row">
                    <CircleAlert size={12} />
                    <span><code>{c.file}</code> touched by {c.units.join(' and ')}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Final report */}
            {!running && mesh.report && (
              <div className="meshview-report">
                <div className="mesh-section-title">Final report</div>
                <div className="mesh-report">{mesh.report}</div>
              </div>
            )}
          </div>

          {/* Inspector + timeline column */}
          <div className="meshview-side">
            <div className="mesh-section-title">Inspector</div>
            {selected ? (
              <div className="meshview-inspector">
                <div className="mesh-inspector-row">
                  <span>{selected.displayName}</span>
                  <AgentStatusChip status={selected.status} />
                </div>
                {selectedUnit && (
                  <div className="mesh-inspector-block">{selectedUnit.description}</div>
                )}
                {selectedUnit && selectedUnit.completion_criteria.length > 0 && (
                  <ul className="mesh-inspector-criteria">
                    {selectedUnit.completion_criteria.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                )}
                {selected.files.length > 0 && (
                  <div className="mesh-inspector-block">
                    {selected.files.map((f) => <code key={f} className="mesh-file">{f}</code>)}
                  </div>
                )}
                {selected.summary && (
                  <div className="mesh-inspector-block mesh-inspector-summary">{selected.summary}</div>
                )}
              </div>
            ) : (
              <div className="meshview-empty">Select an agent node.</div>
            )}

            <div className="mesh-section-title">Timeline</div>
            <div className="meshview-timeline">
              {mesh.timeline.slice(-80).map((entry, i) => (
                <div key={i} className={`mesh-timeline-entry mesh-tl-${entry.kind}`}>
                  <span className="mesh-tl-agent">
                    {entry.agentId ? (mesh.agents[entry.agentId]?.displayName || entry.agentId) : 'Mesh'}
                  </span>
                  <span className="mesh-tl-text">{entry.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
