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


def test_swallowed_progress_reports_char_count():
    out, emit = collect()
    reports = []
    gate = StreamGate(emit, on_swallowed=lambda n, head: reports.append((n, head)))
    # Prose then a big tool call that streams in chunks.
    gate.push("Creating the file:\n")
    body = '<tool_call>\n{"name": "write_file", "arguments": {"path": "big.css", "content": "'
    gate.push(body)
    for _ in range(20):
        gate.push("x" * 100)  # 2000 swallowed chars total
    gate.flush()
    # Prose still forwarded; markup suppressed.
    assert "Creating the file:" in "".join(out)
    assert "<tool_call" not in "".join(out)
    # Progress fired with rising counts and a head containing the tool info.
    assert reports, "expected at least one swallowed-progress report"
    assert reports[-1][0] >= 1500
    assert "write_file" in reports[0][1]


def test_peek_streaming_tool_extracts_name_and_path():
    from nexcoder.agent.core.loop import _peek_streaming_tool
    head = '<tool_call>\n{"name": "write_file", "arguments": {"path": "src/App.js", "content": "'
    tool, path = _peek_streaming_tool(head)
    assert tool == "write_file"
    assert path == "src/App.js"


def test_peek_streaming_tool_tolerates_partial():
    from nexcoder.agent.core.loop import _peek_streaming_tool
    tool, path = _peek_streaming_tool('<tool_call>\n{"na')
    assert tool == "" and path == ""
