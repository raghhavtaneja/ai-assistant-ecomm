"""All runtime configuration, loaded once from environment variables (and `.env`).

Every key, model name, and path lives here so swapping a provider or model
is a config change, not a code hunt. Import `settings` everywhere else.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore" so unrelated variables in .env don't crash startup.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Empty default so tests and offline commands work without a key;
    # the LLM/embedding modules check for it at call time and fail clearly.
    gemini_api_key: str = ""
    chat_model: str = "gemini-3.8-flash"
    embedding_model: str = "gemini-embedding-2"

    database_path: Path = Path("data/app.db")
    log_level: str = "INFO"


settings = Settings()
