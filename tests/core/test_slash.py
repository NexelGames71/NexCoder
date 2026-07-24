from nexcoder.agent.core.slash import DEFAULT_SKILL_TASK, parse_slash_command

IDS = {"commit", "code-review"}


def test_known_slash_with_task():
    assert parse_slash_command("/commit fix the auth bug", IDS) == ("commit", "fix the auth bug")


def test_bare_slash_gets_default_task():
    assert parse_slash_command("/commit", IDS) == ("commit", DEFAULT_SKILL_TASK)


def test_unknown_slash_passes_through():
    assert parse_slash_command("/wat do things", IDS) == (None, "/wat do things")


def test_plain_text_passes_through():
    assert parse_slash_command("commit my changes", IDS) == (None, "commit my changes")
