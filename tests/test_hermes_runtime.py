import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from nexcoder.agent.errors import ModelStreamError
from nexcoder.agent.hermes_runtime import HermesAgentLoop


class _TinyProfile:
    """Minimal stand-in for a ModeProfile.

    The runtime test only needs ``max_turns`` / ``max_retries`` /
    ``allowed_tools`` / ``system_prompt`` / ``extra_instructions`` â€”
    a real ModeProfile carries more, but the loop only ``getattr``s these.
    """

    max_turns = 2
    max_retries = 1
    allowed_tools = ("read_file", "list_directory", "search_grep", "load_skill", "write_file", "run_command")
    system_prompt = "test system"
    extra_instructions = ""


class HermesAgentLoopTests(unittest.TestCase):
    def test_agent_profile_question_cannot_inherit_implement_task_type(self):
        class _AgentProfile(_TinyProfile):
            name = "agent"
            task_type = "implement"
            max_turns = 3

        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            loop._model = MagicMock()
            loop._model.chat_completion.side_effect = [
                iter(['<tool_call name="list_directory">{"path":"."}</tool_call>']),
                iter([
                    '<final_answer>{"type":"final_answer","title":"Stack",'
                    '"summary":"No stack files were found.","evidence":[],'
                    '"files_used":[],"next_steps":[]}</final_answer>'
                ]),
            ]

            result = loop.run(
                "what are the stack",
                {
                    "project_path": tmp,
                    "_mode_profile": _AgentProfile(),
                },
                {},
            )

        self.assertEqual(result["task_type"], "question")
        self.assertEqual(result["patches"], 0)
        self.assertFalse(Path(tmp, "index.html").exists())

    def test_stops_model_loop_when_all_explicit_files_are_staged(self):
        class _Profile(_TinyProfile):
            max_turns = 8
            task_type = "implement"

        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            loop._model = MagicMock()
            loop._model.chat_completion.side_effect = [
                iter(['<tool_call name="list_directory">{"path":"."}</tool_call>']),
                iter([
                    '<tool_call name="write_file">'
                    '{"path":"index.html","content":"<!doctype html><h1>Status</h1>"}'
                    '</tool_call>'
                    '<tool_call name="write_file">'
                    '{"path":"README.md","content":"# Status page"}'
                    '</tool_call>'
                ]),
                iter(["This third model turn should never be requested."]),
            ]

            result = loop.run(
                "Create index.html and README.md",
                {
                    "project_path": tmp,
                    "_mode_profile": _Profile(),
                    "task_type": "implement",
                },
                {},
            )

        self.assertEqual(result["patches"], 2)
        self.assertEqual(loop._model.chat_completion.call_count, 2)

    def test_moving_entry_file_rebases_staged_asset_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            timeline: list[dict] = []
            result = loop.run(
                "Put the index file into a src folder",
                {
                    "project_path": tmp,
                    "_mode_profile": _TinyProfile(),
                    "task_type": "implement",
                    "pending_changes": [
                        {
                            "file": "index.html",
                            "action": "create",
                            "content": (
                                '<!doctype html><link rel="stylesheet" '
                                'href="assets/css/styles.css">'
                                '<script src="assets/js/script.js"></script>'
                            ),
                        },
                        {"file": "assets/css/styles.css", "action": "create", "content": "body {}"},
                        {"file": "assets/js/script.js", "action": "create", "content": "console.log('ok')"},
                    ],
                },
                {"on_timeline": timeline.append},
            )

        patches = {patch["file"]: patch for patch in result["patchset"]}
        self.assertNotIn("index.html", patches)
        self.assertIn("src/index.html", patches)
        self.assertIn('href="../assets/css/styles.css"', patches["src/index.html"]["content"])
        self.assertIn('src="../assets/js/script.js"', patches["src/index.html"]["content"])
        self.assertTrue(any(item["tool"] == "create_directory" for item in timeline))
        self.assertTrue(any(item["tool"] == "move_path" for item in timeline))

    def test_extracts_tool_calls_from_xml(self):
        loop = HermesAgentLoop(project_root=Path("."))
        text = (
            'I will inspect the app.\n'
            '<tool_call name="read_file">{"path": "src/app.py"}</tool_call>\n'
            '<tool_call name="run_command">{"command": "pytest"}</tool_call>'
        )
        calls = loop.extract_tool_calls(text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["name"], "read_file")
        self.assertEqual(calls[1]["name"], "run_command")

    def test_detects_python_verification_command(self):
        loop = HermesAgentLoop(project_root=Path("."))
        command = loop.detect_verification_command("", ["src/app.py"])
        self.assertEqual(command, "python -m pytest")

    def test_detects_build_command_for_node_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_json = Path(tmp) / "package.json"
            package_json.write_text("{}", encoding="utf-8")
            loop = HermesAgentLoop(project_root=Path(tmp))
            command = loop.detect_verification_command(str(package_json), ["src/index.ts"])
        self.assertEqual(command, "npm run build")

    def test_static_html_project_does_not_require_npm(self):
        loop = HermesAgentLoop(project_root=Path("."))
        command = loop.detect_verification_command("", ["index.html"])
        self.assertNotEqual(command, "npm run build")
        self.assertIn("index.html", command)
        self.assertIn("verified files", command)

    def test_extracts_files_inside_named_folder(self):
        loop = HermesAgentLoop(project_root=Path("."))
        prompt = """Create a new folder named:

game-site

Inside that folder, create these files:
index.html
styles.css
script.js
README.md

Website requirements:
- responsive
"""
        self.assertEqual(
            loop.extract_requested_files(prompt),
            [
                "game-site/index.html",
                "game-site/styles.css",
                "game-site/script.js",
                "game-site/README.md",
            ],
        )

    def test_extracts_sentence_final_requested_file(self):
        loop = HermesAgentLoop(project_root=Path("."))
        prompt = "Create index.html, styles.css, script.js, and README.md."

        self.assertEqual(
            loop.extract_requested_files(prompt),
            ["index.html", "styles.css", "script.js", "README.md"],
        )

    def test_recovers_unambiguous_fenced_code_as_file_write(self):
        loop = HermesAgentLoop(project_root=Path("."))
        calls = loop.recover_fenced_write_calls(
            "```html\n<!doctype html><title>Recovered</title>\n```",
            ["index.html", "styles.css"],
            set(),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].tool, "write_file")
        self.assertEqual(calls[0].args["path"], "index.html")
        self.assertIn("Recovered", calls[0].args["content"])

    def test_recovers_plain_markdown_from_isolated_file_turn(self):
        call = HermesAgentLoop.recover_plain_requested_file(
            "# Product page\n\nSetup and usage notes.",
            "README.md",
        )

        self.assertIsNotNone(call)
        self.assertEqual(call.tool, "write_file")
        self.assertEqual(call.args["path"], "README.md")

    def test_does_not_recover_explanatory_prose_as_source_file(self):
        call = HermesAgentLoop.recover_plain_requested_file(
            "I created the requested file and it is ready.",
            "script.js",
        )

        self.assertIsNone(call)

    def test_frontend_quality_finds_alpha_level_output(self):
        findings = HermesAgentLoop.frontend_quality_findings(
            "Build a dark responsive website with a working theme toggle",
            {
                "index.html": "<h2>Product 1</h2><p>Description of Product 1.</p>",
                "styles.css": "body { background-color: #f4f4f4; }",
                "script.js": "button.addEventListener('click', () => document.body.classList.toggle('dark-theme'));",
            },
        )
        self.assertTrue(any("media query" in finding for finding in findings))
        self.assertTrue(any("dark visual" in finding for finding in findings))
        self.assertTrue(any("state class" in finding for finding in findings))
        self.assertTrue(any("placeholder" in finding for finding in findings))


