from nexcoder.agent.core.events import AgentEvent


def test_event_to_dict_roundtrip():
    event = AgentEvent(type="tool_started", payload={"tool": "read_file"})
    data = event.to_dict()
    assert data["type"] == "tool_started"
    assert data["payload"] == {"tool": "read_file"}
    assert isinstance(data["ts"], float)


def test_event_default_payload_is_empty_dict():
    event = AgentEvent(type="run_started")
    assert event.payload == {}
