// Shared types for the skill catalog.
export interface Skill {
  id: string;
  label: string;
  icon: string;
  description: string;
  shortcut: string;
  category?: string;
}

export interface SkillCategory {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  order?: number;
}
