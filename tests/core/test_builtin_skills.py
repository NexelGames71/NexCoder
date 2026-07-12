from nexcoder.agent.skills_registry import get_skill_body, get_skills

NEW_IDS = {"commit", "init", "code-review", "systematic-debugging",
           "verification-before-completion", "writing-plans"}
RETIRED_IDS = {"code-review-and-quality", "debugging-and-error-recovery"}


def test_new_skills_present_with_bodies():
    ids = {s["id"] for s in get_skills()}
    assert NEW_IDS <= ids
    for skill_id in NEW_IDS:
        record = get_skill_body(skill_id)
        assert record and len(record["body"]) > 200, skill_id


def test_retired_skills_gone():
    ids = {s["id"] for s in get_skills()}
    assert not (RETIRED_IDS & ids)


def test_new_skills_have_descriptions_for_catalog():
    by_id = {s["id"]: s for s in get_skills()}
    for skill_id in NEW_IDS:
        assert len(by_id[skill_id]["description"]) > 20, skill_id
