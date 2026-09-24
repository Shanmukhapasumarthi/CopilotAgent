"""Logging must never emit API keys."""

import logging
from io import StringIO

from app.config import Settings, reset_settings_cache
from app.logging_config import SecretRedactingFilter, configure_logging, redact_secrets


def test_redact_groq_key_shape() -> None:
    text = "using key gsk_abcdefghijklmnopqrstuvwxyz123456"
    assert "[REDACTED]" in redact_secrets(text)
    assert "gsk_abcdefgh" not in redact_secrets(text)


def test_redact_explicit_env_assignment() -> None:
    raw = "GROQ_API_KEY=super-secret-value"
    assert redact_secrets(raw) == "GROQ_API_KEY=[REDACTED]"


def test_log_filter_redacts_configured_key(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "literal-secret-token")
    reset_settings_cache()
    logger = configure_logging("INFO")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SecretRedactingFilter())
    logger.addHandler(handler)
    try:
        logger.info("loaded key literal-secret-token")
        output = stream.getvalue()
    finally:
        logger.removeHandler(handler)
        reset_settings_cache()
    assert "literal-secret-token" not in output
    assert "[REDACTED]" in output


def test_settings_object_does_not_show_key_in_logs() -> None:
    settings = Settings(_env_file=None, groq_api_key="abc123secret")
    assert "abc123secret" not in redact_secrets(str(settings), [settings.groq_api_key])
