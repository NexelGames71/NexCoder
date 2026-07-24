from nexcoder.agent.core.rules import (
    MAX_RULE_FILE_CHARS, load_project_rules,
)


def test_no_rules_renders_nothing(tmp_path):
    assert load_project_rules(tmp_path) == ""


def test_agents_md_and_nexcoder_md_load_in_order(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Use tabs.", encoding="utf-8")
    (tmp_path / "NEXCODER.md").write_text("Prefer pytest.", encoding="utf-8")
    out = load_project_rules(tmp_path)
    assert "Project rules" in out
    assert out.index("Use tabs.") < out.index("Prefer pytest.")
    assert "## AGENTS.md" in out and "## NEXCODER.md" in out


def test_rules_dir_files_load_sorted(tmp_path):
    rules = tmp_path / ".nexcoder" / "rules"
    rules.mkdir(parents=True)
    (rules / "b-style.md").write_text("Style rule.", encoding="utf-8")
    (rules / "a-security.md").write_text("Security rule.", encoding="utf-8")
    out = load_project_rules(tmp_path)
    assert out.index("Security rule.") < out.index("Style rule.")
    assert "rule: a-security" in out


def test_oversized_rule_file_is_truncated(tmp_path):
    (tmp_path / "AGENTS.md").write_text("x" * 50_000, encoding="utf-8")
    out = load_project_rules(tmp_path)
    assert "(rule file truncated)" in out
    assert len(out) < MAX_RULE_FILE_CHARS + 500


def test_rules_state_they_cannot_override_safety(tmp_path):
    (tmp_path / "AGENTS.md").write_text("anything", encoding="utf-8")
    out = load_project_rules(tmp_path)
    assert "never override safety rules" in out
