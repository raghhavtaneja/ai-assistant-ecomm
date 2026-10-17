"""The shared Gemini client, used by app/llm.py and app/embeddings.py only."""

from functools import cache

from google import genai
from google.genai import types

from app.config import settings


class MissingApiKeyError(RuntimeError):
    pass


@cache  # one client per process, so HTTP connections are reused
def get_client() -> genai.Client:
    if not settings.gemini_api_key:
        raise MissingApiKeyError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return genai.Client(
        api_key=settings.gemini_api_key,
        # The SDK retries rate limits (429) and server errors with exponential backoff
        # (2s, 4s, 8s, ... capped), so callers don't need their own retry loops.
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=settings.llm_retry_attempts,
                initial_delay=2.0,
                max_delay=settings.llm_retry_max_delay_seconds,
            )
        ),
    )
