"""Tests for the AgenticRunner, mode profiles, and contract enforcement."""

import unittest
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

from nexcoder.agent.agentic_runner import (
    AgenticRunner,
    _extract_final_answer,
)
from nexcoder.agent.errors import AgentContractError
from nexcoder.agent.hermes_runtime import HermesAgentLoop
from nexcoder.agent.mode_profiles import (
    AGENT_PROFILE,
    ASK_PROFILE,
    DEBUG_PROFILE,
    EDIT_PROFILE,
    FINAL_ANSWER_CLOSE,
    FINAL_ANSWER_OPEN,
    READ_TOOLS,
    REVIEW_PROFILE,
    get_profile,
)


class ModeProfileTests(unittest.TestCase):
    def test_read_only_modes_only_allow_read_tools(self):
        for name in ("ask", "review"):
            profile = get_profile(name)
            self.assertTrue(profile.read_only, f"{name} must be read-only")
            for tool in profile.allowed_tools:
                self.assertIn(tool, READ_TOOLS)

    def test_load_skill_is_a_read_tool(self):
        # load_skill is a read operation (returns SKILL.md content) and
        # must be allowed in read-only modes.
        for name in ("ask", "review", "edit", "debug", "agent"):
            profile = get_profile(name)
            self.assertIn(
                "load_skill",
                profile.allowed_tools,
                f"{name} must allow load_skill",
            )

    def test_write_capable_modes_allow_all_tools(self):
        for name in ("edit", "debug", "agent"):
            profile = get_profile(name)
            self.assertFalse(profile.read_only, f"{name} must be write-capable")
            self.assertIn("write_file", profile.allowed_tools)
            self.assertIn("run_command", profile.allowed_tools)

    def test_get_profile_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_profile("nope")

    def test_turn_budgets_are_mode_specific(self):
        # Read-only modes get fewer turns, agent mode gets the most.
        self.assertLess(ASK_PROFILE.max_turns, AGENT_PROFILE.max_turns)
        self.assertLess(REVIEW_PROFILE.max_turns, EDIT_PROFILE.max_turns)
        # All profiles share the same retry budget for now.
        for profile in (ASK_PROFILE, EDIT_PROFILE, DEBUG_PROFILE, REVIEW_PROFILE, AGENT_PROFILE):
            self.assertGreaterEqual(profile.max_retries, 1)

    def test_final_shapes_match_mode_intent(self):
        self.assertEqual(ASK_PROFILE.final_shape, "final_answer")
        self.assertEqual(REVIEW_PROFILE.final_shape, "final_answer")
        self.assertEqual(EDIT_PROFILE.final_shape, "write_or_diff")
        self.assertEqual(DEBUG_PROFILE.final_shape, "write_or_diff")
        self.assertEqual(AGENT_PROFILE.final_shape, "any")

    def test_read_only_profiles_ask_for_final_answer_tags(self):
        for profile in (ASK_PROFILE, REVIEW_PROFILE):
            self.assertIn(FINAL_ANSWER_OPEN, profile.extra_instructions)
            self.assertIn(FINAL_ANSWER_CLOSE, profile.extra_instructions)


class HermesContractTests(unittest.TestCase):
    """Cover the contract enforcement added in hermes_runtime.py."""

    def setUp(self) -> None:
        self.loop = HermesAgentLoop(project_root=Path("."))

    def test_extract_tool_calls_raises_on_invalid_json(self):
        bad = '<tool_call name="read_file">{not json}</tool_call>'
        with self.assertRaises(ValueError) as ctx:
            self.loop.extract_tool_calls(bad)
        self.assertIn("invalid JSON", str(ctx.exception))
        self.assertIn("read_file", str(ctx.exception))

    def test_extract_tool_calls_raises_when_args_not_object(self):
        bad = '<tool_call name="read_file">"a string"</tool_call>'
        with self.assertRaises(ValueError) as ctx:
            self.loop.extract_tool_calls(bad)
        self.assertIn("must be a JSON object", str(ctx.exception))

    def test_tool_args_or_error_returns_parse_error_string(self):
        calls, err = self.loop.tool_args_or_error(
            '<tool_call name="read_file">{not json}</tool_call>'
        )
        self.assertEqual(calls, [])
        self.assertIsNotNone(err)
        self.assertIn("invalid JSON", err)

    def test_tool_args_or_error_handles_empty_args(self):
        calls, err = self.loop.tool_args_or_error(
            '<tool_call name="read_file"></tool_call>'
        )
        self.assertEqual(err, None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["args"], {})

    def test_prefill_first_tool_call_emits_list_directory(self):
        prefill = self.loop.prefill_first_tool_call()
        self.assertIn('<tool_call name="list_directory">', prefill)
        self.assertTrue(prefill.endswith("</tool_call>"))


