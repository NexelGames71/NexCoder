import json

from nexcoder.agent.core.transport import (
    ModelTurn, NativeAdapter, ToolCall, XmlAdapter, get_adapter,
)

SCHEMAS = [{"type": "function", "function": {
    "name": "read_file", "description": "Read a file",
    "parameters": {"type": "object",
                   "properties": {"path": {"type": "string"}},
                   "required": ["path"]}}}]


def test_adapters_parse_equivalent_calls_identically():
    xml_message = {"role": "assistant", "content":
                   'Reading it now.\n<tool_call name="read_file">{"path": "app.py"}</tool_call>'}
    native_message = {"role": "assistant", "content": "Reading it now.",
                      "tool_calls": [{"id": "call_1", "type": "function", "function": {
                          "name": "read_file", "arguments": '{"path": "app.py"}'}}]}
    xml_turn = XmlAdapter().parse_assistant_message(xml_message)
    native_turn = NativeAdapter().parse_assistant_message(native_message)
    assert [(c.name, c.args) for c in xml_turn.tool_calls] == \
           [(c.name, c.args) for c in native_turn.tool_calls] == [("read_file", {"path": "app.py"})]
    assert xml_turn.text == native_turn.text == "Reading it now."


def test_xml_adapter_parses_qwen_native_format():
    # Qwen2.5 emits Hermes-style calls: name inside the JSON body.
    message = {"role": "assistant", "content":
               'On it.\n<tool_call>\n{"name": "read_file", "arguments": {"path": "app.py"}}\n</tool_call>'}
    turn = XmlAdapter().parse_assistant_message(message)
    assert [(c.name, c.args) for c in turn.tool_calls] == [("read_file", {"path": "app.py"})]
    assert turn.text == "On it."


def test_xml_adapter_qwen_format_bad_json_is_parse_error():
    turn = XmlAdapter().parse_assistant_message(
        {"role": "assistant", "content": "<tool_call>\n{broken\n</tool_call>"})
    assert turn.tool_calls == ()
    assert turn.parse_error


def test_xml_adapter_reports_parse_error_not_exception():
    turn = XmlAdapter().parse_assistant_message(
        {"role": "assistant", "content": '<tool_call name="read_file">{bad json</tool_call>'})
    assert turn.tool_calls == ()
    assert turn.parse_error and "read_file" in turn.parse_error


def test_native_adapter_reports_bad_arguments_json():
    turn = NativeAdapter().parse_assistant_message(
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
         "function": {"name": "read_file", "arguments": "{oops"}}]})
    assert turn.tool_calls == ()
    assert turn.parse_error


def test_request_extras_and_prompt_suffix():
    assert XmlAdapter().request_extras(SCHEMAS) == {}
    assert NativeAdapter().request_extras(SCHEMAS) == {"tools": SCHEMAS}
    suffix = XmlAdapter().system_prompt_suffix(SCHEMAS)
    assert "read_file" in suffix and "tool_call" in suffix
    assert NativeAdapter().system_prompt_suffix(SCHEMAS) == ""


def test_tool_result_messages_shapes():
    calls = [ToolCall(id="c1", name="read_file", args={"path": "a"})]
    results = [{"success": True, "content": "hello"}]
    xml_msgs = XmlAdapter().tool_result_messages(calls, results)
    assert len(xml_msgs) == 1 and xml_msgs[0]["role"] == "user"
    assert "<tool_response>" in xml_msgs[0]["content"]
    native_msgs = NativeAdapter().tool_result_messages(calls, results)
    assert native_msgs[0]["role"] == "tool"
    assert native_msgs[0]["tool_call_id"] == "c1"
    assert json.loads(native_msgs[0]["content"])["success"] is True


def test_get_adapter():
    assert isinstance(get_adapter("xml"), XmlAdapter)
    assert isinstance(get_adapter("native"), NativeAdapter)
