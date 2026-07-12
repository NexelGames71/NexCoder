"""Tests for the cancellation token, error envelope, and error helpers."""

import unittest

from nexcoder.agent.cancellation import CancellationToken, get_token
from nexcoder.agent.errors import (
    AgentCancelledError,
    AgentContractError,
    ERROR_CATEGORIES,
    ERROR_CODES,
    ErrorEnvelope,
    envelope_from_exception,
)


class CancellationTokenTests(unittest.TestCase):
    def test_starts_uncancelled(self):
        token = CancellationToken()
        self.assertFalse(token.is_cancelled())

    def test_cancel_sets_state(self):
        token = CancellationToken()
        token.cancel()
        self.assertTrue(token.is_cancelled())

    def test_cancel_is_idempotent(self):
        token = CancellationToken()
        token.cancel("first")
        token.cancel("second")  # second call must not change reason
        self.assertEqual(token.reason, "first")

    def test_default_reason(self):
        token = CancellationToken()
        token.cancel()
        # ``cancel()`` with no arg uses the default "cancelled by user".
        self.assertEqual(token.reason, "cancelled by user")

    def test_raise_if_cancelled_raises(self):
        token = CancellationToken()
        token.cancel("user stopped")
        with self.assertRaises(AgentCancelledError) as ctx:
            token.raise_if_cancelled()
        self.assertIn("user stopped", str(ctx.exception))

    def test_raise_if_cancelled_no_op_when_uncancelled(self):
        token = CancellationToken()
        # Should NOT raise.
        token.raise_if_cancelled()

    def test_reset_clears_state(self):
        token = CancellationToken()
        token.cancel()
        token.reset()
        self.assertFalse(token.is_cancelled())
        # raise_if_cancelled must not raise after reset.
        token.raise_if_cancelled()

    def test_get_token_returns_none_for_empty_context(self):
        self.assertIsNone(get_token(None))
        self.assertIsNone(get_token({}))

    def test_get_token_returns_none_for_wrong_type(self):
        self.assertIsNone(get_token({"_cancellation_token": "not a token"}))

    def test_get_token_returns_token(self):
        token = CancellationToken()
        self.assertIs(get_token({"_cancellation_token": token}), token)


class AgentCancelledErrorTests(unittest.TestCase):
    def test_carries_reason(self):
        exc = AgentCancelledError(reason="test reason")
        self.assertEqual(exc.reason, "test reason")
        self.assertIn("test reason", str(exc))


class ErrorEnvelopeTests(unittest.TestCase):
    def test_to_dict_round_trip(self):
        env = ErrorEnvelope(
            code="tool_blocked",
            message="blocked",
            category="safety",
            details={"file": "x.py"},
            retryable=False,
        )
        d = env.to_dict()
        self.assertEqual(d["code"], "tool_blocked")
        self.assertEqual(d["category"], "safety")
        self.assertEqual(d["details"], {"file": "x.py"})

    def test_from_exception_cancelled(self):
        exc = AgentCancelledError("user stopped")
        env = ErrorEnvelope.from_exception(exc)
        self.assertEqual(env.code, "agent_cancelled")
        self.assertEqual(env.category, "user_recoverable")
        self.assertIn("user stopped", env.message)

    def test_from_exception_contract(self):
        exc = AgentContractError(mode="ask", attempts=3, last_response="x")
        env = ErrorEnvelope.from_exception(exc)
        self.assertEqual(env.code, "agent_contract_failure")
        self.assertEqual(env.category, "contract")
        self.assertFalse(env.retryable)

    def test_from_exception_generic(self):
        env = ErrorEnvelope.from_exception(ValueError("boom"))
        self.assertEqual(env.code, "value_error")
        self.assertEqual(env.category, "internal")

    def test_from_exception_overrides(self):
        env = ErrorEnvelope.from_exception(
            ValueError("boom"),
            code="custom_code",
            category="system",
            retryable=True,
            details={"k": "v"},
        )
        self.assertEqual(env.code, "custom_code")
        self.assertEqual(env.category, "system")
        self.assertTrue(env.retryable)
        self.assertEqual(env.details, {"k": "v"})

    def test_from_exception_includes_traceback_when_requested(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            env = ErrorEnvelope.from_exception(exc, include_traceback=True)
        self.assertIsNotNone(env.traceback)
        self.assertIn("RuntimeError", env.traceback)

    def test_envelope_from_exception_helper(self):
        exc = AgentCancelledError("x")
        d = envelope_from_exception(exc)
        self.assertEqual(d["code"], "agent_cancelled")
        self.assertIn("message", d)
        self.assertIn("category", d)

    def test_error_codes_dict_has_expected_keys(self):
        # Spot-check a handful of stable codes.
        for key in (
            "agent_cancelled",
            "agent_contract_failure",
            "tool_blocked",
            "tool_command_blocked",
            "tool_sensitive_file",
            "session_not_found",
            "model_unavailable",
        ):
            self.assertIn(key, ERROR_CODES)
            self.assertIsInstance(ERROR_CODES[key], str)

    def test_error_categories_set(self):
        # Keep this stable — the UI branches on these names.
        self.assertEqual(
            ERROR_CATEGORIES,
            {"user_recoverable", "system", "contract", "safety", "internal"},
        )


if __name__ == "__main__":
    unittest.main()