class FinalAnswerExtractionTests(unittest.TestCase):
    def test_extracts_strict_final_answer(self):
        text = f"Here is the answer:\n{FINAL_ANSWER_OPEN}\n**bold** and `code`\n{FINAL_ANSWER_CLOSE}\nbye"
        self.assertEqual(_extract_final_answer(text), "**bold** and `code`")

    def test_handles_multiline_final_answer(self):
        text = (
            f"{FINAL_ANSWER_OPEN}\nline 1\nline 2\nline 3\n{FINAL_ANSWER_CLOSE}"
        )
        self.assertEqual(_extract_final_answer(text), "line 1\nline 2\nline 3")

    def test_falls_back_to_whole_text_when_missing_tags(self):
        text = "no tags here"
        self.assertEqual(_extract_final_answer(text), "no tags here")

    def test_strips_unbalanced_tag_text_as_fallback(self):
        text = f"oops {FINAL_ANSWER_OPEN} but no close"
        result = _extract_final_answer(text)
        self.assertNotIn(FINAL_ANSWER_OPEN, result)
        self.assertIn("oops", result)


class AgenticRunnerTests(unittest.TestCase):
    """Exercise the runner with a mocked Hermes loop."""

    def _make_runner(self, profile_name: str) -> tuple[AgenticRunner, MagicMock]:
        runner = AgenticRunner(profile_name)
        loop_mock = MagicMock(spec=HermesAgentLoop)
        runner._loop = loop_mock
        return runner, loop_mock

    def test_runner_injects_profile_into_context(self):
        runner, loop_mock = self._make_runner("ask")
        loop_mock.run.return_value = {
            "success": True,
            "response": f"{FINAL_ANSWER_OPEN}the answer{FINAL_ANSWER_CLOSE}",
            "mode": "ask",
            "patches": 0,
        }
        chunks: list[str] = []
        runner.run(
            "what is X?",
            {"project_path": str(Path.cwd())},
            {"on_chunk": chunks.append},
        )
        loop_mock.run.assert_called_once()
        call_args = loop_mock.run.call_args
        ctx_passed = call_args.args[1]
        self.assertIs(ctx_passed["_mode_profile"], ASK_PROFILE)

    def test_final_answer_is_extracted_and_restyled(self):
        runner, loop_mock = self._make_runner("ask")
        loop_mock.run.return_value = {
            "success": True,
            "response": (
                "thinking aloud\n"
                f"{FINAL_ANSWER_OPEN}\nthe real answer\n{FINAL_ANSWER_CLOSE}"
            ),
            "mode": "ask",
            "patches": 0,
        }
        chunks: list[str] = []
        result = runner.run("q", {}, {"on_chunk": chunks.append})
        self.assertEqual(result["response"], "the real answer")
        # The cleaned answer should be re-streamed (not the raw tagged text).
        self.assertTrue(any("the real answer" in c for c in chunks))
        self.assertFalse(any(FINAL_ANSWER_OPEN in c for c in chunks))

    def test_write_or_diff_missing_flag_for_prose_only_edit(self):
        runner, loop_mock = self._make_runner("edit")
        loop_mock.run.return_value = {
            "success": True,
            "response": "I think we should add logging here.",
            "mode": "edit",
            "patches": 0,
        }
        result = runner.run("add logging", {}, {})
        self.assertTrue(result.get("write_or_diff_missing"))

    def test_write_or_diff_passes_through_when_patch_present(self):
        runner, loop_mock = self._make_runner("edit")
        loop_mock.run.return_value = {
            "success": True,
            "response": "```diff\n@@\n-old\n+new\n```",
            "mode": "edit",
            "patches": 1,
        }
        result = runner.run("fix", {}, {})
        self.assertNotIn("write_or_diff_missing", result)
        self.assertEqual(result["patches"], 1)

    def test_run_propagates_agent_contract_error(self):
        runner, loop_mock = self._make_runner("ask")
        loop_mock.run.side_effect = AgentContractError(
            mode="ask", attempts=4, last_response="just prose"
        )
        with self.assertRaises(AgentContractError) as ctx:
            runner.run("q", {}, {})
        self.assertEqual(ctx.exception.mode, "ask")
        self.assertEqual(ctx.exception.attempts, 4)


class AgentContractErrorTests(unittest.TestCase):
    def test_error_carries_mode_attempts_and_snippet(self):
        err = AgentContractError(
            mode="edit", attempts=5, last_response="a" * 1000
        )
        self.assertEqual(err.mode, "edit")
        self.assertEqual(err.attempts, 5)
        # The message includes a 400-char snippet, not the full 1000.
        self.assertIn("a" * 100, str(err))
        self.assertIn("...", str(err))

    def test_error_without_last_response_omits_snippet(self):
        err = AgentContractError(mode="ask", attempts=3, last_response="")
        self.assertNotIn("Last response", str(err))


if __name__ == "__main__":
    unittest.main()
