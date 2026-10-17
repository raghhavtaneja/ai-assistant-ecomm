"""Answer a shopper's question: retrieve, build the prompt, call the model."""

import sqlite3
from collections.abc import Iterator

from app import llm
from app.config import settings
from app.models import Message, SearchResults, Site
from app.prompts import build_system_prompt, build_user_turn
from app.retrieval import search


def retrieval_query(question: str, history: list[Message]) -> str:
    """The text to search with: the new question plus the shopper's previous one.

    Follow-ups like "how much is the bigger size of that one?" name no product, so
    searching them alone finds nothing. The previous question supplies the topic
    without an extra model call to rewrite the query.
    """
    previous = next((m.content for m in reversed(history) if m.role == "user"), None)
    return f"{previous}\n{question}" if previous else question


def prepare(
    conn: sqlite3.Connection,
    site: Site,
    question: str,
    history: list[Message] | None = None,
    page_url: str | None = None,
) -> tuple[str, list[Message], SearchResults]:
    """Everything the model will see, without calling it. Evals use this to inspect inputs."""
    results = search(conn, site.id, retrieval_query(question, history or []), page_url)
    # Earlier turns are sent as plain text: their store data was for earlier questions,
    # and resending it would bloat every request. Fresh data comes with the new turn.
    recent = (history or [])[-settings.chat_history_turns :]
    messages = [*recent, Message(role="user", content=build_user_turn(question, results))]
    return build_system_prompt(site), messages, results


def stream_answer(
    conn: sqlite3.Connection,
    site: Site,
    question: str,
    history: list[Message] | None = None,
    page_url: str | None = None,
) -> tuple[Iterator[str], SearchResults]:
    """The reply as a stream of text pieces, plus the data it was grounded on.

    Results are returned too, so callers can show product cards and evals can
    check every price and link in the reply against them.
    """
    system, messages, results = prepare(conn, site, question, history, page_url)
    return llm.stream(system, messages), results


def answer(
    conn: sqlite3.Connection,
    site: Site,
    question: str,
    history: list[Message] | None = None,
    page_url: str | None = None,
) -> tuple[str, SearchResults]:
    pieces, results = stream_answer(conn, site, question, history, page_url)
    return "".join(pieces), results
