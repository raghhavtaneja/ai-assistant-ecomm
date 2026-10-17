"""Chat completions. The only module that knows which chat model provider we use.

Takes a system prompt and provider-neutral Messages, returns plain text.
To switch providers, rewrite this file; app/chat.py doesn't change.
"""

from collections.abc import Iterator

from google.genai import errors, types

from app.config import settings
from app.gemini import get_client
from app.models import Message


class LLMError(RuntimeError):
    pass


def _to_gemini(messages: list[Message]) -> list[types.Content]:
    # Gemini calls the assistant role "model".
    return [
        types.Content(
            role="model" if m.role == "assistant" else "user",
            parts=[types.Part(text=m.content)],
        )
        for m in messages
    ]


def _config(system: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=settings.chat_max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_level=settings.chat_thinking_level),
    )


def stream(system: str, messages: list[Message]) -> Iterator[str]:
    """Yield the reply in pieces as the model produces them."""
    try:
        response = get_client().models.generate_content_stream(
            model=settings.chat_model, contents=_to_gemini(messages), config=_config(system)
        )
        for chunk in response:
            if chunk.text:  # thinking-only and empty chunks carry no text
                yield chunk.text
    except errors.APIError as exc:
        raise LLMError(f"Chat request failed: {exc}") from exc


def generate(system: str, messages: list[Message]) -> str:
    """The whole reply at once. Used by evals and anywhere streaming isn't needed."""
    return "".join(stream(system, messages))
