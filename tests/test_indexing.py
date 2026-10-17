from pathlib import Path

import pytest

from app import db, indexing
from app.models import Chunk, Product

SERUM = Product(
    url="https://shop.test/products/serum",
    title="Niacinamide Serum",
    description="Reduces blemishes.",
    price=599.0,
    variants=[{"title": "30ml"}, {"title": "50ml"}],
)
REFUND = Chunk(source="https://shop.test/policies/refund-policy", text="Refund policy\n7 days.")


def test_product_text_includes_sizes_but_not_price() -> None:
    text = indexing.product_text(SERUM)
    assert text == "Niacinamide Serum\nReduces blemishes.\nSizes: 30ml, 50ml"
    assert "599" not in text


def test_product_text_skips_shopify_default_variant() -> None:
    single = SERUM.model_copy(update={"variants": [{"title": "Default Title"}]})
    assert "Sizes" not in indexing.product_text(single)


def test_index_site_stores_embedded_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(indexing, "fetch_products", lambda client, url: [SERUM])
    monkeypatch.setattr(indexing, "fetch_policy_chunks", lambda client, url: [REFUND])
    monkeypatch.setattr(indexing, "embed_documents", lambda docs: [[0.5, 0.25] for _ in docs])
    conn = db.connect(tmp_path / "test.db")

    assert indexing.index_site(conn, "https://shop.test") == (1, 1)

    site = db.get_or_create_site(conn, "https://shop.test")
    assert site.last_crawled_at is not None
    assert db.list_products(conn, site.id)[0].embedding == [0.5, 0.25]
    assert db.list_chunks(conn, site.id)[0].embedding == [0.5, 0.25]


def test_failed_embedding_keeps_old_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "test.db")
    site = db.get_or_create_site(conn, "https://shop.test")
    db.replace_products(conn, site.id, [SERUM])

    def failing_embed(docs: list[tuple[str, str]]) -> list[list[float]]:
        raise RuntimeError("API down")

    monkeypatch.setattr(indexing, "fetch_products", lambda client, url: [])
    monkeypatch.setattr(indexing, "fetch_policy_chunks", lambda client, url: [])
    monkeypatch.setattr(indexing, "embed_documents", failing_embed)

    with pytest.raises(RuntimeError, match="API down"):
        indexing.index_site(conn, "https://shop.test")
    assert [p.title for p in db.list_products(conn, site.id)] == ["Niacinamide Serum"]
