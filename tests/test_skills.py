"""Tests for the skills registry."""

import unittest

from nexcoder.agent.skills_registry import (
    get_skill,
    get_skill_body,
    get_skill_categories,
    get_skills,
    get_skills_grouped,
)


class SkillsRegistryTests(unittest.TestCase):
    def test_lists_at_least_20_skills(self):
        skills = get_skills()
        self.assertGreaterEqual(len(skills), 20, "expected the 26 SKILL.md files")

    def test_each_skill_has_required_metadata(self):
        valid_categories = {c["id"] for c in get_skill_categories()}
        for s in get_skills():
            self.assertTrue(s["id"], "skill must have an id")
            self.assertTrue(s["label"], f"skill {s['id']} must have a label")
            self.assertTrue(s["description"], f"skill {s['id']} must have a description")
            self.assertIn(s["category"], valid_categories, f"unknown category: {s['category']!r}")

    def test_categories_are_ordered(self):
        cats = get_skill_categories()
        orders = [c["order"] for c in cats]
        self.assertEqual(orders, sorted(orders), "categories must be in ascending order")

    def test_no_duplicate_ids(self):
        ids = [s["id"] for s in get_skills()]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate skill ids: {ids}")

    def test_skill_body_round_trips(self):
        body = get_skill_body("test-driven-development")
        self.assertIsNotNone(body)
        self.assertEqual(body["id"], "test-driven-development")
        self.assertTrue(body["body"].strip(), "tdd body must be non-empty")
        # The body is the markdown content after the frontmatter.
        self.assertNotIn("---", body["body"].splitlines()[0])

    def test_unknown_skill_returns_none(self):
        self.assertIsNone(get_skill_body("not-a-real-skill"))
        self.assertIsNone(get_skill("not-a-real-skill"))

    def test_get_skill_metadata_matches_get_skill_body(self):
        for skill in get_skills():
            meta = get_skill(skill["id"])
            body = get_skill_body(skill["id"])
            self.assertIsNotNone(meta, f"missing metadata for {skill['id']}")
            self.assertIsNotNone(body, f"missing body for {skill['id']}")
            self.assertEqual(meta["id"], body["id"])

    def test_grouped_output_groups_all_skills(self):
        grouped = get_skills_grouped()
        flat = get_skills()
        in_groups = sum(len(v) for v in grouped["skills_by_category"].values())
        self.assertEqual(in_groups, len(flat))

    def test_categories_have_at_least_one_skill(self):
        grouped = get_skills_grouped()
        # Every category except security (which only has one) should
        # have at least one skill. The registry may add new categories
        # later; this test just guards against an empty category bug.
        # "project" is populated from the open project's .nexcoder/skills
        # and is expected to be empty when no project_root is passed.
        for cat_id, skills in grouped["skills_by_category"].items():
            if cat_id not in {"security", "project"}:
                self.assertGreater(len(skills), 0, f"category {cat_id!r} is empty")


if __name__ == "__main__":
    unittest.main()
