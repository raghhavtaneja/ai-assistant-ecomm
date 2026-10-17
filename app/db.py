"""SQLite storage. The only module that touches sqlite3.

Functions take and return the models in app/models.py, so callers never see
rows or SQL. To move to Postgres later, rewrite this file only.
"""

import json
import secrets
import sqlite3
from array import array
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.models import Chunk, Product, Site

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL UNIQUE,
    persona_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    last_crawled_at TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price REAL,
    currency TEXT,
    image_url TEXT,
    available INTEGER NOT NULL DEFAULT 0,
    variants_json TEXT NOT NULL DEFAULT '[]',
    embedding BLOB
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_products_site ON products(site_id);
CREATE INDEX IF NOT EXISTS idx_chunks_site ON chunks(site_id);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the database, creating the file and schema if needed."""
    path = path or settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # SQLite ignores foreign keys (and so ON DELETE CASCADE) unless asked, per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


# Embeddings are stored as packed float32 bytes: 4x smaller than JSON and fast to load.
def _pack(vector: list[float] | None) -> bytes | None:
    return array("f", vector).tobytes() if vector is not None else None


def _unpack(blob: bytes | None) -> list[float] | None:
    return array("f", blob).tolist() if blob is not None else None


def _row_to_site(row: sqlite3.Row) -> Site:
    return Site(
        id=row["id"],
        url=row["url"],
        public_key=row["public_key"],
        persona=json.loads(row["persona_json"]),
        created_at=row["created_at"],
        last_crawled_at=row["last_crawled_at"],
    )


def get_or_create_site(conn: sqlite3.Connection, url: str) -> Site:
    url = url.rstrip("/")
    row = conn.execute("SELECT * FROM sites WHERE url = ?", (url,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO sites (url, public_key, created_at) VALUES (?, ?, ?)",
            (url, secrets.token_urlsafe(16), _now()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sites WHERE url = ?", (url,)).fetchone()
    return _row_to_site(row)


def mark_crawled(conn: sqlite3.Connection, site_id: int) -> None:
    conn.execute("UPDATE sites SET last_crawled_at = ? WHERE id = ?", (_now(), site_id))
    conn.commit()


def replace_products(conn: sqlite3.Connection, site_id: int, products: list[Product]) -> None:
    """Swap a site's whole catalog in one transaction.

    A re-crawl is the source of truth, so deleting and re-inserting is simpler
    than diffing, and drops products the store has removed.
    """
    with conn:  # commits on success, rolls back on error
        conn.execute("DELETE FROM products WHERE site_id = ?", (site_id,))
        conn.executemany(
            """INSERT INTO products (site_id, url, title, description, price, currency,
                   image_url, available, variants_json, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    site_id,
                    p.url,
                    p.title,
                    p.description,
                    p.price,
                    p.currency,
                    p.image_url,
                    int(p.available),
                    json.dumps(p.variants),
                    _pack(p.embedding),
                )  # fmt: skip
                for p in products
            ],
        )


def list_products(conn: sqlite3.Connection, site_id: int) -> list[Product]:
    rows = conn.execute("SELECT * FROM products WHERE site_id = ? ORDER BY id", (site_id,))
    return [
        Product(
            id=r["id"],
            url=r["url"],
            title=r["title"],
            description=r["description"],
            price=r["price"],
            currency=r["currency"],
            image_url=r["image_url"],
            available=bool(r["available"]),
            variants=json.loads(r["variants_json"]),
            embedding=_unpack(r["embedding"]),
        )
        for r in rows
    ]


def replace_chunks(conn: sqlite3.Connection, site_id: int, chunks: list[Chunk]) -> None:
    """Same replace-all approach as replace_products."""
    with conn:
        conn.execute("DELETE FROM chunks WHERE site_id = ?", (site_id,))
        conn.executemany(
            "INSERT INTO chunks (site_id, source, text, embedding) VALUES (?, ?, ?, ?)",
            [(site_id, c.source, c.text, _pack(c.embedding)) for c in chunks],
        )


def list_chunks(conn: sqlite3.Connection, site_id: int) -> list[Chunk]:
    rows = conn.execute("SELECT * FROM chunks WHERE site_id = ? ORDER BY id", (site_id,))
    return [
        Chunk(id=r["id"], source=r["source"], text=r["text"], embedding=_unpack(r["embedding"]))
        for r in rows
    ]
