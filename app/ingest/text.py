"""HTML-to-text conversion using only the standard library."""

import re
from html.parser import HTMLParser

# Content inside these tags is never shown to a reader, so it's noise for retrieval.
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}
# These tags start a new line, so text from neighbouring blocks doesn't run together.
_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


class _TextExtractor(HTMLParser):
    # A class because HTMLParser is callback-based; this is the stdlib's intended use.
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            # Like a browser: newlines in the HTML source are just spaces.
            # Only block tags (above) produce real line breaks.
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> str:
    """Visible text with one line per block and collapsed whitespace."""
    parser = _TextExtractor()
    parser.feed(html)
    raw = "".join(parser.parts)
    lines = (re.sub(r" +", " ", line).strip() for line in raw.splitlines())
    return "\n".join(line for line in lines if line)
