"""Fetch a store's policy and FAQ pages and turn them into chunks."""

import hashlib
import html
import logging
import re
import time
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.ingest.chunking import chunk_text
from app.ingest.http import is_allowed, load_robots
from app.ingest.text import html_to_text
from app.models import Chunk

log = logging.getLogger(__name__)

# Shopify's built-in policy pages. Not every store has all of them; 404s are skipped.
SHOPIFY_POLICY_PATHS = [
    "/policies/refund-policy",
    "/policies/shipping-policy",
    "/policies/terms-of-service",
    "/policies/contact-information",
]

# A sitemap page is kept only if its URL path contains one of these words. An allowlist,
# not a blocklist: promo pages ("flat-200-off") are often expired, and quoting a dead
# discount to a shopper is exactly the kind of answer we must never give.
# Privacy policies are left out on purpose: shoppers rarely ask about them, and their long
# legal text mentions orders and shipping, so it would crowd out the real policies.
POLICY_KEYWORDS = (
    "faq", "refund", "return", "exchange", "cancel", "shipping", "delivery",
    "payment", "warranty", "terms", "contact", "get-in-touch", "grievance",
)  # fmt: skip
MAX_TITLE_CHARS = 100
# Pages built by JavaScript arrive as just "Loading..." or bare form labels. Text that
# short carries no answer, yet scores as vaguely similar to everything during retrieval.
MIN_PAGE_CHARS = 100


def sitemap_locs(xml: str) -> list[str]:
    """All <loc> URLs in a sitemap or sitemap index.

    A regex rather than an XML parser: we only need one tag, and it avoids feeding
    untrusted XML (with its entity-expansion tricks) into a real parser.
    """
    return [html.unescape(loc.strip()) for loc in re.findall(r"<loc>(.*?)</loc>", xml, re.S)]


def is_policy_page(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(keyword in path for keyword in POLICY_KEYWORDS)


def _same_site(url: str, base_url: str) -> bool:
    # A sitemap is untrusted input; never let it send the crawler to another domain.
    return urlparse(url).netloc == urlparse(base_url).netloc


def find_policy_urls(client: httpx.Client, base_url: str) -> list[str]:
    """Policy/FAQ URLs from Shopify's fixed paths plus the store's pages sitemap."""
    urls = [base_url + path for path in SHOPIFY_POLICY_PATHS]
    try:
        index = client.get(f"{base_url}/sitemap.xml")
        index.raise_for_status()
        # Shopify splits its sitemap by type; only the "pages" ones hold policy/FAQ pages.
        for sitemap_url in sitemap_locs(index.text):
            if "sitemap_pages" in sitemap_url and _same_site(sitemap_url, base_url):
                response = client.get(sitemap_url)
                response.raise_for_status()
                urls.extend(sitemap_locs(response.text))
    except httpx.HTTPError as exc:
        log.warning("Could not read sitemap for %s, using policy paths only: %s", base_url, exc)

    wanted = [u for u in urls if _same_site(u, base_url) and is_policy_page(u)]
    return list(dict.fromkeys(wanted))  # dedupe, keep order


def fetch_page_text(client: httpx.Client, url: str) -> str | None:
    """Main text of one page, or None if it can't be fetched."""
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return None
    if response.status_code != 200:
        log.info("Skipping %s (HTTP %d)", url, response.status_code)
        return None
    return html_to_text(response.text)


def fetch_policy_chunks(
    client: httpx.Client, base_url: str, delay: float | None = None
) -> list[Chunk]:
    """Fetch every policy/FAQ page (politely, capped) and chunk its text."""
    delay = settings.crawl_delay_seconds if delay is None else delay
    base_url = base_url.rstrip("/")
    robots = load_robots(client, base_url)
    urls = [u for u in find_policy_urls(client, base_url) if is_allowed(robots, u)]

    chunks: list[Chunk] = []
    seen_hashes: set[str] = set()
    for url in urls[: settings.crawl_max_pages]:
        text = fetch_page_text(client, url)
        time.sleep(delay)
        if not text or len(text) < MIN_PAGE_CHARS:
            log.info("Skipping %s (no usable text, likely rendered by JavaScript)", url)
            continue
        # Stores often publish the same policy at two URLs; index it once.
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        # The first line is the page heading; capped so it can't eat the chunk budget.
        title = text.splitlines()[0][:MAX_TITLE_CHARS]
        chunks.extend(
            Chunk(source=url, text=passage)
            for passage in chunk_text(text, title, settings.chunk_max_chars)
        )
    log.info("Built %d chunks from %d policy/FAQ pages on %s", len(chunks), len(urls), base_url)
    return chunks
