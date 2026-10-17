from datetime import UTC, datetime

import pytest

from app import chat
from app.models import Message, SearchResults, Site

SITE = Site(id=1, url="https://shop.test", public_key="k", created_at=datetime.now(UTC))


@pytest.fixture(autouse=True)
def no_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat, "search", lambda conn, site_id, q, page_url: SearchResults())


def test_prepare_keeps_only_recent_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat.settings, "chat_history_turns", 2)
    history = [Message(role="user", content=f"turn {i}") for i in range(5)]

    _, messages, _ = chat.prepare(None, SITE, "new question", history)

    assert [m.content for m in messages[:-1]] == ["turn 3", "turn 4"]
    assert messages[-1].role == "user"
    assert "<shopper_message>\nnew question\n</shopper_message>" in messages[-1].content


def test_answer_joins_streamed_pieces(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_stream(system: str, messages: list[Message]):
        seen["system"] = system
        yield from ["We don't ", "carry that."]

    monkeypatch.setattr(chat.llm, "stream", fake_stream)
    text, results = chat.answer(None, SITE, "running shoes?")

    assert text == "We don't carry that."
    assert results == SearchResults()
    assert "https://shop.test" in seen["system"]
