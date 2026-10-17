from app.ingest.chunking import chunk_text


def test_short_text_is_one_chunk() -> None:
    text = "Refund policy\nReturns within 7 days."
    assert chunk_text(text, "Refund policy", max_chars=200) == [text]


def test_lines_are_never_split_when_they_fit() -> None:
    lines = [f"Question {i}? Answer {i}." for i in range(10)]  # ~22 chars each
    chunks = chunk_text("\n".join(lines), "FAQs", max_chars=60)

    assert len(chunks) > 1
    body_lines = [line for chunk in chunks for line in chunk.splitlines() if line != "FAQs"]
    assert body_lines == lines  # nothing lost, nothing cut, order kept


def test_later_chunks_get_the_title() -> None:
    text = "Shipping Policy\n" + "\n".join(["x" * 40] * 4)
    chunks = chunk_text(text, "Shipping Policy", max_chars=60)

    assert all(chunk.startswith("Shipping Policy") for chunk in chunks)
    # The first chunk already starts with the title, so it isn't repeated.
    assert not chunks[0].startswith("Shipping Policy\nShipping Policy")


def test_long_line_splits_at_sentences() -> None:
    line = "First sentence here. Second sentence here. Third sentence here."
    chunks = chunk_text(line, "T", max_chars=45)

    assert [c.removeprefix("T\n") for c in chunks] == [
        "First sentence here. Second sentence here.",
        "Third sentence here.",
    ]


def test_no_chunk_exceeds_limit_after_title_prefix() -> None:
    text = "Shipping Policy\n" + "\n".join(["Sentence that fills space."] * 30)
    chunks = chunk_text(text, "Shipping Policy", max_chars=100)
    assert max(len(c) for c in chunks) <= 100


def test_unbreakable_text_is_hard_cut() -> None:
    chunks = chunk_text("a" * 25, "T", max_chars=10)
    assert "".join(c.removeprefix("T\n") for c in chunks) == "a" * 25
