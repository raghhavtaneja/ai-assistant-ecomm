"""Plain data shapes passed between modules.

These are the contract between ingest, storage, retrieval, and chat. Storage
(app/db.py) converts to and from them, so swapping SQLite for Postgres
never changes these.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """One turn of a conversation, in provider-neutral form."""

    role: Literal["user", "assistant"]
    content: str


class Site(BaseModel):
    id: int
    url: str
    # Public, not a secret: it ends up in the embed snippet on the store's pages.
    public_key: str
    persona: dict = Field(default_factory=dict)
    created_at: datetime
    last_crawled_at: datetime | None = None


class Product(BaseModel):
    url: str
    title: str
    description: str = ""
    # Lowest variant price. A float is fine here: we only display and compare
    # prices, we never sum them, so rounding drift can't creep in.
    price: float | None = None
    currency: str | None = None
    image_url: str | None = None
    available: bool = False
    # Raw per-variant details (size, price, stock) kept for answering specifics.
    variants: list[dict] = Field(default_factory=list)
    embedding: list[float] | None = None
    id: int | None = None


class Chunk(BaseModel):
    """A passage of non-product text, e.g. part of a refund policy or FAQ page."""

    source: str  # page URL or PDF file name, shown to the shopper as the source
    text: str
    embedding: list[float] | None = None
    id: int | None = None


class SearchResults(BaseModel):
    """What retrieval hands to the answering step. Empty lists mean "nothing relevant"."""

    products: list[Product] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    # The product the shopper is looking at, if any; always included in `products` too.
    current_product: Product | None = None
