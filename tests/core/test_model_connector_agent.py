import pytest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nexcoder.agent.errors import AgentCancelledError
from nexcoder.agent.model_connector import ModelConnector, has_image_input


def chunk(delta, finish=None):
    return {"choices": [{"delta": delta, "finish_reason": finish}]}


def test_api_url_accepts_host_versioned_and_full_completion_bases():
    connector = ModelConnector()
    for base in (
        "https://integrate.api.nvidia.com",
        "https://integrate.api.nvidia.com/v1",
        "https://integrate.api.nvidia.com/v1/chat/completions",
    ):
        connector.set_endpoint(base)
        assert connector._api_url("chat/completions") == (
            "https://integrate.api.nvidia.com/v1/chat/completions")
        assert connector._api_url("models") == (
            "https://integrate.api.nvidia.com/v1/models")


def test_cloud_rate_limits_do_not_use_local_fifteen_minute_retry(monkeypatch):
    monkeypatch.delenv("NEXA_RATE_LIMIT_RETRIES", raising=False)
    connector = ModelConnector()
    connector.set_endpoint("https://integrate.api.nvidia.com/v1")
    assert connector._rate_limit_retry_limit() == 1

    connector.set_endpoint("http://127.0.0.1:8002/v1")
    assert connector._rate_limit_retry_limit() == connector.BUSY_RETRY_LIMIT


def test_rate_limit_retry_can_be_overridden(monkeypatch):
    monkeypatch.setenv("NEXA_RATE_LIMIT_RETRIES", "0")
    connector = ModelConnector()
    assert connector._rate_limit_retry_limit() == 0


def test_rate_limit_wait_remains_cancellable():
    def cancel_check(_text):
        raise AgentCancelledError("cancelled")

    with pytest.raises(AgentCancelledError):
        ModelConnector._interruptible_sleep(10, cancel_check)


def test_provider_request_extras_are_opt_in(monkeypatch):
    for name in (
        "NEXCODER_TOP_P", "NEXCODER_REASONING_BUDGET",
        "NEXCODER_REASONING_EFFORT", "NEXCODER_ENABLE_THINKING",
        "NEXCODER_FORCE_NONEMPTY_CONTENT", "NEXCODER_REASONING_MODELS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert ModelConnector()._provider_request_extras() == {}


def test_detects_multimodal_image_content():
    assert has_image_input([{"role": "user", "content": [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
    ]}])
    assert not has_image_input([{"role": "user", "content": "look"}])


def test_provider_request_extras_support_reasoning_models(monkeypatch):
    monkeypatch.delenv("NEXCODER_REASONING_MODELS", raising=False)
    monkeypatch.setenv("NEXCODER_TOP_P", "0.95")
    monkeypatch.setenv("NEXCODER_REASONING_BUDGET", "16384")
    monkeypatch.setenv("NEXCODER_REASONING_EFFORT", "high")
    monkeypatch.setenv("NEXCODER_ENABLE_THINKING", "true")
    monkeypatch.setenv("NEXCODER_FORCE_NONEMPTY_CONTENT", "1")

    assert ModelConnector()._provider_request_extras() == {
        "top_p": 0.95,
        "reasoning_budget": 16384,
        "reasoning_effort": "high",
        "chat_template_kwargs": {
            "enable_thinking": True,
            "force_nonempty_content": True,
        },
    }


def test_provider_request_extras_can_be_scoped_to_selected_models(monkeypatch):
    monkeypatch.setenv("NEXCODER_REASONING_MODELS", "nvidia/reasoning-model")
    monkeypatch.setenv("NEXCODER_TOP_P", "0.9")
    monkeypatch.setenv("NEXCODER_ENABLE_THINKING", "1")
    monkeypatch.setenv("NEXA_MODEL", "nvidia/other-model")

    assert ModelConnector()._provider_request_extras() == {"top_p": 0.9}


def test_cancel_current_request_unblocks_waiting_http_stream():
    accepted = threading.Event()
    release = threading.Event()

    class HangingHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            self.rfile.read(length)
            accepted.set()
            # Simulate a provider that accepts the request but sends no
            # headers or tokens. Stop must close this socket immediately.
            release.wait(10)
            try:
                self.send_response(200)
                self.end_headers()
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), HangingHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    connector = ModelConnector()
    connector.set_endpoint(f"http://127.0.0.1:{server.server_port}/v1")
    outcome = {}

    def request():
        try:
            connector.chat_agent([{"role": "user", "content": "hello"}])
        except Exception as exc:  # captured for assertion in the test thread
            outcome["exception"] = exc

    request_thread = threading.Thread(target=request)
    request_thread.start()
    try:
        assert accepted.wait(2), "test server never received the request"
        connector.cancel_current_request()
        request_thread.join(2)
        assert not request_thread.is_alive()
        assert isinstance(outcome.get("exception"), AgentCancelledError)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        request_thread.join(2)


def test_merge_text_only():
    message = ModelConnector.merge_stream_chunks([
        chunk({"role": "assistant"}),
        chunk({"content": "Hello "}),
        chunk({"content": "world"}),
        chunk({}, finish="stop"),
    ])
    assert message == {
        "role": "assistant",
        "content": "Hello world",
        "_finish_reason": "stop",
    }


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


def test_merge_captures_finish_reason():
    message = ModelConnector.merge_stream_chunks([
        chunk({"content": "done"}, finish="stop"),
    ])
    assert message["_finish_reason"] == "stop"


def test_merge_removes_reasoning_markup_and_orphan_close_tag():
    message = ModelConnector.merge_stream_chunks([
        chunk({"content": "private chain of thought"}),
        chunk({"content": "</think>\n\n## Result\n\n- changed file"}, finish="stop"),
    ])
    assert message["content"] == "## Result\n\n- changed file"
    assert "think" not in message["content"]


def test_merge_removes_paired_and_unfinished_think_blocks():
    paired = ModelConnector.merge_stream_chunks([
        chunk({"content": "<think>private</think>Visible"}),
    ])
    unfinished = ModelConnector.merge_stream_chunks([
        chunk({"content": "Visible first<think>private tail"}),
    ])
    assert paired["content"] == "Visible"
    assert unfinished["content"] == "Visible first"


def test_empty_agent_completion_is_retryable_stream_error():
    from nexcoder.agent.errors import ModelStreamError

    with pytest.raises(ModelStreamError, match="empty completion"):
        ModelConnector._validate_agent_message({
            "role": "assistant", "content": ""})


def test_tool_only_agent_completion_is_valid():
    message = {"role": "assistant", "content": "", "tool_calls": [{
        "id": "call_1", "type": "function",
        "function": {"name": "read_file", "arguments": "{}"},
    }]}
    assert ModelConnector._validate_agent_message(message) is message


def test_404_backend_surfaces_actionable_model_not_found_error(monkeypatch):
    from nexcoder.agent.errors import ModelHTTPError

    monkeypatch.setenv("NEXA_MODEL", "z-ai/glm-5.2")

    class NotFoundHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            self.rfile.read(length)
            body = b'{"error":{"message":"model not found"}}'
            self.send_response(404)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), NotFoundHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        connector = ModelConnector()
        connector.set_endpoint(f"http://127.0.0.1:{server.server_port}/v1")
        with pytest.raises(ModelHTTPError) as exc_info:
            connector.chat_agent([{"role": "user", "content": "hello"}])
        msg = str(exc_info.value)
        assert "HTTP 404" in msg
        assert "not available" in msg
        assert "z-ai/glm-5.2" in msg
        assert "model not found" in msg  # backend detail preserved
    finally:
        server.shutdown()
        server.server_close()
