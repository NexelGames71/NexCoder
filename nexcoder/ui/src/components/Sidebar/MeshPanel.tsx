import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot, ChevronDown, ChevronUp, CircleAlert, Expand, Eye, FlaskConical,
  Hammer, Network, ShieldCheck, Square,
} from 'lucide-react';
import { useMeshStore, MeshAgent } from '../../store/useMeshStore';
import { useProjectStore } from '../../store/useProjectStore';
import {
  agentPermissionResponse, meshCancel, meshList, meshRun, onMeshEvent,
} from '../../services/bridge';
import MeshView from '../Mesh/MeshView';
import './MeshPanel.css';

export const ROLE_META: Record<string, { icon: any; color: string }> = {
  explorer: { icon: Eye, color: 'var(--accent-blue, #74b9ff)' },
  implementation: { icon: Hammer, color: 'var(--accent-green, #00b894)' },
  test: { icon: FlaskConical, color: 'var(--accent-yellow, #fdcb6e)' },
  review: { icon: ShieldCheck, color: 'var(--accent-cyan, #81ecec)' },
};

export function AgentStatusChip({ status }: { status: MeshAgent['status'] }) {
  return <span className={`mesh-chip mesh-chip-${status}`}>{status}</span>;
}

function useElapsed(startedAt: number | null, active: boolean, finalSeconds: number) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  if (!startedAt) return '0:00';
  const seconds = active ? Math.floor((now - startedAt) / 1000)
    : Math.floor(finalSeconds);
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, '0');
  return `${m}:${s}`;
}

let meshEventsWired = false;

