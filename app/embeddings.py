"""Text embeddings. The only module that knows which embedding provider we use.

Callers get plain lists of floats. To switch providers, rewrite this file and
re-index (vectors from different models can't be compared).
"""

import logging

from google.genai import errors, types

from app.config import settings
from app.gemini import get_client

log = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


# gemini-embedding-2 has no task_type option; it takes the task as a text prefix instead.
# Documents and queries use different prefixes so a short question can match a long passage.
def _document_input(title: str, text: str) -> str:
    return f"title: {title or 'none'} | text: {text}"


def _query_input(query: str) -> str:
    return f"task: search result | query: {query}"


def _embed_batch(inputs: list[str]) -> list[list[float]]:
    """One API call. Kept separate so tests can replace it without a network."""
    try:
        result = get_client().models.embed_content(
            model=settings.embedding_model,
            contents=inputs,
            config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dimensions),
        )
    except errors.APIError as exc:
        raise EmbeddingError(f"Embedding request failed: {exc}") from exc
    vectors = [e.values for e in result.embeddings or []]
    if len(vectors) != len(inputs) or any(v is None for v in vectors):
        raise EmbeddingError(f"Expected {len(inputs)} embeddings, got {len(vectors)}")
    return vectors


def _embed(inputs: list[str]) -> list[list[float]]:
    size = settings.embedding_batch_size
    vectors: list[list[float]] = []
    for start in range(0, len(inputs), size):
        vectors.extend(_embed_batch(inputs[start : start + size]))
        log.debug("Embedded %d/%d", len(vectors), len(inputs))
    return vectors


def embed_documents(docs: list[tuple[str, str]]) -> list[list[float]]:
    """Embed (title, text) pairs for storage, in the same order."""
    return _embed([_document_input(title, text) for title, text in docs])


def embed_query(query: str) -> list[float]:
    """Embed a shopper's question for searching stored documents."""
    return _embed([_query_input(query)])[0]
