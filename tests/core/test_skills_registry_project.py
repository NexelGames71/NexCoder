from skill_helpers import make_project_skill

from nexcoder.agent.skills_registry import get_skill_body, get_skills, get_skills_grouped


def test_project_skills_merge_with_builtins(tmp_path):
    make_project_skill(tmp_path, "deploy-widget")
    skills = get_skills(str(tmp_path))
    by_id = {s["id"]: s for s in skills}
    assert "deploy-widget" in by_id
    assert by_id["deploy-widget"]["category"] == "project"
    assert "test-driven-development" in by_id  # built-ins still present


def test_project_skill_overrides_builtin(tmp_path):
    make_project_skill(tmp_path, "test-driven-development",
                       description="Our custom TDD", body="Custom body.")
    body = get_skill_body("test-driven-development", str(tmp_path))
    assert body is not None and body["body"] == "Custom body."


def test_no_project_root_is_builtins_only(tmp_path):
    baseline = {s["id"] for s in get_skills()}
    make_project_skill(tmp_path, "deploy-widget")
    assert "deploy-widget" not in baseline
    assert get_skill_body("deploy-widget") is None


def test_grouped_includes_project_category_first(tmp_path):
    make_project_skill(tmp_path, "deploy-widget")
    grouped = get_skills_grouped(str(tmp_path))
    categories = grouped["categories"]
    assert categories[0]["id"] == "project"
    assert any(s["id"] == "deploy-widget" for s in grouped["skills_by_category"]["project"])


def test_malformed_project_skill_is_skipped(tmp_path):
    folder = tmp_path / ".nexcoder" / "skills" / "broken"
    folder.mkdir(parents=True)
    # No SKILL.md at all
    skills = get_skills(str(tmp_path))
    assert all(s["id"] != "broken" for s in skills)
