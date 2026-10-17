"""Build a site's searchable index: fetch, embed, store."""

import logging
import sqlite3

from app import db
from app.embeddings import embed_documents
from app.ingest.http import make_client
from app.ingest.pages import fetch_policy_chunks
from app.ingest.shopify import fetch_products
from app.models import Chunk, Product

log = logging.getLogger(__name__)


def product_text(product: Product) -> str:
    """What we embed for a product.

    Price and stock are left out on purpose: they change often, and they're always
    read from the database at answer time, never from the vector.
    """
    sizes = ", ".join(v["title"] for v in product.variants if v["title"] != "Default Title")
    parts = [product.title, product.description, f"Sizes: {sizes}" if sizes else ""]
    return "\n".join(p for p in parts if p)


def embed_products(products: list[Product]) -> list[Product]:
    vectors = embed_documents([(p.title, product_text(p)) for p in products])
    return [p.model_copy(update={"embedding": v}) for p, v in zip(products, vectors, strict=True)]


def embed_chunks(chunks: list[Chunk]) -> list[Chunk]:
    # The chunk text already starts with its page title, so no separate title is passed.
    vectors = embed_documents([("", c.text) for c in chunks])
    return [c.model_copy(update={"embedding": v}) for c, v in zip(chunks, vectors, strict=True)]


def index_site(conn: sqlite3.Connection, url: str) -> tuple[int, int]:
    """Fetch and embed everything, then store it. Returns (products, chunks) counts.

    All embedding happens before any write, so a failed run leaves the old index intact.
    """
    site = db.get_or_create_site(conn, url)
    with make_client() as client:
        products = fetch_products(client, site.url)
        chunks = fetch_policy_chunks(client, site.url)

    products = embed_products(products)
    chunks = embed_chunks(chunks)

    db.replace_products(conn, site.id, products)
    db.replace_chunks(conn, site.id, chunks)
    db.mark_crawled(conn, site.id)
    log.info("Indexed %s: %d products, %d chunks", site.url, len(products), len(chunks))
    return len(products), len(chunks)
