import json
from pathlib import Path

import httpx
import pytest

from app.ingest.shopify import (
    NotShopifyError,
    fetch_products,
    is_free_gift,
    is_hidden,
    parse_product,
)

BASE = "https://shop.test"
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "shopify_products.json").read_text())
RAW = {p["handle"]: p for p in FIXTURE["products"]}


def _fake_store(robots: str = "User-agent: *\nAllow: /", meta_status: int = 200) -> httpx.Client:
    """A client whose requests are answered in-process, so tests never hit the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        path, page = request.url.path, request.url.params.get("page")
        if path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if path == "/meta.json":
            return httpx.Response(meta_status, json={"currency": "INR"})
        if path == "/products.json":
            return httpx.Response(200, json=FIXTURE if page == "1" else {"products": []})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_product_uses_cheapest_in_stock_variant() -> None:
    product = parse_product(RAW["hydrating-face-moisturizer"], BASE, "INR")

    assert product.url == f"{BASE}/products/hydrating-face-moisturizer"
    # 30g is cheaper but sold out, so the headline price is the 50g one.
    assert product.price == 359.0
    assert product.available is True
    assert product.currency == "INR"
    assert product.image_url == "https://cdn.shop.test/moisturizer.png"
    assert [v["title"] for v in product.variants] == ["30g", "50g"]


def test_parse_product_strips_html_from_description() -> None:
    product = parse_product(RAW["hydrating-face-moisturizer"], BASE, "INR")
    assert product.description == (
        "A lightweight moisturizer with ceramides.\nFragrance free\nFor dry skin"
    )


def test_parse_product_sold_out_keeps_price_and_has_no_image() -> None:
    product = parse_product(RAW["niacinamide-serum"], BASE, "INR")

    assert product.available is False
    assert product.price == 599.0
    assert product.image_url is None


def test_hidden_tag_detection_is_case_insensitive() -> None:
    assert is_hidden(RAW["kit-as-a-gift"])
    assert is_hidden({"tags": ["Hidden"]})
    assert not is_hidden(RAW["niacinamide-serum"])


def test_free_gift_detection() -> None:
    assert is_free_gift(RAW["free-cleanser-mini"])
    # One paid variant is enough to make it a real product.
    assert not is_free_gift({"variants": [{"price": "0.00"}, {"price": "199.00"}]})
    assert not is_free_gift({"variants": []})


def test_fetch_products_skips_hidden_and_free_gifts() -> None:
    products = fetch_products(_fake_store(), BASE + "/", delay=0)
    assert [p.title for p in products] == ["Hydrating Face Moisturizer", "Niacinamide 10% Serum"]


def test_fetch_products_respects_robots_txt() -> None:
    blocked = _fake_store(robots="User-agent: *\nDisallow: /products.json")
    assert fetch_products(blocked, BASE, delay=0) == []


def test_non_shopify_site_raises_clear_error() -> None:
    with pytest.raises(NotShopifyError, match="does not look like a Shopify store"):
        fetch_products(_fake_store(meta_status=404), BASE, delay=0)
