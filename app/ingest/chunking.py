"""Split page text into retrieval-sized passages."""

import re


def _split_long_line(line: str, max_chars: int) -> list[str]:
    """Break an oversized line at sentence ends, falling back to a hard cut."""
    pieces: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", line):
        while len(sentence) > max_chars:  # a single sentence that is still too long
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, title: str, max_chars: int) -> list[str]:
    """Group whole lines into chunks of at most max_chars (title included).

    Lines are kept intact where possible so a FAQ question stays with its answer.
    Chunks that don't already start with the page title get it as a first line, so
    a passage like "Within 7 days." still tells retrieval (and the model) it is
    about returns. The title must be much shorter than max_chars.
    """
    # Reserve room for the title line so prefixing never pushes a chunk over the limit.
    budget = max_chars - len(title) - 1
    lines: list[str] = []
    for line in text.splitlines():
        lines.extend(_split_long_line(line, budget) if len(line) > budget else [line])

    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        if current and len("\n".join([*current, line])) > budget:
            chunks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        chunks.append("\n".join(current))

    return [chunk if chunk.startswith(title) else f"{title}\n{chunk}" for chunk in chunks]
