from skill_helpers import make_project_skill

from nexcoder.agent.core.skills_catalog import render_skills_catalog


def test_catalog_lists_skills_with_header():
    text = render_skills_catalog()
    assert text.startswith("# Skills")
    assert "load_skill" in text
    assert "- test-driven-development" in text


def test_project_skills_listed_first(tmp_path):
    make_project_skill(tmp_path, "deploy-widget", description="Deploy the widget")
    text = render_skills_catalog(str(tmp_path))
    lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert lines[0].startswith("- deploy-widget")


def test_catalog_truncates_at_budget(tmp_path):
    for i in range(40):
        make_project_skill(tmp_path, f"skill-{i:02}", description="x" * 200)
    text = render_skills_catalog(str(tmp_path), token_budget=100)
    assert len(text) <= 100 * 3 + 80
    assert "[more skills omitted]" in text


def test_description_capped_at_90_chars(tmp_path):
    make_project_skill(tmp_path, "wordy", description="d" * 300)
    text = render_skills_catalog(str(tmp_path))
    line = next(l for l in text.splitlines() if l.startswith("- wordy"))
    assert len(line) <= len("- wordy — ") + 90
