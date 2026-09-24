"""Unit tests for configuration."""

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings, reset_settings_cache


def test_default_settings_do_not_require_a_key() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_model == "llama-3.3-70b-versatile"
    assert settings.max_iterations == 8
    assert settings.groq_api_key == ""


def test_require_llm_credentials_fails_without_key() -> None:
    settings = Settings(_env_file=None, groq_api_key="  ")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        settings.require_llm_credentials()


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="VERBOSE")


def test_temperature_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_temperature=3.5)


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_ITERATIONS", "4")
    reset_settings_cache()
    first = get_settings()
    monkeypatch.setenv("MAX_ITERATIONS", "9")
    second = get_settings()
    assert first is second
    assert first.max_iterations == 4
    reset_settings_cache()
