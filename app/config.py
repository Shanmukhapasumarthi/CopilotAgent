"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secrets stay in the environment, never in code."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    groq_api_key: str = Field(default="", description="Groq API key")
    llm_model: str = Field(default="llama-3.3-70b-versatile")
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_iterations: int = Field(default=8, ge=1, le=20)
    log_level: str = Field(default="INFO")
    sandbox_timeout_seconds: int = Field(default=30, ge=1, le=120)
    sandbox_memory: str = Field(default="256m")
    sandbox_cpus: str = Field(default="0.5")
    sandbox_pids: int = Field(default=64, ge=8, le=256)
    max_request_chars: int = Field(default=8000, ge=200, le=50000)
    max_source_chars: int = Field(default=20000, ge=500, le=200000)
    graph_recursion_limit: int = Field(default=48, ge=20, le=200)
    
    # LangSmith observability (optional)
    langchain_tracing_v2: str = Field(default="false", description="Enable LangSmith tracing")
    langchain_api_key: str = Field(default="", description="LangSmith API key")
    langchain_project: str = Field(default="codepilot-agent", description="LangSmith project name")
    langchain_endpoint: str = Field(default="https://api.smith.langchain.com", description="LangSmith API endpoint")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return level

    def require_llm_credentials(self) -> None:
        """Raise if a live LLM call is requested without a key."""
        if not self.groq_api_key.strip():
            raise RuntimeError(
                "GROQ_API_KEY is missing. Copy .env.example to .env and set the key."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test helper: force the next get_settings() call to reload env."""
    get_settings.cache_clear()
