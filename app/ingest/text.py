"""HTML-to-text conversion using only the standard library."""

import re
from html.parser import HTMLParser

# Content inside these tags is never shown to a reader, so it's noise for retrieval.
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
# These tags start a new line, so text from neighbouring blocks doesn't run together.
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


def decode_cfemail(encoded: str) -> str:
    """Undo Cloudflare's email obfuscation: first hex byte is an XOR key for the rest."""
    data = bytes.fromhex(encoded)
    return bytes(b ^ data[0] for b in data[1:]).decode("utf-8", errors="replace")


class _TextExtractor(HTMLParser):
    # A class because HTMLParser is callback-based; this is the stdlib's intended use.
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        # Text inside <main>, kept separately: on full store pages everything outside
        # it is header, menus, and footer, which would drown out the real content.
        self.main_parts: list[str] = []
        self._skip_depth = 0
        self._main_depth = 0
        self._cfemail_tag: str | None = None

    def _emit(self, text: str) -> None:
        self.parts.append(text)
        if self._main_depth:
            self.main_parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        cfemail = dict(attrs).get("data-cfemail")
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "main":
            self._main_depth += 1
        elif cfemail and not self._skip_depth:
            # The tag's own text is a "[email protected]" placeholder; emit the real address.
            self._emit(decode_cfemail(cfemail))
            self._cfemail_tag = tag
        elif tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "main" and self._main_depth:
            self._main_depth -= 1
        elif tag == self._cfemail_tag:
            self._cfemail_tag = None
        elif tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and not self._cfemail_tag:
            # Like a browser: newlines in the HTML source are just spaces.
            # Only block tags (above) produce real line breaks.
            self._emit(re.sub(r"\s+", " ", data))


def _clean_lines(raw: str) -> str:
    lines = (re.sub(r" +", " ", line).strip() for line in raw.splitlines())
    return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    """Visible text with one line per block and collapsed whitespace.

    If the page has a <main> element, only its content is returned.
    """
    parser = _TextExtractor()
    parser.feed(html)
    main_text = _clean_lines("".join(parser.main_parts))
    return main_text or _clean_lines("".join(parser.parts))
