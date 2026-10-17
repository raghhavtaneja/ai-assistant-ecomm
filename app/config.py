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
    # 768 keeps vectors small (3 KB each) with little quality loss vs the 3072 default.
    # Changing it means re-indexing: old and new vectors can't be compared.
    embedding_dimensions: int = 768
    embedding_batch_size: int = 100
    # Gemini's free tier counts every embedded text as a request (100/min), so a store
    # index can hit 429s. Backing off up to a minute rides out one quota window.
    llm_retry_attempts: int = 6
    llm_retry_max_delay_seconds: float = 60.0

    database_path: Path = Path("data/app.db")
    log_level: str = "INFO"

    # Crawler politeness: identify ourselves, pause between requests, cap the work.
    crawl_user_agent: str = "AISalesAssistantBot/0.1"
    crawl_delay_seconds: float = 0.5
    crawl_max_pages: int = 200
    http_timeout_seconds: float = 20.0

    # Retrieval tuning. Small enough to be specific, big enough to keep a FAQ answer whole.
    chunk_max_chars: int = 1000
    top_products: int = 5
    top_chunks: int = 3
    # Below this cosine score a match is treated as unrelated. On Minimalist, relevant hits
    # scored 0.69-0.77 and off-topic ones 0.56-0.63. Tune with the evals, not by feel.
    min_score: float = 0.65


settings = Settings()
