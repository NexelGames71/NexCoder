import base64

import pytest

from nexcoder.agent.core.conversation import message_tokens
from nexcoder.agent.image_inputs import (
    attachment_metadata,
    build_user_content,
    messages_for_persistence,
    validate_image_attachments,
)


PNG_BYTES = bytes.fromhex("89504e470d0a1a0a")
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


def image_input(name="problem.png"):
    return {
        "id": "image-1",
        "name": name,
        "mime_type": "image/png",
        "data_url": PNG_DATA_URL,
    }


def test_validates_and_formats_openai_image_parts():
    images = validate_image_attachments([image_input()])

    assert images[0]["size"] == len(PNG_BYTES)
    content = build_user_content("Fix what is shown", images)
    assert content[0]["type"] == "text"
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": PNG_DATA_URL, "detail": "high"},
    }


def test_rejects_mime_signature_mismatch():
    bad = image_input()
    bad["data_url"] = "data:image/jpeg;base64," + base64.b64encode(PNG_BYTES).decode()

    with pytest.raises(ValueError, match="declared type"):
        validate_image_attachments([bad])


def test_persistence_never_keeps_inline_image_bytes():
    images = validate_image_attachments([image_input("ui.png")])
    content = build_user_content("Inspect this", images)
    saved = messages_for_persistence([{"role": "user", "content": content}])

    assert PNG_DATA_URL not in str(saved)
    assert "ui.png" in saved[0]["content"]
    assert "omitted from saved transcript" in saved[0]["content"]
    assert "data_url" not in str(attachment_metadata(images))


def test_token_estimate_does_not_count_base64_as_text():
    content = [{"type": "text", "text": "look"}, {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64," + ("A" * 1_000_000)},
    }]

    assert message_tokens({"role": "user", "content": content}) < 2000
