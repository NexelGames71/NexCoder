import unittest

from nexcoder.agent.intent_router import classify_prompt, classify_task_type


class IntentRouterTests(unittest.TestCase):
    def test_agent_stack_question_is_read_only(self):
        prompt = "what are the stack"

        self.assertEqual(classify_prompt(prompt, "agent"), "read")
        self.assertEqual(classify_task_type(prompt, "agent"), "question")

    def test_agent_implementation_request_remains_write_capable(self):
        prompt = "add a countdown in the center of index.html"

        self.assertEqual(classify_prompt(prompt, "agent"), "write")
        self.assertEqual(classify_task_type(prompt, "agent"), "implement")


if __name__ == "__main__":
    unittest.main()
