from nexcoder.agent.core.conversation import Conversation


def make_convo(**kwargs):
    defaults = dict(context_window=1000, reserve_output=200, compact_threshold=0.5)
    defaults.update(kwargs)
    return Conversation("system prompt", **defaults)


def test_payload_messages_strip_private_keys():
    convo = make_convo()
    convo.add({"role": "user", "content": "hi", "_compacted": True})
    payload = convo.payload_messages()
    assert payload[0] == {"role": "system", "content": "system prompt"}
    assert payload[1] == {"role": "user", "content": "hi"}


def test_needs_compaction_threshold():
    convo = make_convo()
    assert not convo.needs_compaction()
    convo.add({"role": "user", "content": "x" * 3000})  # ~1000 tokens > 400 budget*0.5
    assert convo.needs_compaction()


def test_compact_collapses_old_tool_results_first():
    convo = make_convo()
    big = "line one of output\n" + ("y" * 2000)
    # Old tool result (both transport shapes), then enough recent messages to
    # push it past the protected window.
    convo.add({"role": "tool", "tool_call_id": "c1", "content": big})
    convo.add({"role": "user", "content": "<tool_response>" + big + "</tool_response>"})
    for i in range(Conversation.PROTECTED_RECENT):
        convo.add({"role": "user", "content": f"recent {i}"})
    stats = convo.compact()
    assert stats["after"] < stats["before"]
    collapsed = convo.messages()[1]
    assert collapsed["_compacted"] is True
    assert len(collapsed["content"]) < 200
    assert collapsed["tool_call_id"] == "c1"  # transport linkage preserved
    # Recent messages untouched
    assert convo.messages()[-1]["content"] == f"recent {Conversation.PROTECTED_RECENT - 1}"


def test_compact_summarizes_old_turns_when_still_over_budget():
    convo = make_convo(context_window=400, reserve_output=100)
    for i in range(10):
        convo.add({"role": "user", "content": f"turn {i} " + "z" * 400})
    called_with: list[list] = []

    def summarizer(messages):
        called_with.append(messages)
        return "the story so far"

    convo.compact(summarizer)
    assert called_with, "summarizer should be invoked when collapsing is not enough"
    contents = [m["content"] for m in convo.messages()]
    assert any("the story so far" in c for c in contents)
    assert contents[0] == "system prompt"  # system always survives
