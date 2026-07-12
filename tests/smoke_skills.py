import sys
sys.path.insert(0, r'D:\NexCoder')
from nexcoder.agent.skills_registry import (
    get_skills,
    get_skill_body,
    get_skills_grouped,
    get_skill_categories,
)

skills = get_skills()
print(f"count: {len(skills)}")

cats = get_skill_categories()
print("categories:", [c["id"] for c in cats])

grouped = get_skills_grouped()
for c in cats:
    skills_in_cat = grouped["skills_by_category"].get(c["id"], [])
    ids = [s["id"] for s in skills_in_cat]
    print(f"  {c['id']:10s} ({len(skills_in_cat):2d}): {ids}")

body = get_skill_body("test-driven-development")
if body:
    print()
    print("tdd body length:", len(body["body"]))
    print("tdd first line:", body["body"].splitlines()[0])
    print("tdd category:", body["category"])

print()
print("unknown skill:", get_skill_body("does-not-exist"))
