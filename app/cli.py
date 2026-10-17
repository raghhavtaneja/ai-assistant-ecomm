"""Terminal interface for M1: index a store, then ask it questions.

uv run python -m app.cli ingest https://beminimalist.co
uv run python -m app.cli ask https://beminimalist.co "anything for oily skin?"
uv run python -m app.cli ask https://beminimalist.co            # interactive chat
"""

import argparse
import logging
import sqlite3
import sys

from app import db
from app.chat import stream_answer
from app.config import settings
from app.embeddings import EmbeddingError
from app.gemini import MissingApiKeyError
from app.indexing import index_site
from app.ingest.shopify import NotShopifyError
from app.llm import LLMError
from app.models import Message, SearchResults, Site

# Failures a user can act on get one clear line instead of a traceback.
EXPECTED_ERRORS = (MissingApiKeyError, NotShopifyError, EmbeddingError, LLMError)


class CliError(Exception):
    pass


def _write(text: str) -> None:
    # stdout is this tool's user interface, so it is written directly, not logged.
    sys.stdout.write(text)
    sys.stdout.flush()  # show streamed tokens as they arrive


def _sources(results: SearchResults) -> str:
    lines = [f"  product: {p.title}" for p in results.products]
    lines += [f"  page:    {c.source}" for c in results.chunks]
    return "\n[grounded on]\n" + ("\n".join(lines) or "  (nothing matched)") + "\n"


def run_ingest(conn: sqlite3.Connection, url: str) -> None:
    _write(f"Indexing {url} (the free Gemini tier may take a minute or two)...\n")
    products, chunks = index_site(conn, url)
    _write(f"Done: {products} products and {chunks} policy/FAQ passages indexed.\n")


def ask_once(
    conn: sqlite3.Connection,
    site: Site,
    question: str,
    history: list[Message],
    page_url: str | None,
    show_sources: bool,
) -> str:
    pieces, results = stream_answer(conn, site, question, history, page_url)
    reply = ""
    for piece in pieces:
        _write(piece)
        reply += piece
    _write("\n")
    if show_sources:
        _write(_sources(results))
    return reply


def run_chat(conn: sqlite3.Connection, site: Site, page_url: str | None, sources: bool) -> None:
    _write(f"Chatting with {site.url}. Empty line or Ctrl-D to quit.\n")
    history: list[Message] = []
    while True:
        try:
            question = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            break
        _write("assistant> ")
        reply = ask_once(conn, site, question, history, page_url, sources)
        # History keeps the plain question, not the store data sent with it.
        history += [
            Message(role="user", content=question),
            Message(role="assistant", content=reply),
        ]


def run_ask(conn: sqlite3.Connection, args: argparse.Namespace) -> None:
    site = db.find_site(conn, args.url)
    if site is None or site.last_crawled_at is None:
        raise CliError(f"{args.url} isn't indexed yet. Run: python -m app.cli ingest {args.url}")
    if args.question:
        ask_once(conn, site, args.question, [], args.page, args.sources)
    else:
        run_chat(conn, site, args.page, args.sources)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="AI sales assistant (M1 CLI)")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="crawl, embed, and store a Shopify store")
    ingest.add_argument("url", help="store home page, e.g. https://beminimalist.co")

    ask = commands.add_parser("ask", help="ask an indexed store a question")
    ask.add_argument("url", help="store URL used with ingest")
    ask.add_argument("question", nargs="?", help="omit for an interactive chat")
    ask.add_argument("--page", help="product page the shopper is viewing (page awareness)")
    ask.add_argument("--sources", action="store_true", help="show what the answer used")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    # Per-request info lines from these libraries drown out the conversation. Their warnings
    # (e.g. rate-limit retries) still show.
    for noisy in ("httpx", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    conn = db.connect()
    try:
        if args.command == "ingest":
            run_ingest(conn, args.url)
        else:
            run_ask(conn, args)
    except (CliError, *EXPECTED_ERRORS) as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
