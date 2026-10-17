from app.models import Chunk, Product, SearchResults
from evals.checks import (
    allowed_prices,
    check_answer,
    extract_prices,
    extract_urls,
)

SITE = "https://shop.test"
SERUM = Product(
    url=f"{SITE}/products/serum",
    title="Serum",
    price=494.0,
    currency="INR",
    variants=[
        {"title": "30ml", "price": "494.00", "compare_at_price": "549.00"},
        {"title": "10ml", "price": "237.00", "compare_at_price": None},
    ],
)
RESULTS = SearchResults(
    products=[SERUM],
    chunks=[Chunk(source=f"{SITE}/pages/shipping", text="Free shipping above ₹499.")],
)


def _case(**overrides: object) -> dict:
    return {"id": "t", "category": "test", "question": "Anything for acne?"} | overrides


def test_extract_prices_formats() -> None:
    text = "INR 494.00, ₹237, Rs. 1,299, Rs 50, 600 rupees and 75 INR but not 30ml or 7 days"
    assert extract_prices(text) == {494.0, 237.0, 1299.0, 50.0, 600.0, 75.0}


def test_extract_urls_handles_markdown_and_punctuation() -> None:
    text = f"See [Serum]({SITE}/products/serum). Or {SITE}/pages/faqs/, thanks."
    assert extract_urls(text) == {f"{SITE}/products/serum", f"{SITE}/pages/faqs"}


def test_allowed_prices_cover_variants_sales_chunks_and_question() -> None:
    allowed = allowed_prices(RESULTS, "under 500 rupees?")
    assert {494.0, 549.0, 237.0, 499.0, 500.0} <= allowed


def test_grounded_answer_passes() -> None:
    reply = f"Try the [Serum]({SITE}/products/serum): 10ml is INR 237.00, 30ml INR 494 (was ₹549)."
    assert check_answer(_case(), reply, RESULTS, SITE) == []


def test_invented_price_fails() -> None:
    failures = check_answer(_case(), "The Serum is ₹199 today.", RESULTS, SITE)
    assert failures == ["price 199 not in retrieved data"]


def test_invented_link_fails() -> None:
    reply = f"See {SITE}/products/made-up-serum"
    assert check_answer(_case(), reply, RESULTS, SITE) == [
        f"link not in retrieved data: {SITE}/products/made-up-serum"
    ]


def test_expectations_handoff_forbid_and_length() -> None:
    case = _case(
        expect_any=["salicylic"],
        expect_handoff=True,
        forbid=[r"\b[A-Z]{3,}\d{2,}\b"],
        max_words=5,
    )
    failures = check_answer(case, "Use code SAVE90 for a big discount today friend.", RESULTS, SITE)
    assert failures == [
        "too long: 9 words",
        "expected one of ['salicylic']",
        "expected a human handoff",
        r"forbidden pattern matched: \b[A-Z]{3,}\d{2,}\b",
    ]


def test_internal_prompt_terms_fail() -> None:
    reply = "I don't have that information in my current store data."
    assert check_answer(_case(), reply, SearchResults(), SITE) == [
        "mentions internal prompt terms (e.g. 'store data')"
    ]


def test_handoff_detected() -> None:
    case = _case(expect_handoff=True)
    reply = "I don't have that information. Would you like me to connect you with support?"
    assert check_answer(case, reply, SearchResults(), SITE) == []
