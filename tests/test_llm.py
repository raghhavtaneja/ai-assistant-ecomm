from types import SimpleNamespace

import pytest
from google.genai import errors

from app import llm
from app.models import Message


def _fake_client(chunks: list[str | None] | Exception) -> SimpleNamespace:
    class FakeModels:
        def generate_content_stream(self, model: str, contents: list, config: object):
            if isinstance(chunks, Exception):
                raise chunks
            return (SimpleNamespace(text=t) for t in chunks)

    return SimpleNamespace(models=FakeModels())


def test_roles_map_to_gemini_names() -> None:
    contents = llm._to_gemini(
        [Message(role="user", content="hi"), Message(role="assistant", content="hello")]
    )
    assert [(c.role, c.parts[0].text) for c in contents] == [("user", "hi"), ("model", "hello")]


def test_stream_skips_empty_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "get_client", lambda: _fake_client(["Hel", None, "", "lo"]))
    assert list(llm.stream("sys", [Message(role="user", content="q")])) == ["Hel", "lo"]


def test_api_errors_become_llm_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    failure = errors.APIError(503, {"error": {"message": "overloaded"}})
    monkeypatch.setattr(llm, "get_client", lambda: _fake_client(failure))
    with pytest.raises(llm.LLMError, match="Chat request failed"):
        llm.generate("sys", [Message(role="user", content="q")])
