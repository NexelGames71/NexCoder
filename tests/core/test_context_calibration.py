"""Context accounting accuracy: calibration against real backend usage
and compaction hysteresis (no compact-every-turn thrash)."""

from nexcoder.agent.core.conversation import Conversation
from nexcoder.agent.model_connector import ModelConnector


def _conv(window=1000, reserve=200):
    return Conversation("sys", context_window=window, reserve_output=reserve)


class TestCalibration:
    def test_estimate_scales_toward_actual(self):
        conv = _conv()
        conv.add({"role": "user", "content": "x" * 900})  # est ~300
        estimated = conv.total_tokens()
        # Backend says the same payload was really twice our estimate.
        conv.calibrate(estimated * 2, estimated)
        assert conv.total_tokens() > estimated * 1.3

    def test_scale_is_clamped(self):
        conv = _conv()
        conv.add({"role": "user", "content": "hello world"})
        estimated = conv.total_tokens()
        conv.calibrate(estimated * 100, estimated)  # absurd report
        conv.calibrate(estimated * 100, estimated)
        assert conv._scale <= 3.0
        conv.calibrate(1, conv.total_tokens())
        conv.calibrate(1, conv.total_tokens())
        conv.calibrate(1, conv.total_tokens())
        assert conv._scale >= 0.4

    def test_zero_or_missing_usage_is_ignored(self):
        conv = _conv()
        before = conv.total_tokens()
        conv.calibrate(0, before)
        conv.calibrate(100, 0)
        assert conv.total_tokens() == before


class TestCompactionHysteresis:
    def test_no_rethrash_when_floor_unreachable(self):
        # A conversation whose protected window alone exceeds the
        # threshold: compact once, then needs_compaction goes quiet
        # until the total grows past the post-compaction floor.
        conv = _conv(window=1000, reserve=200)  # budget 800, threshold 600
        for _ in range(8):
            conv.add({"role": "user", "content": "y" * 900})  # protected
        assert conv.needs_compaction()
        conv.compact()  # protected recent messages cannot shrink
        assert not conv.needs_compaction()

    def test_growth_past_floor_triggers_compaction_again(self):
        conv = _conv(window=1000, reserve=200)
        for _ in range(8):
            conv.add({"role": "user", "content": "y" * 900})
        conv.compact()
        for _ in range(3):
            conv.add({"role": "user", "content": "z" * 900})
        assert conv.needs_compaction()


class TestUsageHarvest:
    def test_merge_stream_chunks_picks_up_usage(self):
        chunks = [
            {"choices": [{"delta": {"content": "hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 1234, "completion_tokens": 2,
                       "total_tokens": 1236}},
        ]
        message = ModelConnector.merge_stream_chunks(chunks)
        assert message["content"] == "hello"
        assert message["_usage"]["prompt_tokens"] == 1234

    def test_no_usage_leaves_message_clean(self):
        message = ModelConnector.merge_stream_chunks(
            [{"choices": [{"delta": {"content": "hi"}}]}])
        assert "_usage" not in message
