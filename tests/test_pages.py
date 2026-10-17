import httpx

from app.ingest.pages import fetch_policy_chunks, is_policy_page, sitemap_locs

BASE = "https://shop.test"

SITEMAP_INDEX = f"""<sitemapindex>
  <sitemap><loc>{BASE}/sitemap_products_1.xml?from=1&amp;to=2</loc></sitemap>
  <sitemap><loc>{BASE}/sitemap_pages_1.xml</loc></sitemap>
</sitemapindex>"""

PAGES_SITEMAP = f"""<urlset>
  <url><loc>{BASE}/pages/faqs</loc></url>
  <url><loc>{BASE}/pages/flat-200-off</loc></url>
  <url><loc>{BASE}/pages/return-policy-copy</loc></url>
  <url><loc>{BASE}/pages/order-delivery</loc></url>
  <url><loc>https://evil.test/pages/faq</loc></url>
</urlset>"""

# Page bodies must be at least MIN_PAGE_CHARS long, like real policy pages.
REFUND_TEXT = (
    "Refund policy\nDamaged, expired, or wrong items can be returned within 7 days of delivery. "
    "Email us with photos."
)
FAQ_TEXT = (
    "FAQs\nDo you ship abroad? Yes, we ship to the US, UK, UAE, Malaysia, and Indonesia "
    "from our nearest warehouse."
)
REFUND_HTML = f"<header>Menu</header><main>{REFUND_TEXT.replace(chr(10), '<br>')}</main>"
PAGES = {
    "/policies/refund-policy": REFUND_HTML,
    "/pages/return-policy-copy": REFUND_HTML,  # same policy at a second URL
    "/pages/faqs": f"<main>{FAQ_TEXT.replace(chr(10), '<br>')}</main>",
    "/pages/flat-200-off": "<main><h1>Flat 200 off</h1></main>",
    "/pages/order-delivery": "<main><p>Loading form…</p></main>",  # rendered by JavaScript
}


def _fake_store(robots: str = "User-agent: *\nAllow: /") -> tuple[httpx.Client, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        path = request.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if path == "/sitemap.xml":
            return httpx.Response(200, text=SITEMAP_INDEX)
        if path == "/sitemap_pages_1.xml":
            return httpx.Response(200, text=PAGES_SITEMAP)
        if path in PAGES:
            return httpx.Response(200, text=PAGES[path])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def test_sitemap_locs_unescapes_entities() -> None:
    assert sitemap_locs(SITEMAP_INDEX)[0] == f"{BASE}/sitemap_products_1.xml?from=1&to=2"


def test_is_policy_page_uses_allowlist() -> None:
    assert is_policy_page(f"{BASE}/pages/faqs")
    assert is_policy_page(f"{BASE}/policies/shipping-policy")
    assert not is_policy_page(f"{BASE}/pages/flat-200-off")
    assert not is_policy_page(f"{BASE}/pages/our-values")
    assert not is_policy_page(f"{BASE}/pages/privacy-policy")


def test_fetch_policy_chunks_end_to_end() -> None:
    client, requested = _fake_store()
    chunks = fetch_policy_chunks(client, BASE, delay=0)

    # The duplicate refund page and the near-empty "Loading form…" page are both dropped.
    assert [(c.source, c.text) for c in chunks] == [
        (f"{BASE}/policies/refund-policy", REFUND_TEXT),
        (f"{BASE}/pages/faqs", FAQ_TEXT),
    ]
    # Promo pages and other domains are never even requested.
    assert not any("flat-200-off" in url or "evil.test" in url for url in requested)


def test_robots_disallowed_pages_are_skipped() -> None:
    client, requested = _fake_store(robots="User-agent: *\nDisallow: /pages/")
    chunks = fetch_policy_chunks(client, BASE, delay=0)

    assert [c.source for c in chunks] == [f"{BASE}/policies/refund-policy"]
    assert not any("/pages/" in url for url in requested)
