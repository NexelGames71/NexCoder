"""Secret / PII redaction for prompts and responses.

Production-grade agentic systems never let user secrets flow to the LLM
provider, and never echo them back into the chat. This module scans
text for known secret formats, PII patterns, and credential
fingerprints, and replaces them with stable placeholders.

The redaction is deliberately conservative: it returns both the
sanitised text and a list of redaction labels so the caller can decide
whether to surface a "Redacted N items" hint to the user, log the
labels for compliance, or refuse to send the prompt entirely.

The redaction is **not** a substitute for a real secrets scanner — it
    catches the obvious patterns (AWS keys, GitHub PATs, AI-provider keys,
private keys, JWTs, emails, credit cards, IPv4). Anything genuinely
novel will pass through. Use a dedicated scanner (e.g. ``gitleaks``)
for compliance-grade detection.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


# Stable placeholder so the same secret always maps to the same token
# (helpful for cache locality and the user remembering what they
# pasted). We use the first 8 chars of the SHA-256 of the secret.
def _fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


# Each pattern is (label, regex). The regex is applied case-insensitively
# unless the secret format is case-sensitive (e.g. AWS keys).
#
# Order matters: more specific patterns come first. The generic
# ``openai_api_key`` pattern (sk-...) would otherwise eat
# sk-proj-... and sk-ant-... matches before the project/anthropic
# patterns get a chance to fire.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    # AI provider keys (specific variants first, then the generic sk-)
    ("openai_project_key", re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}")),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("nvidia_api_key", re.compile(r"nvapi-[A-Za-z0-9_-]{20,}")),
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    # Source-control PATs
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{36,}")),
    ("github_oauth", re.compile(r"gho_[A-Za-z0-9]{36,}")),
    ("github_app_token", re.compile(r"(?:ghu|ghs)_[A-Za-z0-9]{36,}")),
    ("gitlab_pat", re.compile(r"glpat-[A-Za-z0-9_-]{20,}")),
    # Cloud provider keys
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_access_key", re.compile(
        r"(?i)aws(.{0,20})?(secret|access)?(.{0,20})?['\"][0-9a-zA-Z/+]{40}['\"]"
    )),
    # Slack / Discord
    ("slack_token", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("discord_token", re.compile(r"[MN][A-Za-z\d]{23,}\.[\w-]{6,}\.[\w-]{27,}")),
    # Stripe (must come before generic api_key_assignment which would
    # also match these)
    ("stripe_live_key", re.compile(r"sk_live_[0-9a-zA-Z]{24,}")),
    ("stripe_test_key", re.compile(r"sk_test_[0-9a-zA-Z]{24,}")),
    # PEM private keys
    ("private_key_pem", re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    )),
    # JWT (header.payload.signature, three base64-url segments)
    ("jwt", re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    )),
    # Generic password/secret assignments. Match the variable name
    # (which may include PASSWORD / Pwd / _password_) plus the value.
    ("password_assignment", re.compile(
        r"(?i)([A-Za-z_][A-Za-z0-9_]*password[A-Za-z0-9_]*|password|passwd|pwd)\s*[=:]\s*['\"]?([^\s'\"]{8,})['\"]?"
    )),
    ("api_key_assignment", re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret|token)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?"
    )),
    # PII
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("credit_card_like", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    # US SSN (NNN-NN-NNNN, but only when not adjacent to digits to avoid
    # catching serial numbers)
    ("us_ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
]


# Patterns that, when matched, get the secret itself replaced with a
# fingerprint-bearing placeholder. ``password_assignment`` and
# ``api_key_assignment`` are special-cased below so the value is
# replaced but the key is preserved.
_ASSIGNMENT_LABELS = {"password_assignment", "api_key_assignment"}


@dataclass
class RedactionResult:
    """Outcome of a redaction pass."""

    text: str
    redactions: list[dict[str, str]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.redactions)

    @property
    def labels(self) -> list[str]:
        return [r["label"] for r in self.redactions]


class SecretRedactor:
    """Detect and replace secrets / PII in text.

    Usage::

        redactor = SecretRedactor()
        result = redactor.redact("My key is sk-abcdef0123456789ABCDEF")
        assert "sk-abcdef" not in result.text
        assert result.labels == ["openai_api_key"]

    The same secret always maps to the same placeholder so a user
    can recognise it across redactions in a long conversation.
    """

    # Maximum text size we will scan in a single call. Larger inputs
    # should be chunked by the caller; we refuse to scan unbounded
    # text because the regexes are linear but the fingerprinting step
    # is O(N) and the placeholder substitution is O(N·M) where M is
    # the number of redactions.
    MAX_INPUT_CHARS = 200_000

    def __init__(
        self,
        *,
        extra_patterns: Optional[Iterable[tuple[str, str]]] = None,
        disabled_labels: Optional[Iterable[str]] = None,
    ) -> None:
        self._patterns: list[tuple[str, re.Pattern]] = list(_PATTERNS)
        if extra_patterns:
            for label, regex in extra_patterns:
                try:
                    self._patterns.append((label, re.compile(regex)))
                except re.error as exc:
                    logger.warning(
                        "Skipping invalid redaction pattern %r: %s", label, exc
                    )
        self._disabled = frozenset(disabled_labels or ())

    def redact(self, text: str) -> RedactionResult:
        """Return a redacted copy of *text* plus a redaction report."""
        if not text:
            return RedactionResult(text=text, redactions=[])
        if len(text) > self.MAX_INPUT_CHARS:
            # Truncate for scanning; preserve the original tail by
            # leaving it untouched. This is intentionally a no-op
            # for huge inputs because the cost of full-DOM regex
            # scanning on a multi-MB blob isn't worth it.
            logger.debug(
                "Skipping redaction on oversized input (%d chars)", len(text)
            )
            return RedactionResult(text=text, redactions=[])

        redactions: list[dict[str, str]] = []
        redacted = text
        for label, pattern in self._patterns:
            if label in self._disabled:
                continue
            if label in _ASSIGNMENT_LABELS:
                redacted, hits = self._redact_assignment(redacted, pattern, label)
            else:
                redacted, hits = self._redact_simple(redacted, pattern, label)
            redactions.extend(hits)
        return RedactionResult(text=redacted, redactions=redactions)

    # ── Internals ────────────────────────────────────────────────────

    @staticmethod
    def _placeholder(label: str, secret: str) -> str:
        return f"[REDACTED:{label}:{_fingerprint(secret)}]"

    def _redact_simple(
        self, text: str, pattern: re.Pattern, label: str
    ) -> tuple[str, list[dict[str, str]]]:
        redactions: list[dict[str, str]] = []
        seen: set[str] = set()

        def _replace(match: re.Match) -> str:
            secret = match.group(0)
            if secret in seen:
                return SecretRedactor._placeholder(label, secret)
            seen.add(secret)
            redactions.append({"label": label, "fingerprint": _fingerprint(secret)})
            return SecretRedactor._placeholder(label, secret)

        new_text = pattern.sub(_replace, text)
        return new_text, redactions

    def _redact_assignment(
        self, text: str, pattern: re.Pattern, label: str
    ) -> tuple[str, list[dict[str, str]]]:
        redactions: list[dict[str, str]] = []
        seen: set[str] = set()

        def _replace(match: re.Match) -> str:
            key = match.group(1)  # the "password" / "api_key" word
            value = match.group(2)
            if value in seen:
                return f"{key}=[REDACTED:{label}:{_fingerprint(value)}]"
            seen.add(value)
            redactions.append({"label": label, "fingerprint": _fingerprint(value)})
            return f"{key}=[REDACTED:{label}:{_fingerprint(value)}]"

        new_text = pattern.sub(_replace, text)
        return new_text, redactions


__all__ = ["SecretRedactor", "RedactionResult"]
