from nexcoder.agent.core.stream_gate import StreamGate


def collect():
    out = []
    return out, out.append


def test_prose_streams_through():
    out, emit = collect()
    gate = StreamGate(emit)
    gate.push("Let me look at ")
    gate.push("the project first.")
    gate.flush()
    assert "".join(out) == "Let me look at the project first."


def test_tool_call_markup_is_suppressed():
    out, emit = collect()
    gate = StreamGate(emit)
    gate.push('I will create the file now:\n<tool_call>\n{"name": "write_file", '
              '"arguments": {"path": "index.html", "content": "<html>..."}}\n</tool_call>')
    gate.flush()
    joined = "".join(out)
    assert "I will create the file now:" in joined
    assert "<tool_call" not in joined
    assert "write_file" not in joined


def test_marker_split_across_deltas():
    out, emit = collect()
    gate = StreamGate(emit)
    gate.push("Creating it: <tool_")
    gate.push('call>{"name": "write_file"}</tool_call>')
    gate.flush()
    joined = "".join(out)
    assert joined.startswith("Creating it:")
    assert "<tool_" not in joined


def test_bare_json_tool_call_suppressed():
    out, emit = collect()
    gate = StreamGate(emit)
    gate.push('{"name": "run_command", "arguments": {"command": "dir"}}')
    gate.flush()
    assert "".join(out) == ""


def test_code_fence_suppressed():
    out, emit = collect()
    gate = StreamGate(emit)
    gate.push("Here is the file:\n```html\n<html></html>\n```")
    gate.flush()
    joined = "".join(out)
    assert "Here is the file:" in joined
    assert "```" not in joined
