"""Skills registry — loads and exposes agent skills.

A *skill* is a ``SKILL.md`` file in ``nexcoder/agent/skills/<id>/SKILL.md``
with YAML frontmatter. Skills are loaded once and exposed to both the
React UI (for the picker menu) and the agent loop (which can invoke them
as a tool via ``load_skill``).

The registry used to conflate the five built-in AI *modes*
(``ask``/``edit``/``agent``/``debug``/``review``) with skills. The modes
live in :mod:`nexcoder.agent.modes`; this module only deals with skills.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SkillMeta:
    """Lightweight metadata for the skill picker UI."""

    id: str
    label: str
    description: str
    category: str
    icon: str  # lucide-react icon name; the UI owns the icon registry
    shortcut: str = ""


@dataclass
class SkillFull:
    """Skill metadata plus the on-disk body content."""

    meta: SkillMeta
    body: str = ""
    path: str = ""


@dataclass(frozen=True)
class SkillCategory:
    """A grouping in the skill picker."""

    id: str
    label: str
    description: str
    order: int


# ──────────────────────────────────────────────────────────────────────
# Categories
# ──────────────────────────────────────────────────────────────────────


SKILL_CATEGORIES: list[SkillCategory] = [
    SkillCategory(
        id="workflow",
        label="Workflow",
        description="How the agent plans and executes work",
        order=1,
    ),
    SkillCategory(
        id="quality",
        label="Quality",
        description="Code quality, review, simplification, debugging",
        order=2,
    ),
    SkillCategory(
        id="frontend",
        label="Frontend",
        description="UI, accessibility, browser testing, performance",
        order=3,
    ),
    SkillCategory(
        id="security",
        label="Security",
        description="Hardening, auth, secrets, risk-aware decisions",
        order=4,
    ),
    SkillCategory(
        id="build",
        label="Build & Ship",
        description="CI/CD, releases, ops, source-driven dev",
        order=5,
    ),
    SkillCategory(
        id="meta",
        label="Meta",
        description="Discovering and combining skills",
        order=6,
    ),
]

CATEGORY_BY_ID: dict[str, SkillCategory] = {c.id: c for c in SKILL_CATEGORIES}


# Manual mapping for skills that don't declare a category in their
# frontmatter. Keep alphabetical and only as a fallback; the loader will
# prefer an explicit frontmatter `category:` field if it is added later.
SKILL_CATEGORY_OVERRIDES: dict[str, str] = {
    # Workflow
    "planning-and-task-breakdown": "workflow",
    "incremental-implementation": "workflow",
    "spec-driven-development": "workflow",
    "idea-refine": "workflow",
    "interview-me": "workflow",
    "doubt-driven-development": "workflow",
    "documentation-and-adrs": "workflow",
    "deprecation-and-migration": "workflow",
    "context-engineering": "workflow",
    "source-driven-development": "workflow",
    "using-agent-skills": "meta",
    # Quality
    "test-driven-development": "quality",
    "code-review-and-quality": "quality",
    "code-simplification": "quality",
    "debugging-and-error-recovery": "quality",
    "git-workflow-and-versioning": "quality",
    "observability-and-instrumentation": "quality",
    # Frontend
    "frontend-ui-engineering": "frontend",
    "browser-testing-with-devtools": "frontend",
    "api-and-interface-design": "frontend",
    "performance-optimization": "frontend",
    # Security
    "security-and-hardening": "security",
    # Build & Ship
    "ci-cd-and-automation": "build",
    "shipping-and-launch": "build",
    # Meta / external runtimes
    "gepeto": "meta",
    "pinokio": "meta",
}


# lucide-react icon name to use for each category, plus per-skill
# overrides. Falls back to a neutral icon for skills without one.
SKILL_ICON_OVERRIDES: dict[str, str] = {
    "test-driven-development": "FlaskConical",
    "code-review-and-quality": "ClipboardCheck",
    "code-simplification": "Sparkles",
    "debugging-and-error-recovery": "Bug",
    "git-workflow-and-versioning": "GitBranch",
    "frontend-ui-engineering": "Layout",
    "browser-testing-with-devtools": "Monitor",
    "performance-optimization": "Gauge",
    "api-and-interface-design": "Cable",
    "security-and-hardening": "Shield",
    "ci-cd-and-automation": "Workflow",
    "shipping-and-launch": "Rocket",
    "planning-and-task-breakdown": "ListChecks",
    "incremental-implementation": "Layers",
    "spec-driven-development": "FileText",
    "idea-refine": "Lightbulb",
    "interview-me": "MessagesSquare",
    "doubt-driven-development": "HelpCircle",
    "documentation-and-adrs": "BookOpen",
    "deprecation-and-migration": "PackageOpen",
    "context-engineering": "Database",
    "source-driven-development": "BookMarked",
    "observability-and-instrumentation": "Activity",
    "using-agent-skills": "Compass",
    "gepeto": "Box",
    "pinokio": "Plug",
}

CATEGORY_ICONS: dict[str, str] = {
    "workflow": "ListChecks",
    "quality": "Sparkles",
    "frontend": "Layout",
    "security": "Shield",
    "build": "Rocket",
    "meta": "Compass",
}


# ──────────────────────────────────────────────────────────────────────
# Frontmatter parsing
# ──────────────────────────────────────────────────────────────────────


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (metadata, body) for a ``SKILL.md`` document.

    The format is intentionally simple: ``key: value`` per line in the
    frontmatter block. Quoted values are unquoted. Missing frontmatter
    returns an empty metadata dict and the original text as the body.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    head, body = match.group(1), match.group(2)
    metadata: dict[str, str] = {}
    for raw_line in head.splitlines():
        line = raw_line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        # Strip a single layer of matching quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        metadata[key] = value
    return metadata, body


def _humanise(name: str) -> str:
    """Turn a kebab-case id into a Title Case label."""
    return name.replace("-", " ").title()


# ──────────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────────


def _skills_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")


def _category_for(skill_id: str, metadata: dict[str, str]) -> str:
    """Return the category id for *skill_id* (frontmatter wins, then override, then ``meta``)."""
    declared = (metadata.get("category") or "").strip().lower()
    if declared and declared in CATEGORY_BY_ID:
        return declared
    return SKILL_CATEGORY_OVERRIDES.get(skill_id, "meta")


def _icon_for(skill_id: str, category: str) -> str:
    return SKILL_ICON_OVERRIDES.get(skill_id, CATEGORY_ICONS.get(category, "Compass"))


def _load_skill_dir(skill_dir: str) -> Optional[SkillFull]:
    """Load a single skill directory. Returns ``None`` on any failure."""
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        return None
    try:
        with open(skill_md, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        logger.warning("Could not read %s: %s", skill_md, exc)
        return None

    metadata, body = _parse_frontmatter(raw)
    name = (metadata.get("name") or os.path.basename(skill_dir)).strip()
    if not name:
        return None
    description = (metadata.get("description") or "").strip()
    category = _category_for(name, metadata)
    icon = _icon_for(name, category)
    label = _humanise(name)
    meta = SkillMeta(
        id=name,
        label=label,
        description=description,
        category=category,
        icon=icon,
    )
    return SkillFull(meta=meta, body=body.strip(), path=skill_md)


def _load_all_skills() -> list[SkillFull]:
    skills: list[SkillFull] = []
    base = _skills_dir()
    if not os.path.isdir(base):
        return skills
    for entry in sorted(os.listdir(base)):
        full = os.path.join(base, entry)
        if not os.path.isdir(full):
            continue
        loaded = _load_skill_dir(full)
        if loaded is not None:
            skills.append(loaded)
    return skills


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def get_skills() -> list[dict]:
    """Return the list of skills (metadata only) for the React picker.

    The shape matches the existing ``Skill`` interface so the UI can
    consume it without a translation layer. The ``category`` field is
    additive — existing components that ignore it will still work.
    """
    return [
        {
            "id": s.meta.id,
            "label": s.meta.label,
            "description": s.meta.description,
            "category": s.meta.category,
            "icon": s.meta.icon,
            "shortcut": "",
        }
        for s in _load_all_skills()
    ]


def get_skill(skill_id: str) -> Optional[dict]:
    """Return metadata for a single skill, or ``None`` if not found."""
    for s in _load_all_skills():
        if s.meta.id == skill_id:
            return {
                "id": s.meta.id,
                "label": s.meta.label,
                "description": s.meta.description,
                "category": s.meta.category,
                "icon": s.meta.icon,
                "shortcut": "",
            }
    return None


def get_skill_body(skill_id: str) -> Optional[dict]:
    """Return a dict ``{id, name, body, category}`` for *skill_id*.

    The body is the markdown content after the frontmatter. Returns
    ``None`` for unknown skill ids so the caller can surface a clear
    error to the model.
    """
    for s in _load_all_skills():
        if s.meta.id == skill_id:
            return {
                "id": s.meta.id,
                "name": s.meta.label,
                "body": s.body,
                "category": s.meta.category,
            }
    return None


def get_skill_categories() -> list[dict]:
    """Return the category catalog for the picker UI."""
    return [
        {
            "id": c.id,
            "label": c.label,
            "description": c.description,
            "icon": CATEGORY_ICONS.get(c.id, "Compass"),
            "order": c.order,
        }
        for c in sorted(SKILL_CATEGORIES, key=lambda x: x.order)
    ]


def get_skills_grouped() -> dict:
    """Return ``{category_id: [skill_meta, ...], categories: [...]}``."""
    skills = get_skills()
    grouped: dict[str, list[dict]] = {c.id: [] for c in SKILL_CATEGORIES}
    for skill in skills:
        grouped.setdefault(skill["category"], []).append(skill)
    return {
        "categories": get_skill_categories(),
        "skills_by_category": grouped,
    }
