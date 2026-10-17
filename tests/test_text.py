from app.ingest.text import html_to_text


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
