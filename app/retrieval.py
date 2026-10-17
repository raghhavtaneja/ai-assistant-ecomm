"""Find the products and policy passages most relevant to a shopper's question."""

import logging
import math
import sqlite3
from urllib.parse import urlparse

from app import db
from app.config import settings
from app.embeddings import embed_query
from app.models import Chunk, Product, SearchResults

log = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity, computed in plain Python.

    Fast enough for a few thousand items per store. If catalogs grow far beyond
    that, swap this for numpy or a vector index; nothing else needs to change.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norms if norms else 0.0


# Generic so one function ranks both products and chunks, and the return type matches the input.
def rank[Item: (Product, Chunk)](
    query: list[float], items: list[Item], k: int, min_score: float
) -> list[Item]:
    """The k most similar items scoring at least min_score, best first."""
    scored = [(cosine(query, item.embedding), item) for item in items if item.embedding]
    scored = [pair for pair in scored if pair[0] >= min_score]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    for score, item in scored[:k]:
        log.debug("%.3f %s", score, getattr(item, "title", None) or item.source)
    return [item for _, item in scored[:k]]


def _product_path(url: str) -> str:
    # Shopify serves one product at many URLs (/products/x, /collections/y/products/x,
    # with ?variant=...), so compare only the part from "/products/" on.
    path = urlparse(url).path.rstrip("/")
    return path[path.find("/products/") :] if "/products/" in path else path


def find_current_product(products: list[Product], page_url: str | None) -> Product | None:
    """The product whose page the shopper is on, if the URL is a product page."""
    if not page_url or "/products/" not in page_url:
        return None
    target = _product_path(page_url)
    return next((p for p in products if _product_path(p.url) == target), None)


def search(
    conn: sqlite3.Connection, site_id: int, query: str, page_url: str | None = None
) -> SearchResults:
    """Products and passages for a question, with the current page's product first.

    Products and passages are ranked separately: their scores sit in different
    ranges, so one combined list would let one kind crowd out the other.
    """
    # Loaded per query: simple and fine at this size. Cache per site if it ever gets slow.
    products = db.list_products(conn, site_id)
    chunks = db.list_chunks(conn, site_id)
    query_vector = embed_query(query)

    top_products = rank(query_vector, products, settings.top_products, settings.min_score)
    current = find_current_product(products, page_url)
    if current:
        # "Is this good for oily skin?" on a product page is about that product, even if the
        # question alone matches other products better.
        others = [p for p in top_products if p.url != current.url]
        top_products = [current, *others][: settings.top_products]

    return SearchResults(
        products=top_products,
        chunks=rank(query_vector, chunks, settings.top_chunks, settings.min_score),
        current_product=current,
    )
