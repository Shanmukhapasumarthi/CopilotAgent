"""Phase 1 smoke check: load config and logging without calling the LLM."""

from app.config import get_settings
from app.logging_config import configure_logging, get_logger


def main() -> None:
    configure_logging()
    log = get_logger("bootstrap")
    settings = get_settings()
    key_present = bool(settings.groq_api_key.strip())
    log.info(
        "Foundation OK | model=%s | max_iterations=%s | api_key_present=%s",
        settings.llm_model,
        settings.max_iterations,
        key_present,
    )
    print("Foundation loaded successfully.")
    print(f"  model: {settings.llm_model}")
    print(f"  max_iterations: {settings.max_iterations}")
    print(f"  api_key_present: {key_present}")


if __name__ == "__main__":
    main()
