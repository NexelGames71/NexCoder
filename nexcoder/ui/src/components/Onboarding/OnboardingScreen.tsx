import React, { useMemo, useState } from 'react';
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Code2,
  Layers3,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import editorScreenshot from '../../assets/onboarding/nexcoder-editor.png';
import agentMeshScreenshot from '../../assets/onboarding/nexcoder-agent-mesh.png';
import './OnboardingScreen.css';

interface OnboardingScreenProps {
  onStartLogin: () => void;
}

const slides = [
  {
    eyebrow: 'NexCoder IDE',
    title: 'Build with the editor and agent in one workspace.',
    body: 'Open projects, inspect problems, preview artifacts, and keep the coding agent close to the files it is changing.',
    image: editorScreenshot,
    icon: Code2,
  },
  {
    eyebrow: 'Agent Mesh',
    title: 'Let specialist agents handle complex engineering work.',
    body: 'Coordinate focused roles for implementation, review, tests, and architecture without leaving the IDE.',
    image: agentMeshScreenshot,
    icon: Bot,
  },
  {
    eyebrow: 'Production Workflow',
    title: 'Configure NexCoder for your preferred working style.',
    body: 'After sign-in, choose editor layout, agent autonomy, and model profile before the workspace opens.',
    image: editorScreenshot,
    icon: ShieldCheck,
  },
];

const capabilities = [
  { label: 'Command palette', icon: Sparkles },
  { label: 'Artifacts', icon: Layers3 },
  { label: 'Agent fixes', icon: Bot },
  { label: 'Secure web auth', icon: ShieldCheck },
];

export default function OnboardingScreen({ onStartLogin }: OnboardingScreenProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeSlide = slides[activeIndex];
  const ActiveIcon = activeSlide.icon;
  const isLastSlide = activeIndex === slides.length - 1;

  const progressLabel = useMemo(
    () => `${activeIndex + 1} of ${slides.length}`,
    [activeIndex],
  );

  const handlePrimary = () => {
    if (isLastSlide) {
      onStartLogin();
      return;
    }
    setActiveIndex((index) => Math.min(index + 1, slides.length - 1));
  };

  return (
    <main className="onboarding-screen">
      <section className="onboarding-copy">
        <div className="onboarding-brand">
          <div className="onboarding-logo">N</div>
          <span>NexCoder</span>
        </div>

        <div className="onboarding-step-pill">
          <ActiveIcon size={14} />
          <span>{activeSlide.eyebrow}</span>
        </div>

        <div className="onboarding-headline">
          <h1>{activeSlide.title}</h1>
          <p>{activeSlide.body}</p>
        </div>

        <div className="onboarding-capability-grid" aria-label="NexCoder capabilities">
          {capabilities.map((item) => {
            const Icon = item.icon;
            return (
              <div className="onboarding-capability" key={item.label}>
                <Icon size={15} />
                <span>{item.label}</span>
              </div>
            );
          })}
        </div>

        <div className="onboarding-actions">
          <button className="btn btn-primary onboarding-primary" type="button" onClick={handlePrimary}>
            {isLastSlide ? 'Sign in to continue' : 'Continue'}
            <ArrowRight size={15} />
          </button>
          <div className="onboarding-progress" aria-label={progressLabel}>
            {slides.map((slide, index) => (
              <button
                key={slide.eyebrow}
                type="button"
                className={`onboarding-dot ${index === activeIndex ? 'active' : ''}`}
                aria-label={`Show ${slide.eyebrow}`}
                onClick={() => setActiveIndex(index)}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="onboarding-preview" aria-label="NexCoder IDE screenshots">
        <div className="onboarding-preview-header">
          <div>
            <span className="onboarding-preview-kicker">Workspace preview</span>
            <h2>{activeSlide.eyebrow}</h2>
          </div>
          <div className="onboarding-preview-status">
            <CheckCircle2 size={14} />
            <span>Ready</span>
          </div>
        </div>
        <div className="onboarding-screenshot-frame">
          <img src={activeSlide.image} alt={`${activeSlide.eyebrow} screenshot`} />
        </div>
      </section>
    </main>
  );
}
