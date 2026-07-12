import React, { useEffect, useMemo, useRef, useState } from 'react';
import { X, Search, Compass, Check } from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import {
  MODES,
  FALLBACK_SKILLS,
  FALLBACK_CATEGORIES,
  ICON_REGISTRY,
  type ModeId,
  type Skill,
  type SkillCategory,
} from '../../data/skills';
import { fetchSkills } from '../../services/bridge';
import './SkillPicker.css';

interface SkillPickerProps {
  onClose: () => void;
  filter?: string;
}

type LoadedData = {
  categories: SkillCategory[];
  skillsByCategory: Record<string, Skill[]>;
};

const EMPTY_DATA: LoadedData = {
  categories: FALLBACK_CATEGORIES,
  skillsByCategory: groupFallback(),
};

function groupFallback(): Record<string, Skill[]> {
  const groups: Record<string, Skill[]> = {};
  for (const c of FALLBACK_CATEGORIES) {
    groups[c.id] = [];
  }
  for (const s of FALLBACK_SKILLS) {
    const cat = s.category || 'meta';
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(s);
  }
  return groups;
}

export default function SkillPicker({ onClose, filter = '' }: SkillPickerProps) {
  const { activeMode, activeSkill, setActiveMode, setActiveSkill } = useChatStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<LoadedData>(EMPTY_DATA);
  const [search, setSearch] = useState(filter);

  // Try to load the live catalog from the backend on mount. If it fails
  // (no bridge in dev mode), we keep the fallback so the picker is
  // never empty.
  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((result) => {
        if (cancelled || !result) return;
        setData({
          categories: result.categories,
          skillsByCategory: result.skills_by_category,
        });
      })
      .catch(() => {/* keep fallback */});
    return () => {
      cancelled = true;
    };
  }, []);

  // Outside-click + escape close
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  const handleMode = (mode: ModeId) => {
    setActiveMode(mode);
    onClose();
  };

  const handleSkill = (skillId: string | null) => {
    setActiveSkill(skillId);
    onClose();
  };

  const filteredSkills = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return data.skillsByCategory;
    const out: Record<string, Skill[]> = {};
    for (const [cat, skills] of Object.entries(data.skillsByCategory)) {
      const matches = skills.filter(
        (s) =>
          s.label.toLowerCase().includes(q) ||
          s.id.includes(q) ||
          s.description.toLowerCase().includes(q),
      );
      if (matches.length > 0) out[cat] = matches;
    }
    return out;
  }, [data, search]);

  const filteredCategories = useMemo(() => {
    return data.categories.filter((c) => (filteredSkills[c.id]?.length ?? 0) > 0);
  }, [data.categories, filteredSkills]);

  const hasAnyResults =
    filteredCategories.length > 0 ||
    (search.trim().length > 0 ? filteredCategories.length > 0 : true);

  return (
    <div
      ref={containerRef}
      className="skill-picker"
      role="dialog"
      aria-label="Select mode and skill"
    >
      <div className="skill-picker-header">
        <span className="skill-picker-title">
          <Compass size={12} style={{ marginRight: 6, opacity: 0.7 }} />
          Modes &amp; Skills
        </span>
        <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close">
          <X size={12} />
        </button>
      </div>

      <div className="skill-picker-search">
        <Search size={12} className="skill-picker-search-icon" />
        <input
          className="skill-picker-search-input"
          placeholder="Filter skills..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
      </div>

      {/* ── Mode row ── */}
      <div className="skill-picker-section">
        <div className="skill-picker-section-label">Mode</div>
        <div className="skill-picker-modes">
          {MODES.map((mode) => {
            const Icon = mode.icon;
            const isActive = activeMode === mode.id;
            return (
              <button
                key={mode.id}
                className={`skill-picker-mode-chip${isActive ? ' is-active' : ''}`}
                onClick={() => handleMode(mode.id)}
                style={{ '--chip-color': mode.color } as React.CSSProperties}
                title={mode.description}
                aria-pressed={isActive}
              >
                <Icon size={12} />
                <span>{mode.label}</span>
                {isActive && <Check size={10} className="skill-picker-check" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Skills grouped by category ── */}
      <div className="skill-picker-section">
        <div className="skill-picker-section-label-row">
          <span className="skill-picker-section-label">Skill</span>
          <span className="skill-picker-section-hint">
            {activeSkill ? `Active: ${activeSkill}` : 'Optional — pick one to bias the agent'}
          </span>
          {activeSkill && (
            <button
              className="skill-picker-clear"
              onClick={() => handleSkill(null)}
              title="Clear active skill"
            >
              Clear
            </button>
          )}
        </div>

        {filteredCategories.length === 0 ? (
          <div className="skill-picker-empty">No skills match "{search}"</div>
        ) : (
          <div className="skill-picker-list">
            {filteredCategories.map((cat) => {
              const skills = filteredSkills[cat.id] || [];
              if (skills.length === 0) return null;
              return (
                <div key={cat.id} className="skill-picker-category">
                  <div className="skill-picker-category-label">
                    {cat.label}
                    <span className="skill-picker-category-count">{skills.length}</span>
                  </div>
                  {skills.map((skill) => {
                    const Icon = ICON_REGISTRY[skill.icon] || Compass;
                    const isActive = activeSkill === skill.id;
                    return (
                      <button
                        key={skill.id}
                        className={`skill-card${isActive ? ' is-active' : ''}`}
                        onClick={() => handleSkill(skill.id)}
                        aria-pressed={isActive}
                      >
                        <div
                          className="skill-card-icon"
                          style={{ color: 'var(--accent-blue)', background: 'var(--accent-blue-18, rgba(96,165,250,0.10))' }}
                        >
                          <Icon size={14} />
                        </div>
                        <div className="skill-card-body">
                          <div className="skill-card-name">{skill.label}</div>
                          <div className="skill-card-desc">{skill.description}</div>
                        </div>
                        {isActive && <Check size={12} className="skill-card-check" />}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
