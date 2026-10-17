"""Fetch a Shopify store's catalog from its public JSON endpoints.

Shopify exposes /products.json on every store. It is far more reliable than
scraping product HTML, and it includes variants, prices, and stock.
"""

import logging
import time

import httpx

from app.config import settings
from app.ingest.http import is_allowed, load_robots
from app.ingest.text import html_to_text
from app.models import Product

log = logging.getLogger(__name__)

PAGE_SIZE = 250  # Shopify's maximum for /products.json
# Merchants use these tags for internal items (gift kits, bundle builders) that shoppers can't buy.
HIDDEN_TAGS = {"hidden", "__hidden"}


class NotShopifyError(Exception):
    pass


def fetch_currency(client: httpx.Client, base_url: str) -> str:
    """Read the store currency from /meta.json, which also confirms the site is Shopify."""
    try:
        response = client.get(f"{base_url}/meta.json")
        response.raise_for_status()
        return response.json()["currency"]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise NotShopifyError(f"{base_url} does not look like a Shopify store: {exc}") from exc


def fetch_raw_products(
    client: httpx.Client, base_url: str, delay: float | None = None
) -> list[dict]:
    """Page through /products.json until an empty page or the page cap."""
    delay = settings.crawl_delay_seconds if delay is None else delay
    robots = load_robots(client, base_url)
    raw: list[dict] = []
    for page in range(1, settings.crawl_max_pages + 1):
        url = f"{base_url}/products.json?limit={PAGE_SIZE}&page={page}"
        if not is_allowed(robots, url):
            log.warning("robots.txt disallows %s, stopping", url)
            break
        response = client.get(url)
        response.raise_for_status()
        batch = response.json().get("products", [])
        if not batch:
            break
        raw.extend(batch)
        time.sleep(delay)
    return raw


def is_hidden(raw: dict) -> bool:
    return any(tag.lower() in HIDDEN_TAGS for tag in raw.get("tags", []))


def is_free_gift(raw: dict) -> bool:
    """All variants at 0 means a gift-with-purchase, which can't be bought on its own."""
    variants = raw.get("variants", [])
    return bool(variants) and all(float(v["price"]) == 0 for v in variants)


def is_sellable(raw: dict) -> bool:
    return not is_hidden(raw) and not is_free_gift(raw)


def parse_product(raw: dict, base_url: str, currency: str) -> Product:
    """Map one Shopify product dict to our Product model."""
    variants = [
        {
            "title": v["title"],
            "price": v["price"],
            "compare_at_price": v.get("compare_at_price"),
            "available": bool(v.get("available")),
        }
        for v in raw.get("variants", [])
    ]
    # Prefer the cheapest *buyable* variant: "from ₹269" shouldn't point at an out-of-stock size.
    in_stock = [v for v in variants if v["available"]]
    prices = [float(v["price"]) for v in (in_stock or variants)]
    images = raw.get("images") or []
    return Product(
        url=f"{base_url}/products/{raw['handle']}",
        title=raw["title"],
        description=html_to_text(raw.get("body_html") or ""),
        price=min(prices) if prices else None,
        currency=currency,
        image_url=images[0]["src"] if images else None,
        available=bool(in_stock),
        variants=variants,
    )


def fetch_products(
    client: httpx.Client, base_url: str, delay: float | None = None
) -> list[Product]:
    """The whole visible catalog of a Shopify store."""
    base_url = base_url.rstrip("/")
    currency = fetch_currency(client, base_url)
    raw = fetch_raw_products(client, base_url, delay)
    products = [parse_product(r, base_url, currency) for r in raw if is_sellable(r)]
    log.info(
        "Fetched %d products (%d hidden or free gifts skipped) from %s",
        len(products),
        len(raw) - len(products),
        base_url,
    )
    return products
