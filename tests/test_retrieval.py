import math
from pathlib import Path

import pytest

from app import db, retrieval
from app.models import Chunk, Product

# 2-D vectors keep the geometry easy to reason about: angle = relevance.
QUERY = [1.0, 0.0]


def _vec(degrees: float) -> list[float]:
    """A unit vector at this angle from QUERY; cosine = cos(angle)."""
    rad = math.radians(degrees)
    return [math.cos(rad), math.sin(rad)]


def _product(handle: str, degrees: float) -> Product:
    return Product(
        url=f"https://shop.test/products/{handle}", title=handle, embedding=_vec(degrees)
    )


def test_cosine_basics() -> None:
    assert retrieval.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert retrieval.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert retrieval.cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)
    # Length doesn't matter, only direction.
    assert retrieval.cosine([1, 1], [5, 5]) == pytest.approx(1.0)
    assert retrieval.cosine([0, 0], [1, 0]) == 0.0


def test_rank_orders_by_similarity_and_applies_k() -> None:
    items = [_product("far", 60), _product("close", 10), _product("mid", 30)]
    assert [p.title for p in retrieval.rank(QUERY, items, k=2, min_score=0)] == ["close", "mid"]


def test_rank_drops_items_below_min_score() -> None:
    items = [_product("close", 10), _product("far", 80)]  # cos(80°) ≈ 0.17
    assert [p.title for p in retrieval.rank(QUERY, items, k=5, min_score=0.5)] == ["close"]


def test_rank_skips_items_without_embeddings() -> None:
    items = [Product(url="u", title="unembedded"), _product("close", 10)]
    assert [p.title for p in retrieval.rank(QUERY, items, k=5, min_score=0)] == ["close"]


@pytest.mark.parametrize(
    "page_url",
    [
        "https://shop.test/products/serum",
        "https://shop.test/products/serum/",
        "https://shop.test/products/serum?variant=123",
        "https://shop.test/collections/face/products/serum",
    ],
)
def test_find_current_product_handles_url_variants(page_url: str) -> None:
    products = [_product("cleanser", 0), _product("serum", 0)]
    assert retrieval.find_current_product(products, page_url).title == "serum"


@pytest.mark.parametrize(
    "page_url", [None, "https://shop.test/", "https://shop.test/products/unknown"]
)
def test_find_current_product_none_when_not_on_a_known_product(page_url: str | None) -> None:
    assert retrieval.find_current_product([_product("serum", 0)], page_url) is None


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    """A tiny indexed store; the query embedding is faked so no API is called."""
    monkeypatch.setattr(retrieval, "embed_query", lambda query: QUERY)
    monkeypatch.setattr(retrieval.settings, "top_products", 2)
    monkeypatch.setattr(retrieval.settings, "min_score", 0.5)
    conn = db.connect(tmp_path / "test.db")
    site = db.get_or_create_site(conn, "https://shop.test")
    db.replace_products(
        conn,
        site.id,
        [_product("best", 5), _product("second", 20), _product("third", 40), _product("off", 85)],
    )
    db.replace_chunks(
        conn,
        site.id,
        [
            Chunk(source="refund", text="Refund policy", embedding=_vec(10)),
            Chunk(source="terms", text="Terms", embedding=_vec(80)),
        ],
    )
    return conn, site.id


def test_search_returns_top_products_and_chunks(store: tuple) -> None:
    conn, site_id = store
    results = retrieval.search(conn, site_id, "question")

    assert [p.title for p in results.products] == ["best", "second"]
    assert [c.source for c in results.chunks] == ["refund"]  # "terms" is below min_score
    assert results.current_product is None


def test_search_puts_current_product_first_even_if_unrelated(store: tuple) -> None:
    conn, site_id = store
    results = retrieval.search(conn, site_id, "is this good?", "https://shop.test/products/off")

    assert results.current_product.title == "off"
    assert [p.title for p in results.products] == ["off", "best"]  # still capped at top_products


def test_search_does_not_duplicate_current_product(store: tuple) -> None:
    conn, site_id = store
    results = retrieval.search(conn, site_id, "q", "https://shop.test/products/second")
    assert [p.title for p in results.products] == ["second", "best"]
