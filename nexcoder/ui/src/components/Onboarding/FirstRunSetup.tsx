import React, { useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  Code2,
  Gauge,
  LayoutPanelTop,
  LockKeyhole,
  MonitorCog,
  Palette,
  Rocket,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-react';
import type { AgentSettings } from '../../store/useAgentStore';
import type { EditorSettings } from '../../store/useEditorSettingsStore';
import './FirstRunSetup.css';

export type OnboardingProfile = {
  discoverySource: string;
  usageIntent: string;
  role: string;
  teamSize: string;
  collectedAt: string;
};

export type SetupPatch = {
  editor: Partial<EditorSettings>;
  agent: Partial<AgentSettings>;
  profile: OnboardingProfile;
};

interface FirstRunSetupProps {
  userName?: string;
  onComplete: (patch: SetupPatch) => void;
}

const layoutOptions = [
  { id: 'balanced', title: 'Balanced', description: 'Default spacing, readable editor text, agent panel on the right.', icon: LayoutPanelTop,
    editor: { uiScale: 100, fontSize: 14, minimap: false, wordWrap: 'on', sidebarPosition: 'left', aiPanelPosition: 'right' } },
  { id: 'focus', title: 'Focus', description: 'Larger code text and fewer visual extras for long editing sessions.', icon: Code2,
    editor: { uiScale: 100, fontSize: 15, minimap: false, wordWrap: 'on', stickyScroll: true } },
  { id: 'compact', title: 'Compact', description: 'Denser panels, smaller text, and minimap on for large projects.', icon: MonitorCog,
    editor: { uiScale: 90, fontSize: 13, minimap: true, wordWrap: 'off' } },
] as const;

const themeOptions = [
  { id: 'nexcoder', title: 'NexCoder', description: 'Premium dark with purple, blue, and green accents.', swatches: ['#0e0e14', '#6c5ce7', '#74b9ff', '#00b894'] },
  { id: 'dark-plus', title: 'Dark Plus', description: 'Familiar dark editor palette for VS Code users.', swatches: ['#1e1e1e', '#007acc', '#dcdcaa', '#c586c0'] },
  { id: 'github-dark', title: 'GitHub Dark', description: 'High-contrast dark with GitHub-style code colors.', swatches: ['#0d1117', '#58a6ff', '#3fb950', '#f85149'] },
  { id: 'light', title: 'Light', description: 'Bright workspace for daylight and presentations.', swatches: ['#ffffff', '#0969da', '#1a7f37', '#cf222e'] },
] as const;

const agentOptions = [
  { id: 'guided', title: 'Guided Agent', description: 'Inspect, edit, and run approved commands with review checkpoints.', icon: ShieldCheck,
    agent: { autonomy: 'ask', fullAuto: false, toolAccess: 'full', memoryEnabled: true } },
  { id: 'readOnly', title: 'Read Only', description: 'Inspect project context and explain fixes before any change.', icon: LockKeyhole,
    agent: { autonomy: 'read_only', fullAuto: false, toolAccess: 'read_only', memoryEnabled: true } },
  { id: 'trusted', title: 'Trusted Workspace', description: 'Handle low-risk commands, still asks before sensitive actions.', icon: Bot,
    agent: { autonomy: 'risky_only', fullAuto: false, toolAccess: 'full', memoryEnabled: true } },
] as const;

const modelOptions = [
  { id: 'balanced', title: 'Balanced', description: 'Production NexCoder defaults for everyday agent tasks.', icon: Sparkles,
    agent: { defaultAgentMode: 'agent', contextWindow: 32768, maxOutputTokens: 6144, temperature: 0.2 } },
  { id: 'fast', title: 'Fast', description: 'Shorter responses and a smaller context for quick edits.', icon: Gauge,
    agent: { defaultAgentMode: 'edit', contextWindow: 16384, maxOutputTokens: 4096, temperature: 0.15 } },
  { id: 'deep', title: 'Deep Work', description: 'Larger context and longer responses for multi-file work.', icon: Bot,
    agent: { defaultAgentMode: 'agent', contextWindow: 65536, maxOutputTokens: 8192, temperature: 0.2 } },
] as const;

const discoveryOptions = [
  { id: 'search', label: 'Search' }, { id: 'social', label: 'Social media' },
  { id: 'youtube', label: 'YouTube' }, { id: 'github', label: 'GitHub' },
  { id: 'friend', label: 'Friend or coworker' }, { id: 'other', label: 'Other' },
] as const;
const usageIntentOptions = [
  { id: 'personal', label: 'Personal' }, { id: 'work', label: 'Work' },
  { id: 'both', label: 'Both' }, { id: 'school', label: 'School' },
] as const;
const roleOptions = [
  { id: 'software_engineer', label: 'Software engineer' }, { id: 'student', label: 'Student' },
  { id: 'founder', label: 'Founder' }, { id: 'product_designer', label: 'Product or design' },
  { id: 'data_ai', label: 'Data or AI' }, { id: 'other', label: 'Other' },
] as const;
const teamSizeOptions = [
  { id: 'solo', label: 'Just me' }, { id: 'small', label: '2–10' },
  { id: 'mid', label: '11–50' }, { id: 'large', label: '51+' },
] as const;

const STEPS = [
  { id: 'profile', label: 'Profile', icon: UserRound, hint: 'Tell us a little about you' },
  { id: 'workspace', label: 'Workspace', icon: Palette, hint: 'Layout & theme' },
  { id: 'agent', label: 'Agent', icon: ShieldCheck, hint: 'Access & model' },
  { id: 'launch', label: 'Launch', icon: Rocket, hint: 'Review & open' },
] as const;

function OptionCard({ selected, title, description, icon: Icon, onClick }: {
  selected: boolean; title: string; description: string;
  icon: React.ComponentType<{ size?: number }>; onClick: () => void;
}) {
  return (
    <button type="button" className={`frs-card ${selected ? 'selected' : ''}`} onClick={onClick}>
      <span className="frs-card-icon"><Icon size={18} /></span>
      <span className="frs-card-copy">
        <span className="frs-card-title">{title}</span>
        <span className="frs-card-desc">{description}</span>
      </span>
      <span className={`frs-card-check ${selected ? 'on' : ''}`}>{selected && <Check size={13} />}</span>
    </button>
  );
}

export default function FirstRunSetup({ userName, onComplete }: FirstRunSetupProps) {
  const [step, setStep] = useState(0);
  const [discoverySource, setDiscoverySource] = useState('search');
  const [usageIntent, setUsageIntent] = useState('both');
  const [role, setRole] = useState('software_engineer');
  const [teamSize, setTeamSize] = useState('solo');
  const [layout, setLayout] = useState<'balanced' | 'focus' | 'compact'>('balanced');
  const [theme, setTheme] = useState<'nexcoder' | 'dark-plus' | 'github-dark' | 'light'>('nexcoder');
  const [agent, setAgent] = useState<'guided' | 'readOnly' | 'trusted'>('guided');
  const [model, setModel] = useState<'balanced' | 'fast' | 'deep'>('balanced');

  const selectedPatch = useMemo<SetupPatch>(() => ({
    editor: { ...layoutOptions.find((o) => o.id === layout)?.editor, theme },
    agent: {
      ...agentOptions.find((o) => o.id === agent)?.agent,
      ...modelOptions.find((o) => o.id === model)?.agent,
    },
    profile: { discoverySource, usageIntent, role, teamSize, collectedAt: new Date().toISOString() },
  }), [agent, discoverySource, layout, model, role, teamSize, theme, usageIntent]);

  const isLast = step === STEPS.length - 1;
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));
  const launch = () => onComplete({
    ...selectedPatch,
    profile: { ...selectedPatch.profile, collectedAt: new Date().toISOString() },
  });

  const themeMeta = themeOptions.find((o) => o.id === theme)!;
  const label = (list: readonly { id: string; label: string }[], id: string) =>
    list.find((o) => o.id === id)?.label ?? id;

  return (
    <main className="frs-screen">
      <div className="frs-window">
        {/* Branded rail */}
        <aside className="frs-rail">
          <div className="frs-brand">
            <div className="frs-logo">N</div>
            <span>NexCoder</span>
          </div>
          <div className="frs-rail-hero">
            <h2>Welcome{userName ? `, ${userName.split(' ')[0]}` : ''}.</h2>
            <p>A couple of quick choices and your workspace is ready. Everything here can be changed later in Settings.</p>
          </div>
          <ol className="frs-steps">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              const state = i < step ? 'done' : i === step ? 'active' : 'todo';
              return (
                <li key={s.id} className={`frs-step frs-step-${state}`}>
                  <span className="frs-step-dot">{state === 'done' ? <Check size={13} /> : <Icon size={14} />}</span>
                  <span className="frs-step-copy">
                    <span className="frs-step-label">{s.label}</span>
                    <span className="frs-step-hint">{s.hint}</span>
                  </span>
                </li>
              );
            })}
          </ol>
          <div className="frs-rail-glow" aria-hidden="true" />
        </aside>

        {/* Content */}
        <section className="frs-content">
          <div className="frs-progress"><span style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} /></div>

          <div className="frs-body">
            {step === 0 && (
              <div className="frs-step-panel">
                <h1>Tell us about you</h1>
                <p className="frs-sub">Helps tailor defaults and recommendations. Saved locally in NexCoder app data.</p>
                <div className="frs-field-grid">
                  <label className="frs-field">
                    <span>How did you hear about NexCoder?</span>
                    <select value={discoverySource} onChange={(e) => setDiscoverySource(e.target.value)}>
                      {discoveryOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                  </label>
                  <label className="frs-field">
                    <span>What will you use it for?</span>
                    <select value={usageIntent} onChange={(e) => setUsageIntent(e.target.value)}>
                      {usageIntentOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                  </label>
                  <label className="frs-field">
                    <span>What is your role?</span>
                    <select value={role} onChange={(e) => setRole(e.target.value)}>
                      {roleOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                  </label>
                  <label className="frs-field">
                    <span>Team size</span>
                    <select value={teamSize} onChange={(e) => setTeamSize(e.target.value)}>
                      {teamSizeOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                    </select>
                  </label>
                </div>
              </div>
            )}

            {step === 1 && (
              <div className="frs-step-panel">
                <h1>Shape your workspace</h1>
                <p className="frs-sub">Pick a layout density and a color theme.</p>
                <div className="frs-group-label"><LayoutPanelTop size={14} /> Layout</div>
                <div className="frs-cards">
                  {layoutOptions.map((o) => (
                    <OptionCard key={o.id} selected={layout === o.id} title={o.title} description={o.description} icon={o.icon} onClick={() => setLayout(o.id)} />
                  ))}
                </div>
                <div className="frs-group-label" style={{ marginTop: 18 }}><Palette size={14} /> Theme</div>
                <div className="frs-theme-grid">
                  {themeOptions.map((o) => (
                    <button key={o.id} type="button" className={`frs-theme ${theme === o.id ? 'selected' : ''}`} onClick={() => setTheme(o.id)}>
                      <span className="frs-theme-swatches">{o.swatches.map((c) => <span key={c} style={{ background: c }} />)}</span>
                      <span className="frs-theme-title">{o.title}</span>
                      {theme === o.id && <span className="frs-theme-check"><Check size={12} /></span>}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="frs-step-panel">
                <h1>How the agent works</h1>
                <p className="frs-sub">Set how much the agent can do on its own, and its default model profile.</p>
                <div className="frs-group-label"><ShieldCheck size={14} /> Agent access</div>
                <div className="frs-cards">
                  {agentOptions.map((o) => (
                    <OptionCard key={o.id} selected={agent === o.id} title={o.title} description={o.description} icon={o.icon} onClick={() => setAgent(o.id)} />
                  ))}
                </div>
                <div className="frs-group-label" style={{ marginTop: 18 }}><Sparkles size={14} /> Model profile</div>
                <div className="frs-cards">
                  {modelOptions.map((o) => (
                    <OptionCard key={o.id} selected={model === o.id} title={o.title} description={o.description} icon={o.icon} onClick={() => setModel(o.id)} />
                  ))}
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="frs-step-panel">
                <h1>You're all set</h1>
                <p className="frs-sub">Review your choices, then open the workspace.</p>
                <div className="frs-review">
                  {[
                    { k: 'Layout', v: layoutOptions.find((o) => o.id === layout)!.title, icon: LayoutPanelTop },
                    { k: 'Theme', v: themeMeta.title, icon: Palette, swatches: themeMeta.swatches },
                    { k: 'Agent access', v: agentOptions.find((o) => o.id === agent)!.title, icon: ShieldCheck },
                    { k: 'Model profile', v: modelOptions.find((o) => o.id === model)!.title, icon: Sparkles },
                    { k: 'Role', v: label(roleOptions, role), icon: UserRound },
                    { k: 'Using it for', v: label(usageIntentOptions, usageIntent), icon: Bot },
                  ].map((row) => {
                    const Icon = row.icon;
                    return (
                      <div key={row.k} className="frs-review-row">
                        <span className="frs-review-key"><Icon size={14} /> {row.k}</span>
                        <span className="frs-review-val">
                          {row.swatches && (
                            <span className="frs-review-swatches">{row.swatches.map((c) => <span key={c} style={{ background: c }} />)}</span>
                          )}
                          {row.v}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Footer nav */}
          <div className="frs-footer">
            <button type="button" className="frs-btn frs-btn-ghost" onClick={back} disabled={step === 0}>
              <ArrowLeft size={15} /> Back
            </button>
            <div className="frs-dots">
              {STEPS.map((s, i) => <span key={s.id} className={`frs-dot ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`} />)}
            </div>
            {isLast ? (
              <button type="button" className="frs-btn frs-btn-primary" onClick={launch}>
                Open NexCoder <Rocket size={15} />
              </button>
            ) : (
              <button type="button" className="frs-btn frs-btn-primary" onClick={next}>
                Continue <ArrowRight size={15} />
              </button>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
