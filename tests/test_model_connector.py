import unittest

from nexcoder.agent.model_connector import ModelConnector


class ModelConnectorContextTests(unittest.TestCase):
    def test_compaction_keeps_system_and_latest_contract(self):
        messages = [
            {"role": "system", "content": "system rules" * 200},
            {"role": "user", "content": "old project context" * 1000},
            {"role": "assistant", "content": "old observation" * 500},
            {"role": "user", "content": "LATEST CONTRACT: read package.json"},
        ]

        fitted = ModelConnector._fit_messages(messages, 600)

        self.assertEqual(fitted[0]["role"], "system")
        self.assertIn("LATEST CONTRACT", fitted[-1]["content"])
        used = sum(ModelConnector._estimated_tokens(item["content"]) + 6 for item in fitted)
        self.assertLessEqual(used, 600)

    def test_messages_under_budget_are_unchanged(self):
        messages = [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "question"},
        ]

        self.assertEqual(ModelConnector._fit_messages(messages, 1000), messages)


if __name__ == "__main__":
    unittest.main()
