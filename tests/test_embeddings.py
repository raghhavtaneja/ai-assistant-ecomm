import pytest

from app import embeddings, gemini
from app.config import settings


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace the API call; record each batch and return one tiny vector per input."""
    batches: list[list[str]] = []

    def fake_batch(inputs: list[str]) -> list[list[float]]:
        batches.append(inputs)
        return [[float(len(text))] for text in inputs]

    monkeypatch.setattr(embeddings, "_embed_batch", fake_batch)
    return batches


def test_documents_and_queries_use_different_prefixes(fake_api: list[list[str]]) -> None:
    embeddings.embed_documents([("Serum", "Reduces blemishes."), ("", "Refund policy")])
    embeddings.embed_query("anything for acne?")

    assert fake_api == [
        ["title: Serum | text: Reduces blemishes.", "title: none | text: Refund policy"],
        ["task: search result | query: anything for acne?"],
    ]


def test_batches_split_and_keep_order(
    fake_api: list[list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "embedding_batch_size", 2)
    docs = [("", "a" * n) for n in range(1, 6)]

    vectors = embeddings.embed_documents(docs)

    assert [len(b) for b in fake_api] == [2, 2, 1]
    # Vector i comes from input i: each fake vector encodes its input's length.
    assert vectors == [[float(len(f"title: none | text: {'a' * n}"))] for n in range(1, 6)]


def test_missing_api_key_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "")
    gemini.get_client.cache_clear()  # the client is cached per process
    with pytest.raises(gemini.MissingApiKeyError, match="GEMINI_API_KEY is not set"):
        embeddings.embed_query("hello")
