"""Shared helper for skills tests."""


def make_project_skill(tmp_path, skill_id, description="A project skill", body="Do the thing."):
    folder = tmp_path / ".nexcoder" / "skills" / skill_id
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n{body}\n",
        encoding="utf-8")