class HermesStreamingTests(unittest.TestCase):
    """The loop must stream the model's prose to ``on_chunk`` as it arrives.

    The user sees status updates (tool activity) but the response text
    is the *only* thing that turns an agentic runner from "doing stuff"
    into "answering a question". The pre-refactor code that swallowed
    chunks was a regression â€” this test pins the live-streaming contract.
    """

    @staticmethod
    def _turn_response(chunks: list[str]):
        """Return a fresh iterator that yields ``chunks`` then stops."""
        return iter(chunks)

    def _patch_loop(self, loop: HermesAgentLoop, turn_responses: list[list[str]]) -> None:
        """Make the model return a different response on each turn.

        ``turn_responses[i]`` is the list of chunks the model streams
        on turn ``i``. When the list is exhausted the mock raises
        StopIteration, which terminates the loop.
        """
        loop._model = MagicMock()
        call_idx = {"n": 0}

        def fake_completion(*_args, **_kwargs):
            idx = call_idx["n"]
            call_idx["n"] += 1
            if idx >= len(turn_responses):
                raise StopIteration("model mock exhausted")
            return self._turn_response(turn_responses[idx])

        loop._model.chat_completion.side_effect = fake_completion

    def test_prose_chunks_are_streamed_to_on_chunk(self):
        loop = HermesAgentLoop(project_root=Path("."))
        streamed: list[str] = []
        callbacks = {"on_chunk": streamed.append, "on_status": lambda s, m: None}

        # Turn 1: model announces intent + emits a tool call.
        # Turn 2: after seeing the tool error, model emits a final prose
        # answer that should land in the chat. We cap max_turns at 2 so
        # the "prose on last turn" early-exit branch fires.
        self._patch_loop(loop, [
            [
                "I will read the file.\n",
                '<tool_call name="read_file">{"path": "x.py"}</tool_call>',
            ],
            ["Here is the answer."],
        ])

        with patch.object(HermesAgentLoop, "_read_file", return_value='{"success": false, "error": "missing"}'):
            # Use a tiny profile so the final-turn prose branch fires on
            # the second turn rather than waiting for turn 7 of 8.
            context = {
                "project_path": str(Path(".").resolve()),
                "_mode_profile": _TinyProfile(),
            }
            result = loop.run("read x.py", context, callbacks)

        joined = "".join(streamed)
        # The model prose must reach the chat stream â€” this is the
        # regression the user reported.
        self.assertIn("Here is the answer", joined, f"model prose never streamed; got: {joined!r}")
        # The renderer also needs the same prose in the result payload.
        self.assertIn("Here is the answer", result.get("response", ""))

    def test_tool_call_xml_is_not_leaked_into_prose_stream(self):
        """When chunks include tool XML, the XML itself should not be streamed.

        We don't want raw ``<tool_call name="read_file">...`` XML in the
        chat. The loop parses the XML and dispatches the tool; the prose
        portion is what the user should see.
        """
        loop = HermesAgentLoop(project_root=Path("."))
        streamed: list[str] = []
        callbacks = {"on_chunk": streamed.append, "on_status": lambda s, m: None}

        self._patch_loop(loop, [
            [
                "Let me check.\n",
                '<tool_call name="read_file">{"path": "x.py"}</tool_call>',
            ],
            ["Done."],
        ])

        with patch.object(HermesAgentLoop, "_read_file", return_value='{"success": false, "error": "missing"}'):
            context = {
                "project_path": str(Path(".").resolve()),
                "_mode_profile": _TinyProfile(),
            }
            loop.run("read x.py", context, callbacks)

        joined = "".join(streamed)
        # Prose is streamed, but raw tool XML is not shown to the user.
        self.assertNotIn("<tool_call", joined, f"raw tool XML leaked into chat stream: {joined!r}")
        self.assertIn("Let me check.", joined)

    def test_implement_task_retries_empty_xml_until_write_file(self):
        """Implement tasks must not finish after prose plus an empty XML fence.

        This reproduces the Spinner failure: the model inspected the empty
        folder, then said it would call ``write_file`` but emitted an empty
        `````xml`` fence. The runtime should retry and only finish after a real
        ``write_file`` tool call creates a pending patch.
        """

        class _ImplementProfile(_TinyProfile):
            max_turns = 3
            max_retries = 2
            task_type = "implement"

        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            streamed: list[str] = []
            diffs: list[dict] = []
            statuses: list[tuple[str, str]] = []
            callbacks = {
                "on_chunk": streamed.append,
                "on_diff": diffs.append,
                "on_status": lambda s, m: statuses.append((s, m)),
            }
            self._patch_loop(loop, [
                ['<tool_call name="list_directory">{"path": "."}</tool_call>'],
                ["I will create the file now.\n\n```xml\n\n```"],
                [
                    '<tool_call name="write_file">'
                    '{"path": "index.html", "content": "<!DOCTYPE html><html><body><div class=\\"spinner\\"></div></body></html>"}'
                    "</tool_call>"
                ],
            ])

            result = loop.run(
                "i want you to build an html web page with a spinning object",
                {
                    "project_path": tmp,
                    "_mode_profile": _ImplementProfile(),
                    "task_type": "implement",
                },
                callbacks,
            )

            self.assertEqual(result.get("patches"), 1)
            self.assertEqual(len(diffs), 1)
            self.assertEqual(diffs[0]["file"], "index.html")
            self.assertFalse((Path(tmp) / "index.html").exists())
            self.assertTrue(any(status == "retrying" for status, _ in statuses))
            self.assertNotIn("```xml", "".join(streamed))

    def test_model_stream_error_retries_same_agent_turn(self):
        """A broken local stream should retry before the agent task fails."""

        class _ImplementProfile(_TinyProfile):
            max_turns = 2
            max_retries = 1
            task_type = "implement"

        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            loop._model = MagicMock()
            responses = [
                ModelStreamError("peer closed stream"),
                ['<tool_call name="list_directory">{"path": "."}</tool_call>'],
                [
                    '<tool_call name="write_file">'
                    '{"path": "index.html", "content": "<!DOCTYPE html><html><body>ok</body></html>"}'
                    "</tool_call>"
                ],
            ]

            def fake_completion(*_args, **_kwargs):
                item = responses.pop(0)
                if isinstance(item, Exception):
                    raise item
                return iter(item)

            loop._model.chat_completion.side_effect = fake_completion
            statuses: list[tuple[str, str]] = []
            diffs: list[dict] = []

            result = loop.run(
                "build an html page",
                {
                    "project_path": tmp,
                    "_mode_profile": _ImplementProfile(),
                    "task_type": "implement",
                },
                {
                    "on_status": lambda s, m: statuses.append((s, m)),
                    "on_diff": diffs.append,
                },
            )

            self.assertEqual(result.get("patches"), 1)
            self.assertEqual(len(diffs), 1)
            self.assertTrue(
                any("Model stream interrupted" in message for _, message in statuses)
            )

    def test_implement_task_stages_every_requested_file_before_review(self):
        class _MultiFileProfile(_TinyProfile):
            max_turns = 6
            max_retries = 2
            task_type = "implement"

        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            diffs: list[dict] = []
            self._patch_loop(loop, [
                ['<tool_call name="list_directory">{"path":"."}</tool_call>'],
                [
                    '<tool_call name="write_file">'
                    '{"path":"index.html","content":"<!doctype html><link rel=\\"stylesheet\\" href=\\"styles.css\\">"}'
                    '</tool_call>'
                ],
                ["All done."],
                [
                    '<tool_call name="write_file">'
                    '{"path":"styles.css","content":"body { background: #111; color: white; }"}'
                    '</tool_call>'
                ],
                ["Both requested files are staged and ready for review."],
                ["Quality review complete. Both files satisfy the task."],
            ])

            result = loop.run(
                "Create index.html and styles.css for a polished website",
                {
                    "project_path": tmp,
                    "_mode_profile": _MultiFileProfile(),
                    "task_type": "implement",
                },
                {"on_diff": diffs.append},
            )

            self.assertEqual(result.get("patches"), 2)
            self.assertFalse(result.get("incomplete"))
            self.assertEqual([diff["file"] for diff in diffs], ["index.html", "styles.css"])
            self.assertFalse((Path(tmp) / "index.html").exists())
            self.assertFalse((Path(tmp) / "styles.css").exists())

    def test_turn_budget_recovers_every_explicit_deliverable(self):
        class _RecoveryProfile(_TinyProfile):
            max_turns = 2
            max_retries = 1
            task_type = "implement"

        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            diffs: list[dict] = []
            self._patch_loop(loop, [
                ['<tool_call name="list_directory">{"path":"."}</tool_call>'],
                [
                    '<tool_call name="write_file">'
                    '{"path":"index.html","content":"<!doctype html><link rel=\\"stylesheet\\" href=\\"styles.css\\"><script src=\\"script.js\\"></script>"}'
                    '</tool_call>'
                ],
                ["```css\nbody { background: #111; color: white; }\n```"],
                ["```javascript\ndocument.addEventListener('DOMContentLoaded', () => {});\n```"],
                ["```markdown\n# Product page\n\nStatic product page documentation.\n```"],
            ])

            result = loop.run(
                "Create index.html, styles.css, script.js, and README.md.",
                {
                    "project_path": tmp,
                    "_mode_profile": _RecoveryProfile(),
                    "task_type": "implement",
                },
                {"on_diff": diffs.append},
            )

            self.assertTrue(result.get("success"))
            self.assertFalse(result.get("incomplete"))
            self.assertEqual(result.get("patches"), 4)
            self.assertEqual(
                [diff["file"] for diff in diffs],
                ["index.html", "styles.css", "script.js", "README.md"],
            )

    def test_unresolved_quality_findings_block_completion(self):
        class _QualityProfile(_TinyProfile):
            max_turns = 2
            max_retries = 1
            task_type = "implement"

        placeholder = "<!doctype html><h2>Product 1</h2><p>Lorem ipsum</p>"
        write_call = (
            '<tool_call name="write_file">'
            '{"path":"index.html","content":"<!doctype html><h2>Product 1</h2><p>Lorem ipsum</p>"}'
            '</tool_call>'
        )

        with tempfile.TemporaryDirectory() as tmp:
            loop = HermesAgentLoop(project_root=Path(tmp))
            self._patch_loop(loop, [
                ['<tool_call name="list_directory">{"path":"."}</tool_call>'],
                [write_call],
                [f"```html\n{placeholder}\n```"],
                [f"```html\n{placeholder}\n```"],
                [f"```html\n{placeholder}\n```"],
            ])

            result = loop.run(
                "Build an HTML website in index.html with realistic product copy.",
                {
                    "project_path": tmp,
                    "_mode_profile": _QualityProfile(),
                    "task_type": "implement",
                },
                {},
            )

            self.assertFalse(result.get("success"))
            self.assertTrue(result.get("quality_findings"))
            self.assertIn("quality review did not pass", result.get("response", ""))


if __name__ == "__main__":
    unittest.main()

