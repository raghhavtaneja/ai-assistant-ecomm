from pathlib import Path

import pytest

from app import cli, db
from app.ingest.shopify import NotShopifyError
from app.models import Message, Product, SearchResults

URL = "https://shop.test"


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "test.db"
    monkeypatch.setattr(cli.settings, "database_path", path)
    return path


def _index(path: Path) -> None:
    conn = db.connect(path)
    site = db.get_or_create_site(conn, URL)
    db.mark_crawled(conn, site.id)


def _fake_stream(reply: list[str], seen: dict | None = None):
    def fake(conn, site, question, history, page_url):
        if seen is not None:
            seen.update(question=question, history=list(history), page_url=page_url)
        results = SearchResults(products=[Product(url=f"{URL}/products/serum", title="Serum")])
        return iter(reply), results

    return fake


def test_ingest_reports_counts(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(cli, "index_site", lambda conn, url: (73, 44))
    assert cli.main(["ingest", URL]) == 0
    assert "73 products and 44 policy/FAQ passages" in capsys.readouterr().out


def test_ingest_non_shopify_fails_cleanly(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    def fail(conn, url):
        raise NotShopifyError("not a Shopify store")

    monkeypatch.setattr(cli, "index_site", fail)
    assert cli.main(["ingest", URL]) == 1
    assert "not a Shopify store" in caplog.text


def test_ask_requires_ingest_first(caplog) -> None:
    assert cli.main(["ask", URL, "hi"]) == 1
    assert "isn't indexed yet" in caplog.text


def test_ask_once_streams_answer_and_sources(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _index(temp_db)
    seen: dict = {}
    monkeypatch.setattr(cli, "stream_answer", _fake_stream(["Try the ", "Serum."], seen))

    page = f"{URL}/products/serum"
    assert cli.main(["ask", URL, "oily skin?", "--page", page, "--sources"]) == 0

    out = capsys.readouterr().out
    assert "Try the Serum." in out
    assert "product: Serum" in out
    assert seen["page_url"] == page


def test_chat_keeps_history_between_turns(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    _index(temp_db)
    seen: dict = {}
    monkeypatch.setattr(cli, "stream_answer", _fake_stream(["Sure."], seen))
    inputs = iter(["first question", "follow up", ""])  # empty line quits
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    assert cli.main(["ask", URL]) == 0
    assert seen["question"] == "follow up"
    assert seen["history"] == [
        Message(role="user", content="first question"),
        Message(role="assistant", content="Sure."),
    ]
