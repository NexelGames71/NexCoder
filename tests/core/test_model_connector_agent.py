from nexcoder.agent.model_connector import ModelConnector


def chunk(delta, finish=None):
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


def test_merge_text_only():
    message = ModelConnector.merge_stream_chunks([
        chunk({"role": "assistant"}),
        chunk({"content": "Hello "}),
        chunk({"content": "world"}),
        chunk({}, finish="stop"),
    ])
    assert message == {"role": "assistant", "content": "Hello world"}


def test_merge_tool_call_fragments():
    message = ModelConnector.merge_stream_chunks([
        chunk({"role": "assistant"}),
        chunk({"tool_calls": [{"index": 0, "id": "call_9", "type": "function",
                               "function": {"name": "read_file", "arguments": ""}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"path":'}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": ' "a.py"}'}}]}),
        chunk({}, finish="tool_calls"),
    ])
    assert message["content"] == ""
    call = message["tool_calls"][0]
    assert call["id"] == "call_9"
    assert call["function"]["name"] == "read_file"
    assert call["function"]["arguments"] == '{"path": "a.py"}'


def test_merge_parallel_tool_calls():
    message = ModelConnector.merge_stream_chunks([
        chunk({"tool_calls": [{"index": 0, "id": "a", "function": {"name": "glob", "arguments": "{}"}}]}),
        chunk({"tool_calls": [{"index": 1, "id": "b", "function": {"name": "grep", "arguments": "{}"}}]}),
    ])
    assert [c["id"] for c in message["tool_calls"]] == ["a", "b"]


def test_merge_captures_usage_chunk():
    # Backends that honor stream_options.include_usage append a final
    # chunk carrying real token counts; the loop uses it to calibrate.
    message = ModelConnector.merge_stream_chunks([
        chunk({"role": "assistant"}),
        chunk({"content": "done"}),
        {"choices": [], "usage": {"prompt_tokens": 1234, "completion_tokens": 12}},
    ])
    assert message["content"] == "done"
    assert message["_usage"]["prompt_tokens"] == 1234


def test_merge_without_usage_has_no_usage_key():
    message = ModelConnector.merge_stream_chunks([
        chunk({"content": "hi"}),
    ])
    assert "_usage" not in message
