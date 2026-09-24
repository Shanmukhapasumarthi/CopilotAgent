"""Logging setup that redacts secrets from log records."""

from __future__ import annotations

import logging
import re
from typing import Iterable

from app.config import get_settings

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(GROQ_API_KEY\s*[=:]\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(GEMINI_API_KEY\s*[=:]\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(API[_-]?KEY\s*[=:]\s*)(\S+)", re.IGNORECASE),
    re.compile(r"(gsk_[A-Za-z0-9]{8,})"),
    re.compile(r"(AIza[0-9A-Za-z\-_]{20,})"),
    re.compile(r"(sk-[A-Za-z0-9]{16,})"),
    re.compile(r"(Bearer\s+)([A-Za-z0-9\-\._~+/]+=*)", re.IGNORECASE),
)


def redact_secrets(text: str, extra_values: Iterable[str] = ()) -> str:
    """Replace known secret shapes and explicit values with [REDACTED]."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    for value in extra_values:
        if value and value.strip():
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


class SecretRedactingFilter(logging.Filter):
    """Scrub secrets from log messages and exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        extra = []
        try:
            key = get_settings().groq_api_key
            if key:
                extra.append(key)
        except Exception:
            pass

        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg, extra)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(str(v), extra) for k, v in record.args.items()
                }
            else:
                record.args = tuple(
                    redact_secrets(str(arg), extra) if not isinstance(arg, int | float)
                    else arg
                    for arg in record.args
                )
        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text, extra)
        return True


def configure_logging(level: str | None = None) -> logging.Logger:
    """Configure the codepilot logger once and return it."""
    logger = logging.getLogger("codepilot")
    if logger.handlers:
        if level:
            logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        return logger

    settings_level = level or get_settings().log_level
    logger.setLevel(getattr(logging, settings_level, logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    handler.addFilter(SecretRedactingFilter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    if name:
        return logging.getLogger(f"codepilot.{name}")
    return logging.getLogger("codepilot")
