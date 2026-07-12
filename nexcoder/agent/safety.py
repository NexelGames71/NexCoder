"""Safety — command blocklist, sensitive file detection, approval matrix."""

import os
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Commands that should NEVER be executed automatically. All patterns
# are matched case-insensitively against the lowercased command.
BLOCKED_COMMANDS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+/\*",
    r"del\s+/s\s+/q\s+c:\\",
    r"rd\s+/s\s+/q\s+c:\\",
    r"format\s+[a-z]:",
    r"diskpart",
    r"mkfs\.",
    r"dd\s+if=.*of=/dev/",
    r":\(\)\s*\{[^}]*\|[^}]*&\s*\}\s*;",  # classic bash fork bomb
    r">\s*/dev/sda",
    r"chmod\s+-r\s+777\s+/",
]

# File patterns that are considered sensitive. Matched against the
# lowercased basename + relative path, so we don't worry about case.
SENSITIVE_PATTERNS = [
    r"\.env($|\.)",             # .env, .env.local, .env.production
    r"\.pem$",                  # SSL certificates
    r"\.key$",                  # Private keys
    r"id_rsa",                  # SSH keys
    r"credentials",             # Credentials files
    r"secrets?\.",              # Secrets files
    r"auth",                    # Auth modules
    r"payment",                 # Payment code
    r"billing",                 # Billing code
    r"migration",              # Database migrations
    r"docker-compose",         # Docker configs
    r"dockerfile",             # Docker configs
    r"\.ya?ml$",                # YAML configs (CI/CD, etc.)
]

# Actions that always require user approval
APPROVAL_REQUIRED = {
    "delete_file",
    "install_package",
    "network_request",
    "modify_env",
    "modify_auth",
    "modify_payment",
    "run_migration",
    "git_push",
    "git_commit",
    "large_patch",       # > 100 lines changed
    "multiple_files",    # > 3 files changed
}


class SafetyChecker:
    """Validates commands and patches for safety before execution."""

    def is_command_blocked(self, command: str) -> bool:
        """Check if a command matches the blocklist."""
        command_lower = command.lower().strip()
        for pattern in BLOCKED_COMMANDS:
            if re.search(pattern, command_lower):
                logger.warning(f"Blocked dangerous command: {command}")
                return True
        return False

    def is_sensitive_file(self, file_path: str) -> bool:
        """Check if a file path matches sensitive patterns."""
        basename = os.path.basename(file_path).lower()
        rel_path = file_path.replace("\\", "/").lower()

        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, basename) or re.search(pattern, rel_path):
                return True
        return False

    def check_patch_safety(self, patches: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze a set of patches for safety concerns.

        Returns:
            {
                "safe": bool,
                "requires_approval": bool,
                "reasons": ["reason1", ...],
                "risk_score": 0-10,
                "sensitive_files": ["file1", ...],
            }
        """
        reasons: list[str] = []
        sensitive_files: list[str] = []
        risk_score = 0
        requires_approval = False

        total_lines_changed = 0
        files_affected = len(patches)

        for patch in patches:
            file_path = patch.get("file", "")
            content = patch.get("content", "") or patch.get("diff", "")

            # Count lines changed
            lines = content.count("\n") + 1
            total_lines_changed += lines

            # Check sensitive files
            if self.is_sensitive_file(file_path):
                sensitive_files.append(file_path)
                risk_score += 3
                requires_approval = True
                reasons.append(f"Modifies sensitive file: {os.path.basename(file_path)}")

            # Check for deletions
            if patch.get("action") == "delete":
                risk_score += 2
                requires_approval = True
                reasons.append(f"Deletes file: {os.path.basename(file_path)}")

            # Check for secrets in content
            secrets = self.detect_secrets(content)
            if secrets:
                risk_score += 5
                reasons.append(f"Potential secrets detected in output ({len(secrets)} found)")

        # Large patch check
        if total_lines_changed > 100:
            risk_score += 2
            requires_approval = True
            reasons.append(f"Large change: {total_lines_changed} lines across {files_affected} files")

        # Multiple files check
        if files_affected > 3:
            risk_score += 1
            requires_approval = True
            reasons.append(f"Modifies {files_affected} files")

        return {
            "safe": risk_score < 8,
            "requires_approval": requires_approval or risk_score > 0,
            "reasons": reasons,
            "risk_score": min(risk_score, 10),
            "sensitive_files": sensitive_files,
            "total_lines_changed": total_lines_changed,
            "files_affected": files_affected,
        }

    def detect_secrets(self, text: str) -> list[str]:
        """Detect potential secrets/credentials in text."""
        patterns = [
            (r'(?:api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})', "API Key"),
            (r'(?:password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']{8,})', "Password"),
            (r'(?:secret|token)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})', "Secret/Token"),
            (r'AKIA[0-9A-Z]{16}', "AWS Key"),
            (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private Key"),
        ]

        found: list[str] = []
        for pattern, label in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                found.append(label)

        return found
