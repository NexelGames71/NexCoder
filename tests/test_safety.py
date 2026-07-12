"""Tests for the SafetyChecker: command blocklist, sensitive files, secret detection."""

import unittest

from nexcoder.agent.safety import SafetyChecker


class CommandBlocklistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s = SafetyChecker()

    def test_blocks_rm_rf_root(self):
        self.assertTrue(self.s.is_command_blocked("rm -rf /"))

    def test_blocks_rm_rf_root_with_star(self):
        self.assertTrue(self.s.is_command_blocked("rm -rf /*"))

    def test_blocks_del_recurse_root(self):
        self.assertTrue(self.s.is_command_blocked("del /s /q C:\\Windows"))

    def test_blocks_format_drive(self):
        self.assertTrue(self.s.is_command_blocked("format C:"))

    def test_blocks_diskpart(self):
        self.assertTrue(self.s.is_command_blocked("diskpart"))

    def test_blocks_dd_to_dev(self):
        self.assertTrue(self.s.is_command_blocked("dd if=foo of=/dev/sda"))

    def test_blocks_fork_bomb(self):
        self.assertTrue(self.s.is_command_blocked(":(){ :|:& };:"))

    def test_blocks_redirect_to_dev_sda(self):
        self.assertTrue(self.s.is_command_blocked("echo x > /dev/sda"))

    def test_blocks_chmod_777_root(self):
        self.assertTrue(self.s.is_command_blocked("chmod -R 777 /"))

    def test_allows_benign_commands(self):
        for cmd in ("echo hello", "ls -la", "git status", "npm install", "pytest -q"):
            self.assertFalse(self.s.is_command_blocked(cmd), f"false positive: {cmd}")

    def test_blocks_case_insensitively(self):
        self.assertTrue(self.s.is_command_blocked("RM -RF /"))


class SensitiveFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s = SafetyChecker()

    def test_env_file_is_sensitive(self):
        self.assertTrue(self.s.is_sensitive_file(".env"))
        self.assertTrue(self.s.is_sensitive_file(".env.production"))
        self.assertTrue(self.s.is_sensitive_file("config/.env.local"))

    def test_pem_files_are_sensitive(self):
        self.assertTrue(self.s.is_sensitive_file("cert.pem"))
        self.assertTrue(self.s.is_sensitive_file("path/to/key.pem"))

    def test_key_files_are_sensitive(self):
        self.assertTrue(self.s.is_sensitive_file("private.key"))
        self.assertTrue(self.s.is_sensitive_file("path/id_rsa"))

    def test_credentials_files_are_sensitive(self):
        self.assertTrue(self.s.is_sensitive_file("aws_credentials"))

    def test_secrets_files_are_sensitive(self):
        self.assertTrue(self.s.is_sensitive_file("secrets.json"))

    def test_docker_configs_are_sensitive(self):
        self.assertTrue(self.s.is_sensitive_file("docker-compose.yml"))
        self.assertTrue(self.s.is_sensitive_file("Dockerfile"))

    def test_yaml_configs_are_sensitive(self):
        self.assertTrue(self.s.is_sensitive_file("deploy.yml"))
        self.assertTrue(self.s.is_sensitive_file("config.yaml"))

    def test_benign_files_are_not_sensitive(self):
        for path in ("main.py", "index.tsx", "README.md", "src/utils.py"):
            self.assertFalse(self.s.is_sensitive_file(path), f"false positive: {path}")


class SecretDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s = SafetyChecker()

    def test_detects_api_key(self):
        secrets = self.s.detect_secrets("api_key = abcdefghijklmnopqrstuv")
        self.assertIn("API Key", secrets)

    def test_detects_password(self):
        secrets = self.s.detect_secrets("password=verysecretvalue")
        self.assertIn("Password", secrets)

    def test_detects_aws_key(self):
        # A real AWS access key id is 20 characters total: AKIA + 16.
        secrets = self.s.detect_secrets("AKIAIOSFODNN7EXAMPLEXX")
        self.assertIn("AWS Key", secrets)

    def test_detects_private_key(self):
        secrets = self.s.detect_secrets("-----BEGIN RSA PRIVATE KEY-----")
        self.assertIn("Private Key", secrets)

    def test_clean_text_has_no_secrets(self):
        secrets = self.s.detect_secrets("this is just some text without any secrets")
        self.assertEqual(secrets, [])


class PatchSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.s = SafetyChecker()

    def test_safe_patch_scores_low(self):
        report = self.s.check_patch_safety([{
            "file": "src/app.py",
            "content": "x = 1\n",
        }])
        self.assertTrue(report["safe"])
        self.assertEqual(report["risk_score"], 0)
        self.assertFalse(report["requires_approval"])

    def test_sensitive_file_bumps_score(self):
        report = self.s.check_patch_safety([{
            "file": ".env",
            "content": "x = 1\n",
        }])
        self.assertGreater(report["risk_score"], 0)
        self.assertTrue(report["requires_approval"])
        self.assertIn(".env", report["sensitive_files"])

    def test_large_patch_requires_approval(self):
        big_content = "x = 1\n" * 200
        report = self.s.check_patch_safety([{
            "file": "big.py",
            "content": big_content,
        }])
        self.assertTrue(report["requires_approval"])

    def test_delete_action_bumps_score(self):
        report = self.s.check_patch_safety([{
            "file": "x.py",
            "content": "",
            "action": "delete",
        }])
        self.assertGreater(report["risk_score"], 0)

    def test_secret_in_content_bumps_score(self):
        report = self.s.check_patch_safety([{
            "file": "src/config.py",
            "content": "API_KEY = abcdef0123456789abcdef\n",
        }])
        self.assertGreater(report["risk_score"], 0)


if __name__ == "__main__":
    unittest.main()