"""Automatic checks for one eval answer. Pure functions, unit-tested in tests/.

The two checks that run on every case are the core promise of the product:
every price and every link in an answer must come from the data we retrieved.
"""

import re

from app.models import SearchResults

# "INR 359.00", "₹359", "Rs. 359", "359 rupees", "1,299 INR"
_NUMBER = r"(\d[\d,]*(?:\.\d+)?)"
PRICE_RE = re.compile(rf"(?:INR|Rs\.?|₹)\s?{_NUMBER}|{_NUMBER}\s?(?:INR|rupees)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)\]>\"'<]+")
HANDOFF_RE = re.compile(
    r"customer support|support team|connect you|contact|reach out|get in touch|help@|email us",
    re.IGNORECASE,
)
# Our internal prompt labels. A shopper should never see them in a reply.
INTERNAL_TERMS_RE = re.compile(r"store[ _]data|shopper[ _]message", re.IGNORECASE)
DEFAULT_MAX_WORDS = 120


def _to_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_prices(text: str) -> set[float]:
    return {_to_float(a or b) for a, b in PRICE_RE.findall(text)}


def extract_urls(text: str) -> set[str]:
    # Trailing punctuation is sentence text, not part of the link.
    return {url.rstrip(".,;:!?").rstrip("/") for url in URL_RE.findall(text)}


def allowed_prices(results: SearchResults, question: str) -> set[float]:
    """Every price the model was shown, plus numbers the shopper used (e.g. a budget)."""
    prices: set[float] = set()
    for p in results.products:
        if p.price is not None:
            prices.add(p.price)
        for v in p.variants:
            for key in ("price", "compare_at_price"):
                if v.get(key):
                    prices.add(_to_float(str(v[key])))
    for c in results.chunks:
        prices |= extract_prices(c.text)
    prices |= {_to_float(n) for n in re.findall(_NUMBER, question)}
    return prices


def allowed_urls(results: SearchResults, site_url: str) -> set[str]:
    urls = {site_url.rstrip("/")}
    urls |= {p.url.rstrip("/") for p in results.products}
    urls |= {c.source.rstrip("/") for c in results.chunks}
    return urls


def check_answer(case: dict, answer: str, results: SearchResults, site_url: str) -> list[str]:
    """All failed checks for one case, as readable messages. Empty means pass."""
    failures: list[str] = []

    allowed = allowed_prices(results, case["question"])
    for price in sorted(extract_prices(answer)):
        if not any(abs(price - ok) < 0.01 for ok in allowed):
            failures.append(f"price {price:g} not in retrieved data")

    for url in sorted(extract_urls(answer) - allowed_urls(results, site_url)):
        failures.append(f"link not in retrieved data: {url}")

    if INTERNAL_TERMS_RE.search(answer):
        failures.append("mentions internal prompt terms (e.g. 'store data')")

    words = len(answer.split())
    if words > case.get("max_words", DEFAULT_MAX_WORDS):
        failures.append(f"too long: {words} words")

    expected = case.get("expect_any", [])
    if expected and not any(term.lower() in answer.lower() for term in expected):
        failures.append(f"expected one of {expected}")

    if case.get("expect_handoff") and not HANDOFF_RE.search(answer):
        failures.append("expected a human handoff")

    for pattern in case.get("forbid", []):
        if re.search(pattern, answer):
            failures.append(f"forbidden pattern matched: {pattern}")

    return failures