export default function MeshPanel() {
  const mesh = useMeshStore();
  const { projectPath } = useProjectStore();
  const [goalInput, setGoalInput] = useState('');
  const [goalExpanded, setGoalExpanded] = useState(false);
  const [showView, setShowView] = useState(false);
  const timelineRef = useRef<HTMLDivElement>(null);
  const elapsed = useElapsed(mesh.startedAt, mesh.active, mesh.elapsedSeconds);

  // Wire the mesh event stream once for the app lifetime.
  useEffect(() => {
    if (meshEventsWired) return;
    meshEventsWired = true;
    onMeshEvent((eventJson) => useMeshStore.getState().handleEvent(eventJson));
  }, []);

  useEffect(() => {
    if (projectPath) {
      meshList().then((r) => {
        if (r?.success) mesh.setPastRuns(r.runs || []);
      }).catch(() => {});
    }
  }, [projectPath, mesh.status]);

  useEffect(() => {
    timelineRef.current?.scrollTo({ top: timelineRef.current.scrollHeight });
  }, [mesh.timeline.length]);

  const selected = mesh.selectedAgentId
    ? mesh.agents[mesh.selectedAgentId] : null;
  const selectedUnit = useMemo(
    () => mesh.units.find((u) => u.id === mesh.selectedAgentId) || null,
    [mesh.units, mesh.selectedAgentId]);

  const handleStart = async () => {
    const goal = goalInput.trim();
    if (!goal) return;
    mesh.start(goal);
    setGoalExpanded(false);
    setGoalInput('');
    const res = await meshRun(goal).catch((e) => ({ success: false, error: String(e) }));
    if (res && res.success === false) {
      useMeshStore.getState().handleEvent(JSON.stringify({
        type: 'mesh_error', payload: { error: res.error || 'Could not start.' },
      }));
    }
  };

  const idle = mesh.status === 'idle';
  const finished = !mesh.active && !idle;

  return (
    <div className="sidebar-panel mesh-panel">
      <div className="sidebar-header">
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Network size={14} style={{ color: 'var(--accent-purple)' }} /> Agent Mesh
        </span>
        {(mesh.active || finished) && (
          <button className="btn btn-ghost btn-icon" title="Open Mesh View"
            onClick={() => setShowView(true)}>
            <Expand size={13} />
          </button>
        )}
      </div>

      {idle && (
        <div className="mesh-start">
          <p className="mesh-hint">
            One goal, multiple coordinated specialists, one verified result.
            The orchestrator decomposes your goal into bounded work units for
            explorer, implementation, test, and review agents.
          </p>
          <textarea
            className="input mesh-goal-input"
            rows={6}
            placeholder={projectPath
              ? 'Describe a development goal…'
              : 'Open a project first'}
            disabled={!projectPath}
            value={goalInput}
            onChange={(e) => setGoalInput(e.target.value)}
          />
          <div className="mesh-goal-input-meta">
            <span>Long prompts are supported and kept intact.</span>
            <span>{goalInput.length.toLocaleString()} characters</span>
          </div>
          <button className="btn btn-primary w-full" disabled={!projectPath || !goalInput.trim()}
            onClick={handleStart}>
            Start Mesh
          </button>

          {mesh.pastRuns.length > 0 && (
            <div className="mesh-history">
              <div className="mesh-section-title">Previous meshes</div>
              {mesh.pastRuns.map((run) => (
                <div key={run.mesh_id} className="mesh-history-item">
                  <div className="mesh-history-goal">{run.goal}</div>
                  <div className="mesh-history-meta">
                    <span className={`mesh-chip mesh-chip-${run.status === 'completed' ? 'completed' : 'failed'}`}>
                      {run.status}
                    </span>
                    <span>{run.agents} agents</span>
                    <span>{run.mutated_files} files</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!idle && (
        <div className="mesh-run">
          <section className={`mesh-goal-card ${goalExpanded ? 'expanded' : ''}`}>
            <div className="mesh-goal-card-heading">
              <span>Goal</span>
              <span>{mesh.goal.length.toLocaleString()} characters</span>
            </div>
            <div className="mesh-goal-text">{mesh.goal}</div>
            <button
              type="button"
              className="mesh-goal-toggle"
              aria-expanded={goalExpanded}
              onClick={() => setGoalExpanded((expanded) => !expanded)}
            >
              {goalExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {goalExpanded ? 'Collapse prompt' : 'View full prompt'}
            </button>
          </section>
          <div className="mesh-status-row">
            <span className={`mesh-chip mesh-chip-${mesh.active ? 'running' : (mesh.status === 'completed' ? 'completed' : 'failed')}`}>
              {mesh.status}
            </span>
            <span>{mesh.order.length || '…'} agents</span>
            <span>{elapsed}</span>
            {mesh.active && (
              <button className="btn btn-ghost btn-icon mesh-cancel" title="Cancel mesh"
                onClick={() => meshCancel()}>
                <Square size={12} />
              </button>
            )}
          </div>

          {/* Orchestrator row */}
          <div className="mesh-agent mesh-orchestrator">
            <Bot size={14} style={{ color: 'var(--accent-purple)' }} />
            <div className="mesh-agent-main">
              <div className="mesh-agent-name">Orchestrator</div>
              <div className="mesh-agent-work">
                {mesh.status === 'planning' ? 'decomposing the goal…'
                  : mesh.active ? 'supervising' : 'done'}
              </div>
            </div>
          </div>

          {/* Agent list */}
          {mesh.order.map((id) => {
            const agent = mesh.agents[id];
            if (!agent) return null;
            const meta = ROLE_META[agent.role] || ROLE_META.implementation;
            const Icon = meta.icon;
            return (
              <div key={id}
                className={`mesh-agent ${mesh.selectedAgentId === id ? 'selected' : ''}`}
                onClick={() => mesh.selectAgent(mesh.selectedAgentId === id ? null : id)}>
                <Icon size={14} style={{ color: meta.color }} />
                <div className="mesh-agent-main">
                  <div className="mesh-agent-name">
                    {agent.displayName}
                    {agent.files.length > 0 && (
                      <span className="mesh-agent-files">{agent.files.length} file(s)</span>
                    )}
                  </div>
                  <div className="mesh-agent-work">
                    {agent.status === 'running'
                      ? (agent.streamingChars
                        ? `writing… ${(agent.streamingChars / 1000).toFixed(1)}k`
                        : agent.lastActivity || agent.title)
                      : agent.title}
                  </div>
                </div>
                <AgentStatusChip status={agent.status} />
              </div>
            );
          })}

          {/* Inspector for the selected agent */}
          {selected && (
            <div className="mesh-inspector">
              <div className="mesh-section-title">{selected.displayName} — {selected.status}</div>
              {selectedUnit && (
                <>
                  <div className="mesh-inspector-block">{selectedUnit.description}</div>
                  {selectedUnit.completion_criteria.length > 0 && (
                    <ul className="mesh-criteria">
                      {selectedUnit.completion_criteria.map((c, i) => <li key={i}>{c}</li>)}
                    </ul>
                  )}
                  {selectedUnit.dependencies.length > 0 && (
                    <div className="mesh-inspector-meta">
                      waits for: {selectedUnit.dependencies.join(', ')}
                    </div>
                  )}
                </>
              )}
              {selected.files.length > 0 && (
                <div className="mesh-inspector-meta">
                  changed: {selected.files.join(', ')}
                </div>
              )}
              {selected.summary && (
                <div className="mesh-inspector-block mesh-inspector-summary">
                  {selected.summary}
                </div>
              )}
            </div>
          )}

          {/* Permission request from a mesh agent */}
          {mesh.permission && (
            <div className="mesh-permission">
              <div className="mesh-section-title">
                <CircleAlert size={12} /> {mesh.agents[mesh.permission.agentId]?.displayName || 'Agent'} requests:
              </div>
              <code>{mesh.permission.command}</code>
              <div className="mesh-permission-actions">
                <button className="btn" onClick={() => agentPermissionResponse(mesh.permission!.id, 'allow')}>Allow</button>
                <button className="btn" onClick={() => agentPermissionResponse(mesh.permission!.id, 'allow_always')}>Always</button>
                <button className="btn" onClick={() => agentPermissionResponse(mesh.permission!.id, 'deny')}>Deny</button>
              </div>
            </div>
          )}

          {/* Conflicts */}
          {mesh.conflicts.length > 0 && (
            <div className="mesh-conflicts">
              {mesh.conflicts.map((c, i) => (
                <div key={i} className="mesh-conflict-row">
                  <CircleAlert size={12} />
                  <span><code>{c.file}</code> touched by {c.units.join(' and ')}</span>
                </div>
              ))}
            </div>
          )}

          {/* Timeline */}
          <div className="mesh-section-title">Timeline</div>
          <div className="mesh-timeline" ref={timelineRef}>
            {mesh.timeline.map((entry, i) => (
              <div key={i} className={`mesh-timeline-entry mesh-tl-${entry.kind}`}>
                <span className="mesh-tl-agent">
                  {entry.agentId ? (mesh.agents[entry.agentId]?.displayName || entry.agentId) : 'Mesh'}
                </span>
                <span className="mesh-tl-text">{entry.text}</span>
              </div>
            ))}
          </div>

          {/* Final report */}
          {finished && mesh.report && (
            <>
              <div className="mesh-section-title">Final report</div>
              <div className="mesh-report">{mesh.report}</div>
              <button className="btn w-full" onClick={() => mesh.reset()}>
                New mesh
              </button>
            </>
          )}
        </div>
      )}

      {showView && <MeshView onClose={() => setShowView(false)} />}
    </div>
  );
}
