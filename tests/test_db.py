import sqlite3
from pathlib import Path

import pytest

from app import db
from app.models import Chunk, Product


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.connect(tmp_path / "test.db")


def _product(title: str, **overrides: object) -> Product:
    fields = {"url": f"https://shop.test/products/{title}", "title": title, "price": 599.0}
    return Product(**(fields | overrides))


def test_get_or_create_site_is_idempotent(conn: sqlite3.Connection) -> None:
    first = db.get_or_create_site(conn, "https://shop.test/")
    second = db.get_or_create_site(conn, "https://shop.test")

    # Trailing slash shouldn't create a duplicate site.
    assert first.id == second.id
    assert first.public_key == second.public_key
    assert first.last_crawled_at is None


def test_mark_crawled_sets_timestamp(conn: sqlite3.Connection) -> None:
    site = db.get_or_create_site(conn, "https://shop.test")
    db.mark_crawled(conn, site.id)
    assert db.get_or_create_site(conn, "https://shop.test").last_crawled_at is not None


def test_products_round_trip(conn: sqlite3.Connection) -> None:
    site = db.get_or_create_site(conn, "https://shop.test")
    original = _product(
        "serum",
        currency="INR",
        available=True,
        variants=[{"title": "30ml", "price": "599.00", "available": True}],
        embedding=[0.5, -0.25, 1.0],  # exactly representable in float32
    )
    db.replace_products(conn, site.id, [original])

    [loaded] = db.list_products(conn, site.id)
    assert loaded.model_dump(exclude={"id"}) == original.model_dump(exclude={"id"})


def test_replace_products_drops_old_catalog(conn: sqlite3.Connection) -> None:
    site = db.get_or_create_site(conn, "https://shop.test")
    db.replace_products(conn, site.id, [_product("old")])
    db.replace_products(conn, site.id, [_product("new-a"), _product("new-b")])

    assert [p.title for p in db.list_products(conn, site.id)] == ["new-a", "new-b"]


def test_products_are_scoped_per_site(conn: sqlite3.Connection) -> None:
    a = db.get_or_create_site(conn, "https://a.test")
    b = db.get_or_create_site(conn, "https://b.test")
    db.replace_products(conn, a.id, [_product("only-in-a")])

    assert db.list_products(conn, b.id) == []


def test_chunks_round_trip_without_embedding(conn: sqlite3.Connection) -> None:
    site = db.get_or_create_site(conn, "https://shop.test")
    chunk = Chunk(source="https://shop.test/policies/refund-policy", text="Returns within 7 days.")
    db.replace_chunks(conn, site.id, [chunk])

    [loaded] = db.list_chunks(conn, site.id)
    assert loaded.text == chunk.text
    assert loaded.embedding is None
