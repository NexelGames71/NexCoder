// Minimal skill type definitions used by generated skill catalogs.
export interface Skill {
  id: string;
  label: string;
  icon: string;
  category: string;
  description: string;
  shortcut: string;
}

export interface SkillCategory {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  order?: number;
}

export type { Skill as SkillType, SkillCategory as SkillCategoryType };
