"""Opt-in redaction for common secrets and personal identifiers in stored logs."""
from __future__ import annotations

import os
import re
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_NAMES = {
    "password", "passwd", "pwd", "secret", "clientsecret", "apikey",
    "accesstoken", "refreshtoken", "token", "authorization", "cookie",
    "setcookie", "sessionid",
}
_KEY_VALUE = re.compile(
    r"(?i)(?P<prefix>\b(?:password|passwd|pwd|secret|client[_-]?secret|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|token|authorization|cookie|set-cookie|session[_-]?id)\b"
    r"[\"']?\s*[:=]\s*)(?P<value>\"[^\"]*\"|'[^']*'|[^\r\n,;}\]\"']+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")


def redaction_enabled() -> bool:
    """Return whether opt-in stored-log redaction is enabled in this process."""
    return os.environ.get("LOGLENS_REDACT_SENSITIVE", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def redact_text(value: str) -> str:
    """Mask common key/value credentials, bearer tokens, and email addresses."""
    def replace_key_value(match: re.Match[str]) -> str:
        current = match.group("value")
        if current[:1] in {'"', "'"} and current[-1:] == current[:1]:
            quote = current[0]
            return f"{match.group('prefix')}{quote}{REDACTED}{quote}"
        return f"{match.group('prefix')}{REDACTED}"

    value = _KEY_VALUE.sub(replace_key_value, value)
    value = _BEARER.sub(f"Bearer {REDACTED}", value)
    return _EMAIL.sub(REDACTED, value)


def redact_value(value: Any, key: str | None = None) -> Any:
    """Recursively redact sensitive named fields and common patterns in text."""
    if key is not None:
        normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized_key in _SENSITIVE_NAMES and value not in (None, ""):
            return REDACTED
    if isinstance(value, dict):
        return {name: redact_value(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a redacted copy; never mutate parsed input held by the caller."""
    return {key: redact_value(value, str(key)) for key, value in record.items()}
