from app.ingest.text import decode_cfemail, html_to_text


def test_drops_scripts_and_styles() -> None:
    html = "<style>.a{color:red}</style><p>Visible</p><script>var x = 1;</script>"
    assert html_to_text(html) == "Visible"


def test_blocks_become_lines_and_whitespace_collapses() -> None:
    html = "<h2>Returns</h2><p>Within   7\n days.</p><div>Unopened items only.</div>"
    assert html_to_text(html) == "Returns\nWithin 7 days.\nUnopened items only."


def test_inline_tags_do_not_split_lines() -> None:
    assert html_to_text("<p>Price is <b>₹599</b> today</p>") == "Price is ₹599 today"


def test_decodes_entities() -> None:
    assert html_to_text("<p>Fish &amp; chips</p>") == "Fish & chips"


def test_empty_input() -> None:
    assert html_to_text("") == ""


def test_keeps_only_main_when_present() -> None:
    html = (
        "<header>Menu Shop Cart</header><main><h1>FAQs</h1><p>Answer</p></main><footer>©</footer>"
    )
    assert html_to_text(html) == "FAQs\nAnswer"


def test_custom_elements_starting_with_main_are_not_main() -> None:
    # Real Shopify themes use tags like <main-header>; they must not count as <main>.
    html = "<main-header>Menu</main-header><main><p>Body</p></main>"
    assert html_to_text(html) == "Body"


def _cf_encode(email: str, key: int = 0x42) -> str:
    return bytes([key, *(ord(c) ^ key for c in email)]).hex()


def test_decode_cfemail() -> None:
    assert decode_cfemail(_cf_encode("help@shop.test")) == "help@shop.test"


def test_cloudflare_email_replaces_placeholder() -> None:
    encoded = _cf_encode("help@shop.test")
    html = f'<p>Email <span data-cfemail="{encoded}">[email&#160;protected]</span> today</p>'
    assert html_to_text(html) == "Email help@shop.test today"
