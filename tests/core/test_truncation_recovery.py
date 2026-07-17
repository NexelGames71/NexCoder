"""The screenshot bug: an oversized write_file call hits the output token
cap, parsing fails, and raw tool-call JSON must never reach the user."""

import json

from nexcoder.agent.core.stream_gate import scrub_tool_markup
from nexcoder.agent.core.transport import XmlAdapter


def _parse(content: str):
    return XmlAdapter().parse_assistant_message(
        {"role": "assistant", "content": content})


class TestUnclosedToolCallSalvage:
    def test_complete_json_without_closing_tag_is_accepted(self):
        turn = _parse('I will write the file now.\n<tool_call>\n'
                      + json.dumps({"name": "write_file", "arguments":
                                    {"path": "style.css", "content": "body{}"}}))
        assert turn.parse_error is None
        assert len(turn.tool_calls) == 1
        assert turn.tool_calls[0].name == "write_file"
        assert turn.tool_calls[0].args["path"] == "style.css"
        assert "<tool_call" not in turn.text

    def test_truncated_json_is_not_salvaged(self):
        turn = _parse('<tool_call>\n{"name": "write_file", "arguments": '
                      '{"path": "style.css", "content": "* { margin: 0')
        assert turn.tool_calls == ()
        # The raw payload stays in text so the loop's truncation
        # detector can see it — but final text gets scrubbed.
        assert "<tool_call" in turn.text


class TestFinalTextScrub:
    def test_plain_text_untouched(self):
        text = "All done. Files changed:\n- style.css"
        assert scrub_tool_markup(text) == text

    def test_code_fences_survive(self):
        text = "Run this:\n```bash\npytest -q\n```"
        assert scrub_tool_markup(text) == text

    def test_truncated_tool_call_is_removed(self):
        text = ('First, I will create the style.css file:\n<tool_call>\n'
                '{"name": "write_file", "arguments": {"content": "'
                + "x" * 5000)
        out = scrub_tool_markup(text)
        assert "<tool_call" not in out
        assert "x" * 100 not in out
        assert "First, I will create the style.css file:" in out
        assert "malformed tool call was removed" in out

    def test_bare_json_call_is_removed(self):
        out = scrub_tool_markup('{"name": "write_file", "arguments": {}}')
        assert '"write_file"' not in out
        assert "malformed tool call was removed" in out


class TestWriteFileAppend:
    def test_append_extends_existing_file(self, tmp_path):
        from nexcoder.agent.core.belt_factory import build_default_belt
        from nexcoder.agent.core.tools.base import ToolContext
        belt = build_default_belt()
        ctx = ToolContext(project_root=tmp_path, emit=lambda _e: None,
                          run_id="t")
        first = belt.execute("write_file", {
            "path": "style.css", "content": "body { margin: 0 }\n"}, ctx)
        assert first["success"]
        second = belt.execute("write_file", {
            "path": "style.css", "content": ".nav { color: red }\n",
            "append": True}, ctx)
        assert second["success"]
        text = (tmp_path / "style.css").read_text(encoding="utf-8")
        assert text == "body { margin: 0 }\n.nav { color: red }\n"

    def test_append_to_missing_file_creates_it(self, tmp_path):
        from nexcoder.agent.core.belt_factory import build_default_belt
        from nexcoder.agent.core.tools.base import ToolContext
        belt = build_default_belt()
        ctx = ToolContext(project_root=tmp_path, emit=lambda _e: None,
                          run_id="t")
        result = belt.execute("write_file", {
            "path": "new.txt", "content": "hello", "append": True}, ctx)
        assert result["success"]
        assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "hello"
