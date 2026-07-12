import React, { useMemo } from 'react';
import { X, Compass, type LucideIcon } from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { MODES, ICON_REGISTRY, type ModeId } from '../../data/skills';

interface ActiveSkillChipProps {
  onClick: () => void;
  onClearSkill?: () => void;
}

const fallbackIcon: LucideIcon = Compass;

export default function ActiveSkillChip({ onClick, onClearSkill }: ActiveSkillChipProps) {
  const { activeMode, activeSkill, skills, setActiveSkill } = useChatStore();

  const mode = useMemo(
    () => MODES.find((m) => m.id === (activeMode as ModeId)) ?? MODES[0],
    [activeMode],
  );
  const ModeIcon = mode.icon;
  const color = mode.color;

  const activeSkillMeta = activeSkill
    ? skills.find((s) => s.id === activeSkill)
    : null;
  const SkillIcon: LucideIcon = activeSkillMeta
    ? ICON_REGISTRY[activeSkillMeta.icon] ?? fallbackIcon
    : fallbackIcon;
  const skillColor = activeSkillMeta
    ? 'var(--accent-blue, #60a5fa)'
    : 'var(--text-secondary, #8888a0)';

  const handleClearSkill = (e: React.MouseEvent) => {
    e.stopPropagation();
    setActiveSkill(null);
    onClearSkill?.();
  };

  return (
    <div className="active-skill-chip-group">
      <button
        className="active-skill-chip"
        onClick={onClick}
        title={`Mode: ${mode.label}. Click to change mode or skill.`}
        style={{ '--chip-color': color } as React.CSSProperties}
      >
        <span className="active-skill-chip-icon">
          <ModeIcon size={11} />
        </span>
        <span className="active-skill-chip-label">{mode.label}</span>
      </button>

      {activeSkill && (
        <>
          <span className="active-skill-chip-sep" aria-hidden>
            +
          </span>
          <button
            className="active-skill-chip active-skill-chip-skill"
            onClick={onClick}
            title={`Skill: ${activeSkillMeta?.label ?? activeSkill}. Click to change.`}
            style={{ '--chip-color': skillColor } as React.CSSProperties}
          >
            <span className="active-skill-chip-icon">
              <SkillIcon size={11} />
            </span>
            <span className="active-skill-chip-label">
              {activeSkillMeta?.label ?? activeSkill}
            </span>
            <span
              className="active-skill-chip-remove"
              role="button"
              aria-label="Remove skill"
              title="Remove skill"
              onClick={handleClearSkill}
            >
              <X size={9} />
            </span>
          </button>
        </>
      )}
    </div>
  );
}
